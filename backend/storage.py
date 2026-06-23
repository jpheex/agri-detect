"""偵測資料目錄是否為持久化儲存。"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from backend.cloudflare_config import cloudflare_storage_enabled
from backend.config import DATA_DIR

MARKER = DATA_DIR / ".storage_persist_marker"

EPHEMERAL_WARNING = (
    "目前伺服器使用暫時性磁碟：重新部署或重啟後，訓練資料、驗收紀錄與上傳照片都會消失。"
    "正式使用請設定 Cloudflare D1 + R2，或見 README「資料持久化」。"
)


def _is_ephemeral_configured() -> bool:
    return os.getenv("STORAGE_EPHEMERAL", "").strip().lower() in {"1", "true", "yes"}


def assess_storage_persistence() -> dict:
    if cloudflare_storage_enabled():
        return {
            "persistent": True,
            "backend": "cloudflare_d1_r2",
            "data_dir": str(DATA_DIR),
        }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    if _is_ephemeral_configured():
        return {
            "persistent": False,
            "data_dir": str(DATA_DIR),
            "warning": EPHEMERAL_WARNING,
            "on_render": os.getenv("RENDER", "").lower() == "true",
        }

    if MARKER.exists():
        try:
            since = MARKER.read_text(encoding="utf-8").strip()
        except OSError:
            since = now
        try:
            MARKER.write_text(now, encoding="utf-8")
        except OSError:
            pass
        return {
            "persistent": True,
            "data_dir": str(DATA_DIR),
            "marker_since": since or now,
        }

    try:
        MARKER.write_text(now, encoding="utf-8")
    except OSError:
        pass
    return {
        "persistent": False,
        "data_dir": str(DATA_DIR),
        "marker_since": now,
        "warning": (
            "首次啟動，尚無法確認磁碟是否持久化。"
            "若使用 Render 免費方案，請假設資料會在重啟後遺失。"
        ),
    }
