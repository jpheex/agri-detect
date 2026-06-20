"""微氣象主動預警定時任務（預設每 3 小時）。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.agri_weather_ai import AgriWeatherAIEngine
from backend.database import list_farm_monitors, update_farm_monitor_alert
from backend.push_notifier import push_configured, send_push_message

logger = logging.getLogger(__name__)

ALERT_COOLDOWN_HOURS = int(os.getenv("WEATHER_ALERT_COOLDOWN_HOURS", "6"))


def _alert_on_cooldown(last_alert_at: str | None) -> bool:
    if not last_alert_at:
        return False
    try:
        last_dt = datetime.fromisoformat(last_alert_at.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_dt < timedelta(hours=ALERT_COOLDOWN_HOURS)
    except ValueError:
        return False


async def run_weather_alert_job() -> dict[str, int]:
    """掃描所有監測點，對 HIGH 風險發送推播。"""
    monitors = await list_farm_monitors()
    engine = AgriWeatherAIEngine()
    stats = {"checked": 0, "high": 0, "pushed": 0, "skipped": 0}

    for monitor in monitors:
        if not monitor.get("push_enabled"):
            stats["skipped"] += 1
            continue

        stats["checked"] += 1
        report = await engine.evaluate_farm_health_risk(
            monitor["crop_name"],
            float(monitor["latitude"]),
            float(monitor["longitude"]),
        )
        high_items = [item for item in report.risk_assessments if item.risk_level == "HIGH"]
        if not high_items:
            continue

        stats["high"] += 1
        top = high_items[0]
        if _alert_on_cooldown(monitor.get("last_alert_at")):
            if monitor.get("last_high_disease") == top.disease_name:
                stats["skipped"] += 1
                continue

        label = monitor.get("label") or monitor["crop_name"]
        w = report.current_weather
        body = (
            f"監測點：{label}\n"
            f"作物：{monitor['crop_name']}\n"
            f"⚠️ {top.disease_name} — {top.risk_level_label}\n"
            f"{top.trigger_reason}\n"
            f"建議：{top.prevention_hint}\n"
            f"（溫度 {w.temperature}°C · 濕度 {w.humidity}% · 葉面濕潤 {w.leaf_wetness_hours}h）"
        )

        if not push_configured():
            logger.info("微氣象 HIGH 預警（未設定推播）：%s — %s", label, top.disease_name)
            continue

        sent = await send_push_message("🌾 農業病蟲害微氣象預警", body, extra={"monitor_id": monitor["id"]})
        if sent:
            await update_farm_monitor_alert(monitor["id"], top.disease_name)
            stats["pushed"] += 1

    return stats


def start_weather_scheduler() -> AsyncIOScheduler | None:
    if os.getenv("WEATHER_CRON_ENABLED", "true").lower() in {"0", "false", "no"}:
        return None

    hours = max(1, int(os.getenv("WEATHER_CRON_HOURS", "3")))
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(
        run_weather_alert_job,
        "interval",
        hours=hours,
        id="weather_alert_job",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("微氣象定時預警已啟動（每 %s 小時）", hours)
    return scheduler
