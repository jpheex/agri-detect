"""
三方聯防協調器：Agri-Weather AI + Gemini 視覺診斷 + 本地 IPM 知識庫。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.agri_weather_ai import (
    AgriWeatherAIEngine,
    PlantWeatherWarningReport,
    format_weather_context_for_gemini,
)
from backend.plant_health_analyzer import (
    PlantHealthAnalyzerError,
    analyze_plant_health_for_app,
)
from backend.crop_disease_identifier import CropDiseaseIdentifierError, is_configured


class CompleteAgriAIOchestrator:
    def __init__(self) -> None:
        self.weather_engine = AgriWeatherAIEngine()

    def _merge_notes(self, user_notes: str | None, weather_report: PlantWeatherWarningReport) -> str:
        weather_ctx = format_weather_context_for_gemini(weather_report)
        if user_notes and user_notes.strip():
            return f"{user_notes.strip()}\n\n{weather_ctx}"
        return weather_ctx

    async def evaluate_weather_only(
        self, crop_name: str, lat: float, lon: float
    ) -> PlantWeatherWarningReport:
        return await self.weather_engine.evaluate_farm_health_risk(crop_name, lat, lon)

    async def execute_comprehensive_diagnostic_flow(
        self,
        crop_name: str,
        lat: float,
        lon: float,
        image_paths: list[str] | None = None,
        organ_labels: list[str] | None = None,
        user_notes: str | None = None,
        knowledge_entries: list[dict] | None = None,
    ) -> dict[str, Any]:
        weather_report = await self.weather_engine.evaluate_farm_health_risk(crop_name, lat, lon)

        output: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location_context": {"latitude": lat, "longitude": lon},
            "agri_weather_ai_proactive_warning": weather_report.model_dump(mode="json"),
        }

        if not image_paths:
            return output

        combined_notes = self._merge_notes(user_notes, weather_report)
        if is_configured():
            try:
                visual = await analyze_plant_health_for_app(
                    image_paths,
                    user_provided_crop=crop_name or None,
                    organ_labels=organ_labels,
                    user_notes=combined_notes,
                    knowledge_entries=knowledge_entries,
                )
                output["visual_ai_diagnostic_report"] = visual
                output["immediate_action_knowledge"] = {
                    "treatment_strategies": visual.get("treatment_strategies"),
                    "prevention_strategies": visual.get("prevention_strategies"),
                    "management_protocol": visual.get("management_protocol"),
                    "extension_links": visual.get("extension_links"),
                }
                return output
            except (PlantHealthAnalyzerError, CropDiseaseIdentifierError) as exc:
                output["visual_ai_error"] = str(exc)

        output["visual_ai_diagnostic_report"] = None
        return output


_orchestrator = CompleteAgriAIOchestrator()


async def evaluate_weather_risk(crop_name: str, lat: float, lon: float) -> dict[str, Any]:
    report = await _orchestrator.evaluate_weather_only(crop_name, lat, lon)
    return report.model_dump(mode="json")


async def run_comprehensive_diagnostic(
    crop_name: str,
    lat: float,
    lon: float,
    image_paths: list[str] | None = None,
    organ_labels: list[str] | None = None,
    user_notes: str | None = None,
    knowledge_entries: list[dict] | None = None,
) -> dict[str, Any]:
    return await _orchestrator.execute_comprehensive_diagnostic_flow(
        crop_name=crop_name,
        lat=lat,
        lon=lon,
        image_paths=image_paths,
        organ_labels=organ_labels,
        user_notes=user_notes,
        knowledge_entries=knowledge_entries,
    )
