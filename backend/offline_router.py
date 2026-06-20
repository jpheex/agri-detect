"""
離線同步 API 路由（/api/v1/diagnostic/*）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from backend.offline_db import get_offline_task
from backend.offline_rule_engine import evaluate_offline_rule_engine
from backend.offline_schemas import (
    OfflineBatchSyncItem,
    OfflineBatchSyncResponse,
    OfflineSelfCheckForm,
    OfflineSyncQueuedResponse,
    OfflineSyncStatusResponse,
    SyncStatus,
)
from backend.offline_sync_service import (
    enqueue_offline_sync,
    process_offline_diagnostic_task,
    save_uploaded_images,
)

router = APIRouter(prefix="/api/v1/diagnostic", tags=["offline-diagnostic"])


def _parse_self_check(
    has_webbing: bool,
    has_gummosis: bool,
    has_white_powder: bool,
    has_water_soaked_spots: bool,
    after_rain: bool,
    affected_part: str,
) -> OfflineSelfCheckForm:
    try:
        return OfflineSelfCheckForm(
            has_webbing=has_webbing,
            has_gummosis=has_gummosis,
            has_white_powder=has_white_powder,
            has_water_soaked_spots=has_water_soaked_spots,
            after_rain=after_rain,
            affected_part=affected_part,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"自主檢查表單格式錯誤：{exc}") from exc


@router.post("/offline-evaluate")
async def offline_evaluate(
    crop_name: str = Form(...),
    has_webbing: bool = Form(False),
    has_gummosis: bool = Form(False),
    has_white_powder: bool = Form(False),
    has_water_soaked_spots: bool = Form(False),
    after_rain: bool = Form(False),
    affected_part: str = Form("leaves"),
):
    """離線規則引擎（可供前端連網時驗證，或 PWA 快取後本地鏡像）。"""
    check = _parse_self_check(
        has_webbing,
        has_gummosis,
        has_white_powder,
        has_water_soaked_spots,
        after_rain,
        affected_part,
    )
    return evaluate_offline_rule_engine(crop_name, check)


@router.post("/sync", response_model=OfflineSyncQueuedResponse)
async def sync_offline_task(
    background_tasks: BackgroundTasks,
    task_id: str = Form(..., description="手機本地 UUID"),
    crop_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    push_registration: str = Form(""),
    has_webbing: bool = Form(False),
    has_gummosis: bool = Form(False),
    has_white_powder: bool = Form(False),
    has_water_soaked_spots: bool = Form(False),
    after_rain: bool = Form(False),
    affected_part: str = Form("leaves"),
    images: list[UploadFile] = File(..., description="離線期間拍攝的相片"),
):
    """
    連網同步接口：立刻回 queued，Gemini 診斷在背景執行。
    """
    self_check = _parse_self_check(
        has_webbing,
        has_gummosis,
        has_white_powder,
        has_water_soaked_spots,
        after_rain,
        affected_part,
    )
    saved_paths = await save_uploaded_images(task_id, images)
    rule_hint = await enqueue_offline_sync(
        task_id=task_id,
        crop_name=crop_name,
        latitude=latitude,
        longitude=longitude,
        self_check=self_check,
        saved_image_paths=saved_paths,
        push_registration_id=push_registration.strip() or None,
    )

    background_tasks.add_task(process_offline_diagnostic_task, task_id)

    from backend.offline_schemas import OfflineRuleEngineResult

    return OfflineSyncQueuedResponse(
        task_id=task_id,
        message="離線數據與相片已安全鎖存，診斷引擎已進入背景佇列，完成後將推播通知。",
        offline_rule_hint=OfflineRuleEngineResult.model_validate(rule_hint),
    )


@router.post("/sync/batch", response_model=OfflineBatchSyncResponse)
async def sync_offline_batch(
    background_tasks: BackgroundTasks,
    tasks_json: str = Form(..., description="OfflineBatchSyncItem 陣列 JSON"),
    images: list[UploadFile] = File(default=[]),
):
    """
    批次同步：tasks_json 為中繼資料陣列；影像檔名需為 `{task_id}__{index}.jpg`。
    """
    try:
        raw_items = json.loads(tasks_json)
        items = [OfflineBatchSyncItem.model_validate(item) for item in raw_items]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"tasks_json 解析失敗：{exc}") from exc

    images_by_task: dict[str, list[UploadFile]] = {}
    for upload in images:
        name = upload.filename or ""
        if "__" not in name:
            raise HTTPException(status_code=400, detail=f"批次影像檔名格式錯誤：{name}")
        task_key = name.split("__", 1)[0]
        images_by_task.setdefault(task_key, []).append(upload)

    queued: list[str] = []
    for item in items:
        task_images = images_by_task.get(item.task_id, [])
        if len(task_images) < item.image_count:
            raise HTTPException(
                status_code=400,
                detail=f"任務 {item.task_id} 影像數不足（需 {item.image_count} 張）",
            )
        saved_paths = await save_uploaded_images(item.task_id, task_images)
        await enqueue_offline_sync(
            task_id=item.task_id,
            crop_name=item.crop_name,
            latitude=item.latitude,
            longitude=item.longitude,
            self_check=item.offline_self_check,
            saved_image_paths=saved_paths,
            push_registration_id=item.push_registration_id,
        )
        background_tasks.add_task(process_offline_diagnostic_task, item.task_id)
        queued.append(item.task_id)

    return OfflineBatchSyncResponse(
        queued_task_ids=queued,
        message=f"已將 {len(queued)} 筆離線任務排入背景佇列。",
    )


@router.get("/sync/{task_id}", response_model=OfflineSyncStatusResponse)
async def get_sync_status(task_id: str):
    """查詢背景診斷進度（前端輪詢或推播後開啟）。"""
    row = await get_offline_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="找不到離線同步任務")

    diagnosis = None
    if row.diagnosis_result:
        try:
            diagnosis = json.loads(row.diagnosis_result)
        except json.JSONDecodeError:
            diagnosis = {"raw": row.diagnosis_result}

    return OfflineSyncStatusResponse(
        task_id=row.task_id,
        sync_status=SyncStatus(row.sync_status),
        diagnosis_result=diagnosis,
        error_message=row.error_message,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
