import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))


def _read_app_version() -> str:
    for key in ("RENDER_GIT_COMMIT", "APP_VERSION"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:12]
    version_file = BASE_DIR / "VERSION"
    if version_file.exists():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "dev"


APP_VERSION = _read_app_version()
