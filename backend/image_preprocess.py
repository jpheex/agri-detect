"""
影像前處理：在送往 Gemini 前等比例縮放，降低 Token 消耗與延遲。
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.config import DATA_DIR

PREPROCESS_DIR = DATA_DIR / "preprocessed"
DEFAULT_MAX_EDGE = int(__import__("os").getenv("GEMINI_IMAGE_MAX_EDGE", "1024"))
JPEG_QUALITY = int(__import__("os").getenv("GEMINI_JPEG_QUALITY", "85"))


class ImagePreprocessError(Exception):
    """影像前處理失敗。"""


def resize_image_for_api(
    source_path: Path,
    max_edge: int = DEFAULT_MAX_EDGE,
    output_dir: Path | None = None,
) -> Path:
    """
    將影像等比例縮小至最長邊不超過 max_edge，並輸出為 JPEG。

    Args:
        source_path: 原始影像路徑
        max_edge: 最長邊像素上限（預設 1024）
        output_dir: 輸出目錄，預設使用 data/preprocessed

    Returns:
        前處理後的 JPEG 路徑
    """
    target_dir = output_dir or PREPROCESS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            longest = max(width, height)
            if longest > max_edge:
                scale = max_edge / longest
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            output_path = target_dir / f"{uuid.uuid4().hex}.jpg"
            img.save(output_path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return output_path
    except UnidentifiedImageError as exc:
        raise ImagePreprocessError(f"無法讀取影像：{source_path}") from exc
    except OSError as exc:
        raise ImagePreprocessError(f"影像處理失敗：{source_path}") from exc


def prepare_images_for_api(
    image_paths: list[Path],
    max_edge: int = DEFAULT_MAX_EDGE,
) -> list[Path]:
    """批次前處理多張影像。"""
    return [resize_image_for_api(path, max_edge=max_edge) for path in image_paths]


def image_to_jpeg_bytes(source_path: Path, max_edge: int = DEFAULT_MAX_EDGE) -> bytes:
    """將影像縮放後直接回傳 JPEG bytes（不寫入磁碟）。"""
    try:
        with Image.open(source_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            longest = max(width, height)
            if longest > max_edge:
                scale = max_edge / longest
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImagePreprocessError(f"影像處理失敗：{source_path}") from exc
