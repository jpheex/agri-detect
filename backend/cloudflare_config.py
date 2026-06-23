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
    from backend.db_connection import use_d1

    return use_d1() and r2_enabled()


def cloudflare_env_status() -> dict[str, bool]:
    """僅回報變數是否存在（不洩漏內容）。"""
    keys = [
        "CF_ACCOUNT_ID",
        "CF_API_TOKEN",
        "CF_D1_DATABASE_ID",
        "R2_BUCKET_NAME",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_ENDPOINT",
    ]
    return {key: bool(os.getenv(key, "").strip()) for key in keys}
