"""上傳影像：本機 data/ 或 Cloudflare R2。"""

from __future__ import annotations

import mimetypes
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.cloudflare_config import r2_enabled
from backend.config import BASE_DIR, DATA_DIR
from backend.r2_storage import get_object, put_object

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def to_r2_key(image_path: str) -> str:
    """data/uploads/foo.jpg -> uploads/foo.jpg"""
    path = Path(image_path.replace("\\", "/"))
    parts = path.parts
    if len(parts) >= 2 and parts[0] == "data":
        return "/".join(parts[1:])
    return path.as_posix()


def to_db_image_path(folder: str, filename: str) -> str:
    return f"data/{folder}/{filename}"


def _guess_content_type(filename: str) -> str:
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


async def save_upload(file: UploadFile, folder: str) -> Path:
    """儲存上傳檔，回傳可供 AI 讀取的本機 Path。"""
    suffix = Path(file.filename or "image.jpg").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="僅支援 jpg、jpeg、png、webp")

    filename = f"{uuid.uuid4().hex}{suffix}"
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="空檔案")

    if r2_enabled():
        key = f"{folder}/{filename}"
        await put_object(key, body, _guess_content_type(filename))
        temp = Path(tempfile.gettempdir()) / filename
        temp.write_bytes(body)
        return temp

    target_dir = DATA_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    target.write_bytes(body)
    return target


def db_path_for_saved(folder: str, saved_path: Path) -> str:
    filename = saved_path.name
    return to_db_image_path(folder, filename)


async def read_image_bytes(image_path: str) -> bytes | None:
    local = (BASE_DIR / image_path).resolve()
    if local.exists():
        return local.read_bytes()

    if r2_enabled():
        key = to_r2_key(image_path)
        data = await get_object(key)
        if data is None and "/agri-" in key:
            # 相容舊版：R2 用 uuid 檔名，DB 卻記成 agri-uuid
            legacy_key = key.replace("/agri-", "/", 1)
            data = await get_object(legacy_key)
        return data
    return None


async def materialize_image(image_path: str) -> Path | None:
    """下載為本機暫存檔（供 Pillow / Gemini 使用）。"""
    local = (BASE_DIR / image_path).resolve()
    if local.exists():
        return local

    data = await read_image_bytes(image_path)
    if not data:
        return None

    suffix = Path(image_path).suffix or ".jpg"
    temp = Path(tempfile.gettempdir()) / f"agri-mat-{uuid.uuid4().hex}{suffix}"
    temp.write_bytes(data)
    return temp


async def read_file_response(folder: str, filename: str) -> tuple[bytes, str] | None:
    db_path = to_db_image_path(folder, filename)
    data = await read_image_bytes(db_path)
    if data is None:
        return None
    return data, _guess_content_type(filename)
