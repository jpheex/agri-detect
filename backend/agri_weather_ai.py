"""
Agri-Weather AI：微氣象抓取、葉面濕潤度估算與作物病蟲害風險評估。
"""

from __future__ import annotations

import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from backend.config import DATA_DIR

RISK_LABELS = {
    "LOW": "安全 (LOW)",
    "MEDIUM": "注意 (MEDIUM)",
    "HIGH": "高風險 (HIGH)",
}

WEATHER_STATE_PATH = DATA_DIR / "weather_leaf_wetness.json"


class MicroWeatherData(BaseModel):
    """即時微氣象數據。"""

    station_id: str = Field(description="氣象觀測站編號或田間 IoT 設備 ID")
    temperature: float = Field(description="現在溫度 (°C)")
    humidity: float = Field(description="現在相對濕度 (%)")
    rainfall_24h: float = Field(description="過去 24 小時累積雨量 (mm)")
    leaf_wetness_hours: float = Field(default=0.0, description="葉面連續濕潤時數 (小時)")
    forecast_rain_prob: float = Field(default=0.0, description="未來 24 小時降雨機率 (0.0 ~ 1.0)")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_source: str = Field(default="simulation", description="cwa | simulation")


class DiseaseRiskAssessment(BaseModel):
    """單一病蟲害風險評估。"""

    disease_id: str
    disease_name: str
    risk_level: str = Field(description="LOW | MEDIUM | HIGH")
    risk_level_label: str = Field(default="", description="繁中顯示標籤")
    risk_score: float = Field(ge=0.0, le=1.0)
    trigger_reason: str
    prevention_hint: str


class PlantWeatherWarningReport(BaseModel):
    """微氣象預警報告。"""

    crop_name: str
    current_weather: MicroWeatherData
    risk_assessments: list[DiseaseRiskAssessment]
    summary_7d: "WeatherSummary7d | None" = None
    environmental_stress: list["EnvironmentalStressItem"] = Field(default_factory=list)


class DailyWeatherRecord(BaseModel):
    date: str
    temp_min: float
    temp_max: float
    temp_mean: float
    humidity_mean: float
    precipitation_mm: float


class WeatherSummary7d(BaseModel):
    days: list[DailyWeatherRecord] = Field(default_factory=list)
    avg_temperature: float = 0.0
    avg_humidity: float = 0.0
    total_precipitation_mm: float = 0.0
    consecutive_rain_days: int = 0
    consecutive_hot_days: int = 0
    consecutive_dry_days: int = 0
    data_source: str = "open-meteo"


class EnvironmentalStressItem(BaseModel):
    stress_type: str
    label: str
    severity: str
    description: str
    management_advice: str


PlantWeatherWarningReport.model_rebuild()


def _risk_level_label(level: str) -> str:
    return RISK_LABELS.get(level.upper(), level)


