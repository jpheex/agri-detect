"""
離線同步服務：檔案落盤、背景 Gemini+氣象聯防、推播觸發。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile

from backend.agri_ai_orchestrator import run_comprehensive_diagnostic
from backend.config import DATA_DIR
from backend.database import list_knowledge_entries
from backend.offline_db import get_offline_task, update_task_status, upsert_offline_task
from backend.offline_rule_engine import evaluate_offline_rule_engine
from backend.offline_schemas import OfflineSelfCheckForm, SyncStatus
from backend.push_notifier import send_push_message

logger = logging.getLogger(__name__)

OFFLINE_SYNC_DIR = DATA_DIR / "offline_sync_vault"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _safe_task_id(task_id: str) -> str:
    """防止路徑穿越：僅允許 UUID 格式。"""
    try:
        uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="task_id 必須為有效 UUID") from exc
    return task_id


def _safe_extension(filename: str | None) -> str:
    ext = Path(filename or "image.jpg").suffix.lower()
    return ext if ext in ALLOWED_EXT else ".jpg"


async def save_uploaded_images(task_id: str, images: list[UploadFile]) -> list[str]:
    """
    將 multipart 上傳的影像安全寫入磁碟。

    回傳伺服器端絕對路徑列表；任一檔案失敗會清理已寫入檔案並拋出 HTTPException。
    """
    if not images:
        raise HTTPException(status_code=400, detail="至少需要上傳一張相片")

    task_dir = OFFLINE_SYNC_DIR / _safe_task_id(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []

    for index, upload in enumerate(images):
        ext = _safe_extension(upload.filename)
        target = task_dir / f"{task_id}_{index}{ext}"
        try:
            with target.open("wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
            if target.stat().st_size == 0:
                target.unlink(missing_ok=True)
                raise OSError("空檔案")
            saved.append(str(target.resolve()))
        except OSError as exc:
            for path in saved:
                Path(path).unlink(missing_ok=True)
            task_dir.rmdir() if task_dir.exists() and not any(task_dir.iterdir()) else None
            logger.exception("離線同步寫入失敗 task_id=%s index=%s", task_id, index)
            raise HTTPException(
                status_code=500,
                detail=f"伺服器寫入磁碟失敗（第 {index + 1} 張）：{exc}",
            ) from exc
        finally:
            await upload.close()

    if not saved:
        raise HTTPException(status_code=400, detail="未收到有效影像檔")
    return saved


async def trigger_push_notification(
    task_id: str,
    push_registration_id: str,
    diagnosis_result: dict[str, Any],
) -> bool:
    """
    推播接口：優先 FCM HTTP v1 Legacy，其次 LINE Notify / Webhook 備援。

    push_registration 為 FCM 推播註冊識別碼；若未設定 FCM_SERVER_KEY 則記錄日誌並走備援推播。
    """
    crop = diagnosis_result.get("crop") or diagnosis_result.get("crop_name") or "作物"
    issue = (
        diagnosis_result.get("issue_name")
        or diagnosis_result.get("primary_diagnosis")
        or "待確認"
    )
    title = "🌾 AI 延遲診斷報告已出爐"
    body = (
        f"您的【{crop}】AI 診斷報告已出爐！確診為：{issue}，"
        f"請立刻查看最新 IPM 防治方案。（任務 {task_id[:8]}…）"
    )

    fcm_key = os.getenv("FCM_SERVER_KEY", "").strip()
    if fcm_key and push_registration_id:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    headers={
                        "Authorization": "key=" + fcm_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "to": push_registration_id,
                        "notification": {"title": title, "body": body},
                        "data": {
                            "task_id": task_id,
                            "crop_name": str(crop),
                            "primary_diagnosis": str(issue),
                        },
                    },
                )
                if response.status_code == 200:
                    payload = response.json()
                    if payload.get("success", 0) >= 1:
                        logger.info("[FCM] 推播成功 task_id=%s", task_id)
                        return True
        except Exception:
            logger.exception("[FCM] 推播失敗 task_id=%s", task_id)

    # 備援：LINE Notify / Webhook（農民可能綁定 LINE 而非 FCM）
    sent = await send_push_message(
        title,
        body,
        extra={"task_id": task_id, "push_registration_id": push_registration_id, "diagnosis": diagnosis_result},
    )
    if sent:
        logger.info("[PUSH] 備援推播成功 task_id=%s", task_id)
    else:
        logger.info("[PUSH] 未設定推播管道，僅寫入雲端 task_id=%s", task_id)
    return sent


async def process_offline_diagnostic_task(task_id: str) -> None:
    """
    背景佇列：Gemini 視覺 + 微氣象 AI + IPM 知識庫，完成後推播。
    """
    row = await get_offline_task(task_id)
    if not row:
        logger.warning("找不到離線任務 task_id=%s", task_id)
        return

    await update_task_status(task_id, SyncStatus.SYNCING)

    try:
        image_paths = json.loads(row.saved_image_paths or "[]")
        self_check = OfflineSelfCheckForm.model_validate(json.loads(row.offline_self_check or "{}"))
        knowledge_entries = await list_knowledge_entries()

        notes = json.dumps(
            evaluate_offline_rule_engine(row.crop_name, self_check),
            ensure_ascii=False,
        )

        payload = await run_comprehensive_diagnostic(
            crop_name=row.crop_name,
            lat=float(row.latitude),
            lon=float(row.longitude),
            image_paths=image_paths,
            organ_labels=None,
            user_notes=f"離線自主檢查表：{self_check.model_dump_json()}\n離線規則建議：{notes}",
            knowledge_entries=knowledge_entries,
        )

        visual = payload.get("visual_ai_diagnostic_report") or {}
        diagnosis_result = {
            "task_id": task_id,
            "crop": visual.get("crop") or row.crop_name,
            "crop_name": row.crop_name,
            "issue_type": visual.get("issue_type"),
            "issue_name": visual.get("issue_name") or visual.get("primary_diagnosis"),
            "primary_diagnosis": visual.get("issue_name") or visual.get("primary_diagnosis"),
            "confidence": visual.get("confidence") or visual.get("confidence_score"),
            "confidence_score": visual.get("confidence_score") or visual.get("confidence"),
            "treatment_strategies": visual.get("treatment_strategies"),
            "prevention_strategies": visual.get("prevention_strategies"),
            "management_protocol": visual.get("management_protocol"),
            "agri_weather_ai_proactive_warning": payload.get("agri_weather_ai_proactive_warning"),
            "offline_self_check": self_check.model_dump(),
            "offline_rule_hint": evaluate_offline_rule_engine(row.crop_name, self_check),
            "record_url_hint": f"/api/v1/diagnostic/sync/{task_id}",
        }

        await update_task_status(task_id, SyncStatus.COMPLETED, diagnosis_result=diagnosis_result)

        if row.push_registration_id:
            await trigger_push_notification(task_id, row.push_registration_id, diagnosis_result)

    except Exception as exc:
        logger.exception("離線任務背景處理失敗 task_id=%s", task_id)
        await update_task_status(task_id, SyncStatus.FAILED, error_message=str(exc))


async def enqueue_offline_sync(
    *,
    task_id: str,
    crop_name: str,
    latitude: float,
    longitude: float,
    self_check: OfflineSelfCheckForm,
    saved_image_paths: list[str],
    push_registration_id: str | None,
) -> dict[str, Any]:
    """建立佇列紀錄並回傳離線規則提示。"""
    _safe_task_id(task_id)
    crop = crop_name.strip()
    if not crop:
        raise HTTPException(status_code=400, detail="crop_name 不可為空")

    await upsert_offline_task(
        task_id=task_id,
        crop_name=crop,
        latitude=latitude,
        longitude=longitude,
        saved_image_paths=saved_image_paths,
        offline_self_check=self_check.model_dump(),
        push_registration_id=push_registration_id,
        sync_status=SyncStatus.PENDING,
    )

    rule_hint = evaluate_offline_rule_engine(crop, self_check)
    return rule_hint
