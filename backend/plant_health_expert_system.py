"""
植物健康 AI 聯防專家系統。

整合：Gemini 多部位視覺診斷 + 本地 IPM 權威知識庫。
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

from backend.crop_disease_identifier import (
    GeminiAPIError,
    GeminiConfigError,
    GeminiInputError,
    GeminiParseError,
    GeminiTimeoutError,
    is_configured,
    merge_knowledge_advice,
)
from backend.disease_management_kb import (
    IPM_DISCLAIMER,
    enrich_diagnosis_with_management,
)
from backend.image_preprocess import image_to_jpeg_bytes

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_TIMEOUT_SEC", "90"))
MAX_IMAGES = int(os.getenv("GEMINI_MAX_IMAGES", "8"))
MAX_IMAGE_EDGE = int(os.getenv("GEMINI_IMAGE_MAX_EDGE", "1024"))

ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

ORGAN_LABELS = {
    "leaves": "葉子 (Leaves)",
    "flowers": "花朵 (Flowers)",
    "stems_trunk": "枝條/樹幹 (Stems/Trunk)",
}

SYSTEM_INSTRUCTION = """你是一位精通亞熱帶與溫帶作物的植物學、植物病理學與昆蟲學專家。
當收到使用者上傳的植物影像時，你必須依據以下「部位特徵鏈 (Organ-Specific Chain)」進行嚴謹分析：

【步驟一：植物種類鑑別】
- 觀察葉形、花冠結構、枝條皮孔、主幹分枝型態，判定植物繁體中文名稱與學名。

【步驟二：多部位病徵掃描】
- 葉子 (Leaves)：檢查正面與背面。注意炭疽病斑、白粉病、捲葉、潛葉蟲食痕、紅蜘蛛絲網或蚜蟲聚集。
- 花朵 (Flowers)：檢查花瓣與花萼。注意薊馬褐化、灰黴病腐爛、畸形花。
- 枝條/樹幹 (Stems/Trunk)：檢查表皮。注意天牛流膠、介殼蟲寄生、潰瘍病斑、木質部枯萎。

【步驟三：鑑別診斷與信心評估】
- 排除生理障礙（缺水、缺肥、肥傷、曬傷、寒害）。
- 產出最終診斷與信心指數；影像不足時調低信心並在 photo_feedback 明示。

