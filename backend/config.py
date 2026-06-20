import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))

_VERSION_PATTERN = re.compile(r"^\d+\.\d{3}$")


def _normalize_version(raw: str) -> str:
    """正規化為 major.xxx 格式（例如 1.005）。"""
    text = raw.strip().lstrip("vV").strip()
    if _VERSION_PATTERN.match(text):
        return text
    # 允許 1.5 -> 1.005
    parts = text.split(".")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0])}.{int(parts[1]):03d}"
    return text


def _read_app_version() -> str:
    env = os.getenv("APP_VERSION", "").strip()
    if env:
        return _normalize_version(env)

    version_file = BASE_DIR / "VERSION"
    if version_file.exists():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return _normalize_version(text)

    return "1.000"


def format_version_label(version: str | None = None) -> str:
    """顯示用標籤：v x.xxx"""
    value = _normalize_version(version or APP_VERSION)
    return f"v {value}"


APP_VERSION = _read_app_version()
