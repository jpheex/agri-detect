"""
農業病蟲害 Gemini 多模態辨識核心模組。

使用 google-genai SDK，支援多圖輸入、System Instruction 與結構化 JSON 輸出。
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

load_dotenv()

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_TIMEOUT_SEC", "90"))
MAX_IMAGES = int(os.getenv("GEMINI_MAX_IMAGES", "8"))

ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

SYSTEM_INSTRUCTION = """你是一位精通亞熱帶與溫帶作物的植物病理學與昆蟲學專家。
當收到作物影像時，你必須嚴謹地執行以下「視覺鏈」推理步驟：
1. 分析受害部位（老葉、新芽、莖、果實）。
2. 評估微觀特徵（病斑顏色、形狀、有無暈圈、有無分生孢子、有無昆蟲排泄物或網絲）。
3. 進行鑑別診斷，比較相似病害的微細差異。
4. 最終做出判定，並給出信心指數。如果影像過於模糊或特徵不足，請調低信心指數並在備註提示需要哪些部位的局部照片。

輸出語言：繁體中文（學名可附拉丁文）。
若判定為健康植株，diagnosis 請寫「健康」並在 treatment_suggestions 提供管理建議。
若無法判定，請降低 confidence_score 並在 ror_notes 說明需補拍哪些角度。"""

USER_PROMPT_TEMPLATE = """請依 System Instruction 的視覺鏈步驟，分析以下作物影像並輸出結構化 JSON。

