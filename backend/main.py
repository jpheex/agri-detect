import mimetypes
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.database import (
    correct_identification,
    export_training_manifest,
    get_knowledge_stats,
    get_verification_stats,
    init_db,
    list_identifications,
    list_knowledge_entries,
    list_knowledge_index,
    list_training_samples,
    save_identification,
    save_training_sample,
    verify_identification,
)
from backend.config import BASE_DIR, DATA_DIR
from backend.crop_disease_identifier import (
    CropDiseaseIdentifierError,
    identify_crop_disease_for_app,
    is_configured,
)
from backend.knowledge import (
    image_vector,
    predict,
    sync_manual_correction,
    sync_training_sample,
    sync_verified_identification,
    vector_to_json,
)

UPLOAD_DIR = DATA_DIR / "uploads"
TRAINING_DIR = DATA_DIR / "training"
STATIC_DIR = BASE_DIR / "frontend"

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# 部署環境可能回傳錯誤的 .js MIME type（例如 text/plain），這裡強制指定
mimetypes.add_type("application/javascript", ".js", True)
mimetypes.add_type("text/css", ".css", True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="農業病蟲害辨識系統", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _save_upload(file: UploadFile, folder: Path) -> Path:
    suffix = Path(file.filename or "image.jpg").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="僅支援 jpg、jpeg、png、webp")

    target = folder / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return target


@app.get("/api/health")
async def health():
    return {"status": "ok", "gemini": is_configured()}


async def _run_identify(saved_paths: list[Path], user_notes: str = "") -> dict:
    index_rows = await list_knowledge_index()
    knowledge_entries = await list_knowledge_entries()

    if is_configured():
        try:
            result = await identify_crop_disease_for_app(
                [str(path) for path in saved_paths],
                user_notes=user_notes or None,
                knowledge_entries=knowledge_entries,
            )
            return result
        except CropDiseaseIdentifierError:
            pass

    # 後備：本機知識庫比對（僅用第一張影像）
    return await predict(saved_paths[0], index_rows, knowledge_entries)


@app.post("/api/identify")
async def identify(
    file: UploadFile | None = File(None),
    files: list[UploadFile] = File(default=[]),
    user_notes: str = Form(""),
):
    uploads = files if files else ([file] if file else [])
    if not uploads:
        raise HTTPException(status_code=400, detail="請上傳至少一張照片")

    saved_paths = [_save_upload(item, UPLOAD_DIR) for item in uploads]
    result = await _run_identify(saved_paths, user_notes=user_notes.strip())
    primary = saved_paths[0]
    record_id = await save_identification(
        {
            "image_path": str(primary.relative_to(BASE_DIR)),
            **{k: v for k, v in result.items() if k in {
                "crop", "issue_type", "issue_name", "confidence", "treatment", "prevention"
            }},
        }
    )
    image_urls = [f"/files/{path.relative_to(DATA_DIR)}" for path in saved_paths]
    return {
        "id": record_id,
        "image_url": image_urls[0],
        "image_urls": image_urls,
        **result,
    }


@app.get("/api/identifications")
async def identifications(limit: int = 50):
    items = await list_identifications(limit=limit)
    for item in items:
        item["image_url"] = f"/files/{Path(item['image_path']).relative_to(DATA_DIR)}"
    return items


@app.post("/api/verify/{record_id}")
async def verify(record_id: int, is_correct: bool = Form(...)):
    ok = await verify_identification(record_id, is_correct)
    if not ok:
        raise HTTPException(status_code=404, detail="找不到紀錄")
    if is_correct:
        await sync_verified_identification(record_id, BASE_DIR)
    return {"success": True}


@app.post("/api/correct/{record_id}")
async def correct(
    record_id: int,
    crop: str = Form(...),
    issue_type: str = Form(...),
    issue_name: str = Form(...),
    treatment: str = Form(""),
    prevention: str = Form(""),
):
    crop = crop.strip()
    issue_type = issue_type.strip()
    issue_name = issue_name.strip()
    treatment = treatment.strip()
    prevention = prevention.strip()

    if not crop or not issue_name:
        raise HTTPException(status_code=400, detail="品種與問題名稱不可為空")

    ok = await correct_identification(
        record_id,
        {
            "crop": crop,
            "issue_type": issue_type,
            "issue_name": issue_name,
            "treatment": treatment or "請依實際狀況處理。",
            "prevention": prevention or "維持良好栽培管理。",
            "confidence": 0.95,
        },
    )
    if not ok:
        raise HTTPException(status_code=404, detail="找不到紀錄")

    await sync_manual_correction(
        record_id,
        BASE_DIR,
        crop,
        issue_type,
        issue_name,
        treatment,
        prevention,
    )
    meta = await get_knowledge_stats()
    return {
        "success": True,
        "message": f"已更正並同步知識庫（共 {meta['entries']} 類、{meta['indexed_images']} 張參考圖）",
        "crop": crop,
        "issue_type": issue_type,
        "issue_name": issue_name,
        "treatment": treatment or "請依實際狀況處理。",
        "prevention": prevention or "維持良好栽培管理。",
        "confidence": 0.95,
        "source": "手動更正",
        **meta,
    }


@app.get("/api/stats")
async def stats():
    base = await get_verification_stats()
    knowledge = await get_knowledge_stats()
    return {**base, **knowledge}


@app.get("/api/knowledge")
async def knowledge(limit: int = 100):
    entries = await list_knowledge_entries(limit=limit)
    meta = await get_knowledge_stats()
    return {"entries": entries, **meta}


@app.post("/api/training")
async def add_training_sample(
    file: UploadFile = File(...),
    crop: str = Form(...),
    issue_type: str = Form(...),
    issue_name: str = Form(...),
    notes: str = Form(""),
    treatment: str = Form(""),
    prevention: str = Form(""),
):
    saved = _save_upload(file, TRAINING_DIR)
    vector = vector_to_json(image_vector(saved))
    record_id = await save_training_sample(
        {
            "image_path": str(saved.relative_to(BASE_DIR)),
            "crop": crop.strip(),
            "issue_type": issue_type.strip(),
            "issue_name": issue_name.strip(),
            "notes": notes.strip(),
            "treatment": treatment.strip(),
            "prevention": prevention.strip(),
            "image_vector": vector,
        }
    )
    await sync_training_sample(
        sample_id=record_id,
        image_path=saved,
        crop=crop.strip(),
        issue_type=issue_type.strip(),
        issue_name=issue_name.strip(),
        treatment=treatment.strip(),
        prevention=prevention.strip(),
    )
    meta = await get_knowledge_stats()
    return {
        "id": record_id,
        "image_url": f"/files/{saved.relative_to(DATA_DIR)}",
        "message": f"已同步至辨識知識庫（共 {meta['entries']} 類、{meta['indexed_images']} 張參考圖）",
        **meta,
    }


@app.get("/api/training")
async def training_samples(limit: int = 100):
    items = await list_training_samples(limit=limit)
    for item in items:
        item["image_url"] = f"/files/{Path(item['image_path']).relative_to(DATA_DIR)}"
    return items


@app.get("/api/training/export")
async def training_export():
    manifest = await export_training_manifest()
    export_path = DATA_DIR / "training_manifest.json"
    export_path.write_text(manifest, encoding="utf-8")
    return FileResponse(
        export_path,
        media_type="application/json",
        filename="training_manifest.json",
    )


@app.get("/files/{folder}/{filename}")
async def serve_file(folder: str, filename: str):
    target = DATA_DIR / folder / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="檔案不存在")
    return FileResponse(target)


@app.get("/")
async def frontend_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="找不到前端 index.html")
    return FileResponse(index_path)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
