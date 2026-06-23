"""Cloudflare D1 / R2 設定。"""

from __future__ import annotations

import os


def d1_enabled() -> bool:
    return bool(
        os.getenv("CF_ACCOUNT_ID", "").strip()
        and os.getenv("CF_API_TOKEN", "").strip()
        and os.getenv("CF_D1_DATABASE_ID", "").strip()
    )


def r2_enabled() -> bool:
    return bool(
        os.getenv("R2_BUCKET_NAME", "").strip()
        and os.getenv("R2_ACCESS_KEY_ID", "").strip()
        and os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
        and os.getenv("R2_ENDPOINT", "").strip()
    )


def cloudflare_storage_enabled() -> bool:
    return d1_enabled() and r2_enabled()