影像數量：{image_count} 張
{notes_block}
請完成鑑別診斷，treatment_suggestions 需包含可行的生物、物理或安全採收期化學防治建議。"""


# ---------------------------------------------------------------------------
# Pydantic Schema（Gemini Structured Output）
# ---------------------------------------------------------------------------


class VisualAnalysis(BaseModel):
    """視覺分析結果。"""

    affected_parts: str = Field(description="受害部位描述，例如：老葉、新芽、果實")
    symptoms: str = Field(description="病斑或蟲害特徵的詳細描述")


class CropDiseaseReport(BaseModel):
    """Gemini 結構化辨識報告。"""

    crop_name: str = Field(description="作物中文名稱，例如：番茄、草莓")
    diagnosis: str = Field(description="最終判定的病蟲害中文名稱與學名")
    confidence_score: float = Field(ge=0.0, le=1.0, description="信心指數 0.0~1.0")
    visual_analysis: VisualAnalysis
    treatment_suggestions: list[str] = Field(min_length=1, description="防治對策清單")
    ror_notes: str = Field(description="備註，例如影像不清或需補充的拍攝角度")

    @field_validator("treatment_suggestions")
    @classmethod
    def strip_suggestions(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("treatment_suggestions 不可為空")
        return cleaned


def response_json_schema() -> dict[str, Any]:
    """產生 Gemini 可用的 JSON Schema（避免 additionalProperties 問題）。"""
    return {
        "type": "object",
        "required": [
            "crop_name",
            "diagnosis",
            "confidence_score",
            "visual_analysis",
            "treatment_suggestions",
            "ror_notes",
        ],
        "properties": {
            "crop_name": {"type": "string"},
            "diagnosis": {"type": "string"},
            "confidence_score": {"type": "number"},
            "visual_analysis": {
                "type": "object",
                "required": ["affected_parts", "symptoms"],
                "properties": {
                    "affected_parts": {"type": "string"},
                    "symptoms": {"type": "string"},
                },
            },
            "treatment_suggestions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "ror_notes": {"type": "string"},
        },
    }


# ---------------------------------------------------------------------------
# 自訂例外
# ---------------------------------------------------------------------------


class CropDiseaseIdentifierError(Exception):
    """辨識模組基底例外。"""


class GeminiConfigError(CropDiseaseIdentifierError):
    """API 金鑰或設定錯誤。"""


class GeminiInputError(CropDiseaseIdentifierError):
    """輸入影像無效。"""


class GeminiAPIError(CropDiseaseIdentifierError):
    """呼叫 Gemini API 失敗。"""


class GeminiTimeoutError(GeminiAPIError):
    """API 請求逾時。"""


class GeminiParseError(CropDiseaseIdentifierError):
    """結構化 JSON 解析或驗證失敗。"""


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """是否已設定 GEMINI_API_KEY。"""
    return bool(API_KEY)


def _guess_mime(path: Path) -> str:
    """依副檔名推斷 MIME，預設 image/jpeg。"""
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".bmp":
        return "image/bmp"
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "image/jpeg"


def _validate_image_paths(image_paths: list[str]) -> list[Path]:
    """驗證並標準化影像路徑清單。"""
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


def _build_user_prompt(image_count: int, user_notes: str | None) -> str:
    """組合使用者 Prompt。"""
    notes_block = ""
    if user_notes and user_notes.strip():
        notes_block = f"使用者補充說明：{user_notes.strip()}"
    return USER_PROMPT_TEMPLATE.format(image_count=image_count, notes_block=notes_block)


def _build_image_parts(image_paths: list[Path]) -> list[Any]:
    """將影像轉為 Gemini Part 清單。"""
    from google.genai import types

    parts: list[Any] = []
    for index, path in enumerate(image_paths, start=1):
        mime_type = _guess_mime(path)
        image_bytes = path.read_bytes()
        parts.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=mime_type,
            )
        )
        parts.append(f"【影像 {index}/{len(image_paths)}】檔名：{path.name}")
    return parts


def _parse_report(raw_text: str) -> CropDiseaseReport:
    """解析 Gemini 回傳 JSON 並以 Pydantic 驗證。"""
    text = (raw_text or "").strip()
    if not text:
        raise GeminiParseError("Gemini 回傳內容為空")

    try:
        return CropDiseaseReport.model_validate_json(text)
    except ValidationError as exc:
        raise GeminiParseError(f"JSON 結構驗證失敗：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise GeminiParseError(f"JSON 解析失敗：{exc}") from exc


def _classify_issue_type(diagnosis: str) -> str:
    """由 diagnosis 文字推斷問題類型。"""
    text = diagnosis.lower()
    if "健康" in diagnosis or "healthy" in text:
        return "健康"
    if any(keyword in diagnosis for keyword in ("蟲", "螟", "蝨", "蚜", "螨", "蛾", "蝇", "蟎")):
        return "蟲害"
    if any(keyword in diagnosis for keyword in ("病", "疫", "霉", "腐", "枯", "斑", "锈", "鏽")):
        return "病害"
    return "待確認"


def report_to_app_format(report: CropDiseaseReport, source: str = "Gemini") -> dict[str, Any]:
    """
    將結構化報告轉為網站既有 API 格式，並保留完整分析欄位。
    """
    issue_type = _classify_issue_type(report.diagnosis)
    treatment = "；".join(report.treatment_suggestions[:3])
    prevention = report.treatment_suggestions[-1] if len(report.treatment_suggestions) > 1 else report.ror_notes

    return {
        "crop": report.crop_name.strip() or "未確定",
        "issue_type": issue_type,
        "issue_name": report.diagnosis.strip() or "待確認",
        "confidence": round(float(report.confidence_score), 2),
        "treatment": treatment,
        "prevention": prevention or "維持良好栽培管理與定期巡查。",
        "source": source,
        "crop_name": report.crop_name,
        "diagnosis": report.diagnosis,
        "confidence_score": report.confidence_score,
        "visual_analysis": report.visual_analysis.model_dump(),
        "treatment_suggestions": report.treatment_suggestions,
        "ror_notes": report.ror_notes,
    }


def merge_knowledge_advice(result: dict[str, Any], knowledge_entries: list[dict]) -> dict[str, Any]:
    """若網站知識庫有相同品種/病蟲害，優先採用在地治療與預防建議。"""
    from backend.knowledge import resolve_advice

    for item in knowledge_entries:
        crop_match = item.get("crop") == result.get("crop")
        issue_match = item.get("issue_name") == result.get("issue_name")
        if crop_match and issue_match:
            treatment, prevention = resolve_advice(
                result["crop"],
                result["issue_type"],
                result["issue_name"],
                item.get("treatment", ""),
                item.get("prevention", ""),
            )
            result["treatment"] = treatment
            result["prevention"] = prevention
            result["source"] = "Gemini + 網站知識庫"
            return result

    treatment, prevention = resolve_advice(
        result["crop"],
        result["issue_type"],
        result["issue_name"],
        result.get("treatment", ""),
        result.get("prevention", ""),
    )
    result["treatment"] = treatment
    result["prevention"] = prevention
    return result


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------


def _sync_identify(image_paths: list[Path], user_notes: str | None) -> CropDiseaseReport:
    """同步呼叫 Gemini（供 asyncio.to_thread 使用）。"""
    if not is_configured():
        raise GeminiConfigError("未設定 GEMINI_API_KEY，請在 .env 填入有效金鑰")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types

    client = genai.Client(api_key=API_KEY)
    user_prompt = _build_user_prompt(len(image_paths), user_notes)
    contents: list[Any] = _build_image_parts(image_paths)
    contents.append(user_prompt)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_json_schema=response_json_schema(),
                temperature=0.2,
            ),
        )
    except genai_errors.APIError as exc:
        message = str(exc)
        if "API key" in message or "API_KEY" in message or exc.code in {401, 403}:
            raise GeminiConfigError("Gemini API 金鑰無效或未授權") from exc
        raise GeminiAPIError(f"Gemini API 呼叫失敗：{message}") from exc
    except TimeoutError as exc:
        raise GeminiTimeoutError("Gemini API 請求逾時") from exc
    except Exception as exc:
        raise GeminiAPIError(f"Gemini API 未知錯誤：{exc}") from exc

    return _parse_report(response.text or "")


async def identify_crop_disease(
    image_paths: list[str],
    user_notes: str | None = None,
) -> CropDiseaseReport:
    """
    使用 Gemini 多模態 API 辨識作物病蟲害。

    Args:
        image_paths: 本機影像路徑清單（可含葉面、葉背、全株等多張照片）
        user_notes: 使用者補充說明（選填）

    Returns:
        CropDiseaseReport 結構化辨識報告

    Raises:
        GeminiConfigError / GeminiInputError / GeminiAPIError /
        GeminiTimeoutError / GeminiParseError
    """
    paths = _validate_image_paths(image_paths)

    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_SEC):
            return await asyncio.to_thread(_sync_identify, paths, user_notes)
    except TimeoutError as exc:
        raise GeminiTimeoutError(f"辨識逾時（>{REQUEST_TIMEOUT_SEC} 秒）") from exc


async def identify_crop_disease_for_app(
    image_paths: list[str],
    user_notes: str | None = None,
    knowledge_entries: list[dict] | None = None,
) -> dict[str, Any]:
    """
    封裝給 FastAPI 使用：回傳網站相容 dict，並合併知識庫建議。
    """
    report = await identify_crop_disease(image_paths, user_notes)
    result = report_to_app_format(report)
    if knowledge_entries:
        result = merge_knowledge_advice(result, knowledge_entries)
    return result
