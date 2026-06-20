"""
反向地理編碼：經緯度 → 繁中地名（供監測點名稱自動填入）。
"""

from __future__ import annotations

import httpx

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "AgriDetect/1.0 (agricultural weather monitor)"


def _pick_address_label(address: dict) -> str:
    """從 Nominatim address 物件組合繁中可讀地名。"""
    parts: list[str] = []
    for key in (
        "city",
        "town",
        "village",
        "suburb",
        "neighbourhood",
        "county",
        "state",
        "country",
    ):
        value = address.get(key)
        if value and value not in parts:
            parts.append(str(value))
    return " · ".join(parts[:4]) if parts else ""


async def reverse_geocode_label(latitude: float, longitude: float) -> dict[str, str | float]:
    """
    依 GPS 經緯度取得地名標籤。

    失敗時回傳座標格式標籤，確保前端一定有可填入的值。
    """
    coord_label = f"GPS {latitude:.4f}°N, {longitude:.4f}°E"
    fallback = {
        "label": coord_label,
        "latitude": latitude,
        "longitude": longitude,
        "source": "coordinates",
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                NOMINATIM_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "json",
                    "accept-language": "zh-TW,zh",
                    "zoom": 14,
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return fallback

    address = payload.get("address") or {}
    label = _pick_address_label(address)
    if not label:
        display = (payload.get("display_name") or "").split(",")[0].strip()
        label = display or coord_label

    return {
        "label": label,
        "latitude": latitude,
        "longitude": longitude,
        "source": "nominatim",
        "display_name": payload.get("display_name", label),
    }