health_status 只能填：健康、受病害侵襲、受蟲害危害、疑似生理障礙。
輸出語言：繁體中文（學名用拉丁文）。"""


class OrganStatus(BaseModel):
    observed_symptoms: str = Field(description="該部位觀察到的視覺病徵")
    suspected_issue: str = Field(description="疑似病害、蟲害或生理障礙")


class OrganAnalysis(BaseModel):
    leaves: OrganStatus
    flowers: OrganStatus
    stems_trunk: OrganStatus


HealthStatus = Literal["健康", "受病害侵襲", "受蟲害危害", "疑似生理障礙"]


class PlantDiagnosisResult(BaseModel):
    """Gemini 必須遵守的結構化診斷 JSON。"""

    common_name: str
    scientific_name: str
    health_status: HealthStatus
    primary_diagnosis: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    organ_analysis: OrganAnalysis
    expert_reasoning: str
    photo_feedback: str


class PlantHealthExpertSystem:
    """農業 AI 診斷 + IPM 知識庫聯防引擎。"""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or MODEL_NAME

    def _validate_paths(self, image_paths: list[str]) -> list[Path]:
        if not image_paths:
            raise GeminiInputError("至少需要提供一張影像路徑")
        if len(image_paths) > MAX_IMAGES:
            raise GeminiInputError(f"最多支援 {MAX_IMAGES} 張影像")
        resolved: list[Path] = []
        for raw in image_paths:
            path = Path(raw).expanduser().resolve()
            if not path.exists():
                raise GeminiInputError(f"找不到影像檔案：{path}")
            if path.suffix.lower() not in ALLOWED_SUFFIX:
                raise GeminiInputError(f"不支援的影像格式：{path.suffix}")
            resolved.append(path)
        return resolved

    def _build_image_parts(self, image_paths: list[Path]) -> list[Any]:
        from google.genai import types

        parts: list[Any] = []
        for index, path in enumerate(image_paths, start=1):
            image_bytes = image_to_jpeg_bytes(path, max_edge=MAX_IMAGE_EDGE)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
            parts.append(f"【影像 {index}/{len(image_paths)}】")
        return parts

    def _build_prompt(
        self,
        image_count: int,
        organ_labels: list[str] | None,
        user_provided_crop: str | None,
        user_notes: str | None,
    ) -> str:
        lines = [
            "請仔細掃描這些植物照片，依部位特徵鏈給出結構化診斷 JSON。",
            f"影像數量：{image_count} 張",
        ]
        if organ_labels:
            lines.append("部位標記（依影像順序）：")
            for idx, label in enumerate(organ_labels, start=1):
                lines.append(f"- 影像 {idx}：{ORGAN_LABELS.get(label, label)}")
        if user_provided_crop:
            lines.append(f"使用者提示：此作物可能為【{user_provided_crop.strip()}】，請驗證。")
        if user_notes:
            lines.append(f"使用者補充：{user_notes.strip()}")
        return "\n".join(lines)

    def _sync_gemini_diagnose(
        self,
        image_paths: list[Path],
        organ_labels: list[str] | None,
        user_provided_crop: str | None,
        user_notes: str | None,
    ) -> PlantDiagnosisResult:
        if not is_configured():
            raise GeminiConfigError("未設定 GEMINI_API_KEY")

        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        client = genai.Client(api_key=API_KEY)
        contents = self._build_image_parts(image_paths)
        contents.append(
            self._build_prompt(len(image_paths), organ_labels, user_provided_crop, user_notes)
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=PlantDiagnosisResult,
                    temperature=0.1,
                ),
            )
        except genai_errors.APIError as exc:
            message = str(exc)
            if "API key" in message or exc.code in {401, 403}:
                raise GeminiConfigError("Gemini API 金鑰無效或未授權") from exc
            raise GeminiAPIError(f"Gemini API 呼叫失敗：{message}") from exc
        except Exception as exc:
            raise GeminiAPIError(f"Gemini API 未知錯誤：{exc}") from exc

        text = (response.text or "").strip()
        if not text:
            raise GeminiParseError("Gemini 回傳內容為空")
        try:
            return PlantDiagnosisResult.model_validate_json(text)
        except ValidationError as exc:
            raise GeminiParseError(f"JSON 結構驗證失敗：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise GeminiParseError(f"JSON 解析失敗：{exc}") from exc

    async def analyze_plant_health(
        self,
        image_paths: list[str],
        user_provided_crop: str | None = None,
        organ_labels: list[str] | None = None,
        user_notes: str | None = None,
    ) -> dict[str, Any]:
        paths = self._validate_paths(image_paths)
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SEC):
                ai_result = await asyncio.to_thread(
                    self._sync_gemini_diagnose,
                    paths,
                    organ_labels,
                    user_provided_crop,
                    user_notes,
                )
        except TimeoutError as exc:
            raise GeminiTimeoutError(f"分析逾時（>{REQUEST_TIMEOUT_SEC} 秒）") from exc

        app_result = diagnosis_to_app_format(ai_result)
        app_result["ai_diagnostic_report"] = ai_result.model_dump()
        app_result = await enrich_diagnosis_with_management(app_result)
        app_result["authoritative_treatment_knowledge"] = app_result.get("management_protocol", {})
        return app_result


def _health_status_to_issue_type(health_status: str, primary_diagnosis: str) -> str:
    mapping = {
        "健康": "健康",
        "受病害侵襲": "病害",
        "受蟲害危害": "蟲害",
        "疑似生理障礙": "生理障礙",
    }
    if health_status in mapping:
        return mapping[health_status]
    if primary_diagnosis in {"無", "健康"}:
        return "健康"
    return "待確認"


def diagnosis_to_app_format(result: PlantDiagnosisResult, source: str = "Gemini") -> dict[str, Any]:
    issue_type = _health_status_to_issue_type(result.health_status, result.primary_diagnosis)
    issue_name = result.primary_diagnosis.strip() or "待確認"
    if issue_type == "健康":
        issue_name = "健康"

    return {
        "crop": result.common_name.strip() or "未確定",
        "issue_type": issue_type,
        "issue_name": issue_name,
        "confidence": round(float(result.confidence_score), 2),
        "treatment": "待 IPM 知識庫補充",
        "prevention": "待 IPM 知識庫補充",
        "source": source,
        "health_status": result.health_status,
        "scientific_name": result.scientific_name,
        "primary_diagnosis": result.primary_diagnosis,
        "confidence_score": result.confidence_score,
        "organ_analysis": result.organ_analysis.model_dump(),
        "expert_reasoning": result.expert_reasoning,
        "photo_feedback": result.photo_feedback,
        "plant_identity": {
            "common_name": result.common_name,
            "scientific_name": result.scientific_name,
        },
        "ipm_disclaimer": IPM_DISCLAIMER,
    }


_expert_system = PlantHealthExpertSystem()


async def analyze_plant_health(
    image_paths: list[str],
    user_provided_crop: str | None = None,
    organ_labels: list[str] | None = None,
    user_notes: str | None = None,
) -> dict[str, Any]:
    return await _expert_system.analyze_plant_health(
        image_paths,
        user_provided_crop=user_provided_crop,
        organ_labels=organ_labels,
        user_notes=user_notes,
    )


async def analyze_plant_health_for_app(
    image_paths: list[str],
    user_provided_crop: str | None = None,
    organ_labels: list[str] | None = None,
    user_notes: str | None = None,
    knowledge_entries: list[dict] | None = None,
) -> dict[str, Any]:
    result = await analyze_plant_health(
        image_paths,
        user_provided_crop=user_provided_crop,
        organ_labels=organ_labels,
        user_notes=user_notes,
    )
    if knowledge_entries and result.get("issue_type") not in {"生理障礙"}:
        result = merge_knowledge_advice(result, knowledge_entries)
    return result


class PlantHealthAnalyzerError(Exception):
    """向後相容例外別名。"""