def _load_wetness_state() -> dict[str, Any]:
    if not WEATHER_STATE_PATH.exists():
        return {}
    try:
        return json.loads(WEATHER_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_wetness_state(state: dict[str, Any]) -> None:
    WEATHER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEATHER_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def estimate_leaf_wetness_hours(
    station_key: str,
    humidity: float,
    rainfall_24h: float,
    *,
    now: datetime | None = None,
) -> float:
    """
    無葉面感測器時的 Fallback：
    - humidity >= 92% 且 rainfall_24h > 0：每小時累加 1
    - humidity < 70%：清零
    """
    now = now or datetime.now(timezone.utc)
    state = _load_wetness_state()
    entry = state.get(station_key, {})
    prev_hours = float(entry.get("leaf_wetness_hours", 0.0))
    last_ts = entry.get("updated_at")

    if humidity < 70.0:
        hours = 0.0
    elif humidity >= 92.0 and rainfall_24h > 0:
        elapsed_hours = 1.0
        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed_hours = max(1.0, (now - last_dt).total_seconds() / 3600.0)
            except ValueError:
                elapsed_hours = 1.0
        hours = min(prev_hours + elapsed_hours, 24.0)
    elif humidity >= 85.0:
        hours = min(prev_hours + 0.5, 12.0)
    else:
        hours = max(prev_hours - 0.5, 0.0)

    state[station_key] = {
        "leaf_wetness_hours": round(hours, 1),
        "updated_at": now.isoformat(),
        "humidity": humidity,
        "rainfall_24h": rainfall_24h,
    }
    _save_wetness_state(state)
    return round(hours, 1)


def format_weather_context_for_gemini(report: PlantWeatherWarningReport) -> str:
    """將微氣象與7天環境摘要轉為 Gemini 診斷上下文。"""
    w = report.current_weather
    lines = [
        "【田間環境上下文（含過去7天天氣）】",
        f"作物：{report.crop_name}",
        f"目前：溫度 {w.temperature}°C、濕度 {w.humidity}%、24h 雨量 {w.rainfall_24h} mm",
        f"葉面連續濕潤約 {w.leaf_wetness_hours} 小時",
    ]
    if report.summary_7d and report.summary_7d.days:
        s = report.summary_7d
        lines.extend(
            [
                f"過去7天平均溫度 {s.avg_temperature}°C、平均濕度 {s.avg_humidity}%",
                f"7天總雨量 {s.total_precipitation_mm} mm",
                f"連續下雨 {s.consecutive_rain_days} 天、連續高溫 {s.consecutive_hot_days} 天、偏乾燥 {s.consecutive_dry_days} 天",
            ]
        )
    for item in report.environmental_stress:
        lines.append(f"- 環境壓力【{item.label}】{item.description}。改善：{item.management_advice}")
    for item in report.risk_assessments:
        lines.append(
            f"- 病害風險 {item.disease_name}：{_risk_level_label(item.risk_level)} — {item.trigger_reason}"
        )
    lines.append(
        "請結合上述環境條件鑑別：區分病害/蟲害與生理障礙（如連續下雨、積水缺氧、連續高溫、過乾）。"
        "若症狀可能由環境造成，請在診斷與建議中說明，並給改善田間環境的具體做法。"
    )
    return "\n".join(lines)


def _max_consecutive_streak(values: list[bool]) -> int:
    best = current = 0
    for flag in values:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def assess_environmental_stress(summary: WeatherSummary7d) -> list[EnvironmentalStressItem]:
    items: list[EnvironmentalStressItem] = []
    if not summary.days:
        return items

    if summary.consecutive_rain_days >= 3:
        sev = "HIGH" if summary.consecutive_rain_days >= 5 else "MEDIUM"
        items.append(
            EnvironmentalStressItem(
                stress_type="continuous_rain",
                label="連續下雨",
                severity=sev,
                description=f"過去7天有 {summary.consecutive_rain_days} 天降雨（總雨量 {summary.total_precipitation_mm} mm）",
                management_advice="加強排水溝、避免積水；雨後通風降濕；注意真菌與細菌性病害，必要時預防性保護。",
            )
        )
    if summary.consecutive_hot_days >= 3:
        sev = "HIGH" if summary.consecutive_hot_days >= 5 else "MEDIUM"
        items.append(
            EnvironmentalStressItem(
                stress_type="continuous_heat",
                label="連續高溫",
                severity=sev,
                description=f"過去7天有 {summary.consecutive_hot_days} 天最高溫 ≥ 32°C",
                management_advice="早晚澆水降溫、搭遮陰網；避免中午施肥或修剪；注意日灼、熱害與乾燥型蟲害（如葉蟎）。",
            )
        )
    if summary.avg_humidity >= 88.0:
        items.append(
            EnvironmentalStressItem(
                stress_type="too_humid",
                label="環境太潮濕",
                severity="HIGH" if summary.avg_humidity >= 92.0 else "MEDIUM",
                description=f"7天平均相對濕度 {summary.avg_humidity}%",
                management_advice="增加通風、適度修剪下位葉；避免傍晚澆水；高濕易誘發白粉病、晚疫病、細菌性溃疡。",
            )
        )
    if summary.consecutive_dry_days >= 4 or summary.avg_humidity <= 58.0:
        items.append(
            EnvironmentalStressItem(
                stress_type="too_dry",
                label="環境太乾燥",
                severity="MEDIUM" if summary.avg_humidity > 50 else "HIGH",
                description=(
                    f"7天平均濕度 {summary.avg_humidity}%，"
                    f"偏乾燥天數 {summary.consecutive_dry_days} 天"
                ),
                management_advice="穩定灌溉、地面覆蓋保濕；乾燥易有葉蟎、蚜蟲及缺水性萎蔫（非病害）。",
            )
        )
    return items


async def fetch_weather_summary_7d(lat: float, lon: float) -> WeatherSummary7d:
    """以 Open-Meteo 取得過去7天日資料（免 API Key）。"""
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "past_days": 7,
                    "forecast_days": 0,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean",
                    "timezone": "Asia/Taipei",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return _simulated_weather_summary_7d(lat, lon)

    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []
    humidity = daily.get("relative_humidity_2m_mean") or []

    days: list[DailyWeatherRecord] = []
    for i, date_str in enumerate(dates):
        try:
            tx = float(tmax[i]) if i < len(tmax) and tmax[i] is not None else 25.0
            tn = float(tmin[i]) if i < len(tmin) and tmin[i] is not None else 18.0
            pr = float(precip[i]) if i < len(precip) and precip[i] is not None else 0.0
            hm = float(humidity[i]) if i < len(humidity) and humidity[i] is not None else 70.0
        except (TypeError, ValueError):
            continue
        days.append(
            DailyWeatherRecord(
                date=date_str,
                temp_min=round(tn, 1),
                temp_max=round(tx, 1),
                temp_mean=round((tx + tn) / 2, 1),
                humidity_mean=round(hm, 1),
                precipitation_mm=round(pr, 1),
            )
        )

    if not days:
        return _simulated_weather_summary_7d(lat, lon)

    avg_temp = round(sum(d.temp_mean for d in days) / len(days), 1)
    avg_hum = round(sum(d.humidity_mean for d in days) / len(days), 1)
    total_rain = round(sum(d.precipitation_mm for d in days), 1)
    rain_flags = [d.precipitation_mm >= 1.0 for d in days]
    hot_flags = [d.temp_max >= 32.0 for d in days]
    dry_flags = [d.precipitation_mm < 0.5 and d.humidity_mean < 62.0 for d in days]

    return WeatherSummary7d(
        days=days,
        avg_temperature=avg_temp,
        avg_humidity=avg_hum,
        total_precipitation_mm=total_rain,
        consecutive_rain_days=_max_consecutive_streak(rain_flags),
        consecutive_hot_days=_max_consecutive_streak(hot_flags),
        consecutive_dry_days=_max_consecutive_streak(dry_flags),
        data_source="open-meteo",
    )


def _simulated_weather_summary_7d(lat: float, lon: float) -> WeatherSummary7d:
    """無法連線時的示意資料。"""
    seed = int(abs(lat * 100) + abs(lon * 100)) % 5
    days = [
        DailyWeatherRecord(
            date=f"D{i}",
            temp_min=20 + seed,
            temp_max=28 + seed,
            temp_mean=24 + seed,
            humidity_mean=75 + seed * 2,
            precipitation_mm=5.0 if i % 2 == 0 else 0.5,
        )
        for i in range(7)
    ]
    return WeatherSummary7d(
        days=days,
        avg_temperature=24 + seed,
        avg_humidity=80 + seed * 2,
        total_precipitation_mm=22.0,
        consecutive_rain_days=2,
        consecutive_hot_days=1,
        consecutive_dry_days=1,
        data_source="simulation",
    )


class AgriWeatherAIEngine:
    def __init__(self) -> None:
        self.cwa_api_key = os.getenv("CWA_API_KEY", "").strip()
        self.cwa_base_url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

    def _station_key(self, lat: float, lon: float) -> str:
        return f"loc_{lat:.3f}_{lon:.3f}"

    async def fetch_current_weather_by_location(self, lat: float, lon: float) -> MicroWeatherData:
        station_key = self._station_key(lat, lon)
        data_source = "simulation"
        temperature = 21.5
        humidity = 94.0
        rainfall_24h = 35.2
        forecast_rain_prob = 0.85

        if self.cwa_api_key:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    url = f"{self.cwa_base_url}/O-A0001-001"
                    response = await client.get(
                        url,
                        params={"Authorization": self.cwa_api_key, "format": "JSON"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    records = payload.get("records", {}).get("Station", [])
                    if records:
                        nearest = records[0]
                        temperature = float(nearest.get("WeatherElement", {}).get("AirTemperature", temperature))
                        humidity = float(nearest.get("WeatherElement", {}).get("RelativeHumidity", humidity))
                        rainfall_24h = float(
                            nearest.get("WeatherElement", {}).get("Now", {}).get("Precipitation", rainfall_24h)
                        )
                        station_key = nearest.get("StationId", station_key)
                        data_source = "cwa"
            except Exception:
                pass

        leaf_wetness_hours = estimate_leaf_wetness_hours(station_key, humidity, rainfall_24h)

        return MicroWeatherData(
            station_id=station_key,
            temperature=temperature,
            humidity=humidity,
            rainfall_24h=rainfall_24h,
            leaf_wetness_hours=leaf_wetness_hours,
            forecast_rain_prob=forecast_rain_prob,
            data_source=data_source,
        )

    def _assess_tomato_risks(self, w: MicroWeatherData) -> list[DiseaseRiskAssessment]:
        assessments: list[DiseaseRiskAssessment] = []
        score = 0.0
        if 15.0 <= w.temperature <= 23.0:
            score += 0.4
        if w.humidity >= 90.0:
            score += 0.3
        if w.leaf_wetness_hours >= 8.0:
            score += 0.3

        if score >= 0.8:
            level = "HIGH"
            hint = (
                "【緊急】請立刻啟動設施雨遮，停止修剪以防傷口感染。"
                "雨前或發病初期可施用亞磷酸二氫鉀 1000 倍液進行系統性免疫誘導。"
            )
            reason = (
                f"溫度 {w.temperature}°C 處於菌絲暴發區，相對濕度 {w.humidity}%，"
                f"葉面連續濕潤 {w.leaf_wetness_hours} 小時，極度吻合晚疫病孢子侵染條件。"
            )
        elif score >= 0.5:
            level = "MEDIUM"
            hint = "加強下位葉打葉與通風，密切注意天氣預報。"
            reason = "環境濕度偏高，溫度接近晚疫病發病臨界點。"
        else:
            return assessments

        assessments.append(
            DiseaseRiskAssessment(
                disease_id="tomato_late_blight",
                disease_name="番茄晚疫病",
                risk_level=level,
                risk_level_label=_risk_level_label(level),
                risk_score=round(score, 2),
                trigger_reason=reason,
                prevention_hint=hint,
            )
        )
        return assessments

    def _assess_strawberry_risks(self, w: MicroWeatherData) -> list[DiseaseRiskAssessment]:
        assessments: list[DiseaseRiskAssessment] = []
        score = 0.0
        if w.temperature >= 28.0:
            score += 0.5
        if w.humidity <= 65.0:
            score += 0.5

        if score < 0.8:
            return assessments

        level = "HIGH"
        assessments.append(
            DiseaseRiskAssessment(
                disease_id="strawberry_two_spotted_mite",
                disease_name="二點葉蟎 (紅蜘蛛)",
                risk_level=level,
                risk_level_label=_risk_level_label(level),
                risk_score=round(score, 2),
                trigger_reason=(
                    f"田區高溫 ({w.temperature}°C) 且乾燥 (相對濕度 {w.humidity}%)，"
                    "葉蟎繁殖週期可縮短至 5–7 天，易爆發流行。"
                ),
                prevention_hint=(
                    "【物理防治】清晨或傍晚以微霧噴水沖刷蟎體並提高濕度；"
                    "或提早釋放智利捕植蟎進行生物防治。"
                ),
            )
        )
        return assessments

    def _assess_citrus_risks(self, w: MicroWeatherData) -> list[DiseaseRiskAssessment]:
        """柑橘專用：高濕 + 葉面濕潤易發溃疡/脂點病。"""
        assessments: list[DiseaseRiskAssessment] = []
        score = 0.0
        if w.humidity >= 88.0:
            score += 0.35
        if w.leaf_wetness_hours >= 6.0:
            score += 0.35
        if w.rainfall_24h >= 10.0:
            score += 0.3

        if score < 0.7:
            return assessments

        level = "HIGH" if score >= 0.85 else "MEDIUM"
        assessments.append(
            DiseaseRiskAssessment(
                disease_id="citrus_canker",
                disease_name="柑橘溃疡病",
                risk_level=level,
                risk_level_label=_risk_level_label(level),
                risk_score=round(score, 2),
                trigger_reason=(
                    f"連續高濕（{w.humidity}%）且葉面濕潤 {w.leaf_wetness_hours} 小時，"
                    f"24h 雨量 {w.rainfall_24h} mm，有利細菌性溃疡病蔓延。"
                ),
                prevention_hint="雨後立即噴銅劑保護，避免風雨期修剪；加強排水與通風。",
            )
        )
        return assessments

    async def evaluate_farm_health_risk(
        self, crop_name: str, lat: float, lon: float
    ) -> PlantWeatherWarningReport:
        weather_data, summary_7d = await asyncio.gather(
            self.fetch_current_weather_by_location(lat, lon),
            fetch_weather_summary_7d(lat, lon),
        )
        environmental_stress = assess_environmental_stress(summary_7d)
        normalized = crop_name.strip()
        risk_list: list[DiseaseRiskAssessment] = []

        lower = normalized.lower()
        if "番茄" in normalized or "tomato" in lower:
            risk_list = self._assess_tomato_risks(weather_data)
        elif "草莓" in normalized or "strawberry" in lower:
            risk_list = self._assess_strawberry_risks(weather_data)
        elif "柑橘" in normalized or "citrus" in lower or "柳橙" in normalized:
            risk_list = self._assess_citrus_risks(weather_data)

        if not risk_list:
            default_level = (
                "HIGH"
                if weather_data.humidity > 90.0 and weather_data.leaf_wetness_hours > 6
                else "LOW"
            )
            risk_list.append(
                DiseaseRiskAssessment(
                    disease_id="generic_fungal",
                    disease_name="通用真菌性病害預警",
                    risk_level=default_level,
                    risk_level_label=_risk_level_label(default_level),
                    risk_score=0.6 if default_level == "HIGH" else 0.2,
                    trigger_reason=(
                        f"目前相對濕度 {weather_data.humidity}%，"
                        "高濕環境有利多數真菌孢子萌發。"
                    ),
                    prevention_hint="保持通風，落實枯枝落葉清園。",
                )
            )

        return PlantWeatherWarningReport(
            crop_name=crop_name,
            current_weather=weather_data,
            risk_assessments=risk_list,
            summary_7d=summary_7d,
            environmental_stress=environmental_stress,
        )
