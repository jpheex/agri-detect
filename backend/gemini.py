"""
Gemini 辨識相容層：保留舊 import 路徑，底層改用 crop_disease_identifier。
"""

from pathlib import Path

from backend.crop_disease_identifier import (
    CropDiseaseIdentifierError,
    GeminiAPIError,
    GeminiConfigError,
    GeminiInputError,
    GeminiParseError,
    GeminiTimeoutError,
    identify_crop_disease,
    identify_crop_disease_for_app,
    is_configured,
    merge_knowledge_advice,
    report_to_app_format,
)

__all__ = [
    "CropDiseaseIdentifierError",
    "GeminiAPIError",
    "GeminiConfigError",
    "GeminiInputError",
    "GeminiParseError",
    "GeminiTimeoutError",
    "identify_crop_disease",
    "identify_crop_disease_for_app",
    "is_configured",
    "merge_knowledge_advice",
    "predict_with_gemini",
    "report_to_app_format",
]


def predict_with_gemini(image_path: Path, knowledge_entries: list[dict]) -> dict:
    """同步相容函式（舊版介面）。"""
    import asyncio

    async def _run() -> dict:
        return await identify_crop_disease_for_app(
            [str(image_path)],
            knowledge_entries=knowledge_entries,
        )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("請在 async 環境改用 identify_crop_disease_for_app")
        return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())
