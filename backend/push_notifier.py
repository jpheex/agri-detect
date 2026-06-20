"""推播通知：LINE Notify 或自訂 Webhook。"""

from __future__ import annotations

import os
from typing import Any

import httpx


async def send_push_message(title: str, body: str, extra: dict[str, Any] | None = None) -> bool:
    line_token = os.getenv("LINE_NOTIFY_TOKEN", "").strip()
    webhook_url = os.getenv("PUSH_WEBHOOK_URL", "").strip()
    message = f"{title}\n{body}".strip()

    if line_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://notify-api.line.me/api/notify",
                    headers={"Authorization": f"Bearer {line_token}"},
                    data={"message": message},
                )
                return response.status_code == 200
        except Exception:
            return False

    if webhook_url:
        payload = {"title": title, "body": body, "message": message, **(extra or {})}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)
                return 200 <= response.status_code < 300
        except Exception:
            return False

    return False


def push_configured() -> bool:
    return bool(os.getenv("LINE_NOTIFY_TOKEN", "").strip() or os.getenv("PUSH_WEBHOOK_URL", "").strip())
