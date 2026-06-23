import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from io import BytesIO

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.database import (
    correct_identification,
    delete_farm_monitor,
    export_training_manifest,
    get_knowledge_stats,
    get_verification_stats,
    init_db,
    list_farm_monitors,
    list_identifications,
    list_knowledge_entries,
    list_knowledge_index,
    list_training_samples,
    save_farm_monitor,
    save_identification,
    save_training_sample,
    verify_identification,
)
from backend.geocode import reverse_geocode_label
from backend.config import APP_VERSION, BASE_DIR, DATA_DIR, format_version_label
from backend.agri_ai_orchestrator import evaluate_weather_risk, run_comprehensive_diagnostic
from backend.agri_weather_ai import AgriWeatherAIEngine, format_weather_context_for_gemini
from backend.plant_health_analyzer import (
    PlantHealthAnalyzerError,
    analyze_plant_health_for_app,
)
from backend.crop_disease_identifier import (
    CropDiseaseIdentifierError,
    is_configured,
)
from backend.disease_management_kb import MOCK_KNOWLEDGE, get_management_protocol
from backend.offline_db import init_offline_db
from backend.offline_router import router as offline_router
from backend.weather_scheduler import run_weather_alert_job, start_weather_scheduler
from backend.push_notifier import push_configured
from backend.storage import assess_storage_persistence
from backend.cloudflare_config import (
    cloudflare_env_status,
    cloudflare_storage_enabled,
    d1_enabled,
    r2_enabled,
)
from backend.db_connection import use_d1
from backend.file_storage import db_path_for_saved, read_file_response, save_upload as store_upload
from backend.knowledge import (
    image_vector,
    predict,
    sync_manual_correction,
    sync_training_sample,
    sync_verified_identification,
    vector_to_json,
)

UPLOAD_FOLDER = "uploads"
TRAINING_FOLDER = "training"
STATIC_DIR = BASE_DIR / "frontend"


def _image_url(image_path: str) -> str:
    path = Path(image_path)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    rel = path.relative_to(DATA_DIR.resolve())
    return f"/files/{rel.as_posix()}"

# 部署環境可能回傳錯誤的 .js MIME type（例如 text/plain），這裡強制指定
mimetypes.add_type("application/javascript", ".js", True)
mimetypes.add_type("text/css", ".css", True)
mimetypes.add_type("application/manifest+json", ".webmanifest", True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not r2_enabled():
        (DATA_DIR / UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
        (DATA_DIR / TRAINING_FOLDER).mkdir(parents=True, exist_ok=True)
    await init_db()
    await init_offline_db()
    scheduler = start_weather_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="農業病蟲害辨識系統", lifespan=lifespan)
app.include_router(offline_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_browser_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in {"/", "/sw.js", "/api/version"} or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


async def _save_upload(file: UploadFile, folder: str) -> Path:
    return await store_upload(file, folder)


@app.get("/api/health")
async def health():
    storage = assess_storage_persistence()
    return {
        "status": "ok",
        "gemini": is_configured(),
        "storage": storage,
        "cloudflare": {
            "d1": use_d1(),
            "d1_env": d1_enabled(),
            "r2": r2_enabled(),
            "persistent": cloudflare_storage_enabled(),
            "env_set": cloudflare_env_status(),
        },
    }


@app.get("/api/version")
async def version():
    return {"version": APP_VERSION, "label": format_version_label()}


@app.get("/api/qrcode")
async def qrcode_image(url: str = Query(..., min_length=8, max_length=2048)):
    """產生分享連結 QR Code PNG。"""
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="url 必須為 http 或 https")
    img = qrcode.make(target, box_size=8, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@app.get("/api/geocode/reverse")
async def geocode_reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """依 GPS 經緯度回傳繁中地名（監測點名稱自動填入用）。"""
    return await reverse_geocode_label(lat, lon)


@app.get("/api/weather/risk")
async def weather_risk(
    crop_name: str = Query(..., min_length=1, max_length=100),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """依作物與經緯度評估微氣象病蟲害風險。"""
    return await evaluate_weather_risk(crop_name.strip(), lat, lon)


@app.get("/api/weather/monitors")
async def weather_monitors():
    items = await list_farm_monitors()
    return {"items": items, "push_configured": push_configured()}


@app.post("/api/weather/monitors")
async def create_weather_monitor(
    crop_name: str = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    label: str = Form(""),
):
    crop = crop_name.strip()
    if not crop:
        raise HTTPException(status_code=400, detail="作物名稱不可為空")
    monitor_id = await save_farm_monitor(
        {
            "label": label.strip(),
            "crop_name": crop,
            "latitude": latitude,
            "longitude": longitude,
        }
    )
    return {"id": monitor_id, "message": "已訂閱微氣象主動預警"}


@app.delete("/api/weather/monitors/{monitor_id}")
async def remove_weather_monitor(monitor_id: int):
    ok = await delete_farm_monitor(monitor_id)
    if not ok:
        raise HTTPException(status_code=404, detail="找不到監測點")
    return {"success": True}


@app.post("/api/weather/check-now")
async def weather_check_now():
    """手動觸發一次全監測點掃描（測試/管理用）。"""
    stats = await run_weather_alert_job()
    return {"success": True, "stats": stats, "push_configured": push_configured()}


@app.post("/api/diagnostic/comprehensive")
async def comprehensive_diagnostic(
    crop_name: str = Form(...),
    lat: float = Form(...),
    lon: float = Form(...),
    user_notes: str = Form(""),
    file_leaves: UploadFile | None = File(None),
    file_flowers: UploadFile | None = File(None),
    file_stems: UploadFile | None = File(None),
):
    """三方聯防：微氣象預警 + 影像診斷 + IPM 知識庫。"""
    organ_uploads: list[tuple[str, UploadFile]] = []
    if file_leaves and file_leaves.filename:
        organ_uploads.append(("leaves", file_leaves))
    if file_flowers and file_flowers.filename:
        organ_uploads.append(("flowers", file_flowers))
    if file_stems and file_stems.filename:
        organ_uploads.append(("stems_trunk", file_stems))

    saved_paths: list[Path] = []
    organ_labels: list[str] | None = None
    if organ_uploads:
        saved_paths = [await _save_upload(item, UPLOAD_FOLDER) for _, item in organ_uploads]
        organ_labels = [label for label, _ in organ_uploads]

    knowledge_entries = await list_knowledge_entries()
    payload = await run_comprehensive_diagnostic(
        crop_name=crop_name.strip(),
        lat=lat,
        lon=lon,
        image_paths=[str(p) for p in saved_paths] if saved_paths else None,
        organ_labels=organ_labels,
        user_notes=user_notes.strip() or None,
        knowledge_entries=knowledge_entries,
    )

    if payload.get("visual_ai_diagnostic_report"):
        visual = payload["visual_ai_diagnostic_report"]
        payload["summary"] = {
            "crop": visual.get("crop"),
            "issue_type": visual.get("issue_type"),
            "issue_name": visual.get("issue_name"),
            "confidence": visual.get("confidence"),
        }
    return payload


@app.get("/api/management/lookup")
async def management_lookup(disease_name: str, plant_name: str = ""):
    """依病蟲害名稱查詢 IPM 防治協議（測試/前端擴充用）。"""
    lookup = await get_management_protocol(disease_name, plant_name=plant_name or None)
    return lookup.model_dump()


@app.get("/api/management/catalog")
async def management_catalog():
    """列出知識庫收錄的所有病蟲害條目。"""
    return [
        {
            "target_id": item.target_id,
            "common_name": item.common_name,
            "scientific_name": item.scientific_name,
            "host_plants": item.host_plants,
        }
        for item in MOCK_KNOWLEDGE
    ]


@app.get("/sw.js")
async def service_worker():
    sw_path = STATIC_DIR / "sw.js"
    if not sw_path.exists():
        raise HTTPException(status_code=404, detail="找不到 service worker")
    body = sw_path.read_text(encoding="utf-8").replace("__APP_VERSION__", APP_VERSION)
    return Response(
        body,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


async def _run_identify(
    saved_paths: list[Path],
    organ_labels: list[str] | None = None,
    user_provided_crop: str = "",
    user_notes: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    index_rows = await list_knowledge_index()
    knowledge_entries = await list_knowledge_entries()

    merged_notes = user_notes.strip()
    weather_payload = None
    crop_for_weather = (user_provided_crop or "").strip() or "通用作物"
    if latitude is not None and longitude is not None:
        try:
            engine = AgriWeatherAIEngine()
            weather_report = await engine.evaluate_farm_health_risk(
                crop_for_weather, latitude, longitude
            )
            weather_payload = weather_report.model_dump(mode="json")
            weather_ctx = format_weather_context_for_gemini(weather_report)
            merged_notes = f"{merged_notes}\n\n{weather_ctx}".strip() if merged_notes else weather_ctx
        except Exception:
            pass

    if is_configured():
        try:
            result = await analyze_plant_health_for_app(
                [str(path) for path in saved_paths],
                user_provided_crop=user_provided_crop or None,
                organ_labels=organ_labels,
                user_notes=merged_notes or None,
                knowledge_entries=knowledge_entries,
            )
            if weather_payload:
                result["agri_weather_ai_proactive_warning"] = weather_payload
            return result
        except (PlantHealthAnalyzerError, CropDiseaseIdentifierError):
            pass

    # 後備：本機知識庫比對（僅用第一張影像）
    result = await predict(saved_paths[0], index_rows, knowledge_entries)
    if weather_payload:
        result["agri_weather_ai_proactive_warning"] = weather_payload
    return result


@app.post("/api/identify")
async def identify(
    file: UploadFile | None = File(None),
    files: list[UploadFile] = File(default=[]),
    file_leaves: UploadFile | None = File(None),
    file_flowers: UploadFile | None = File(None),
    file_stems: UploadFile | None = File(None),
    user_provided_crop: str = Form(""),
    user_notes: str = Form(""),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
):
    organ_uploads: list[tuple[str, UploadFile]] = []
    if file_leaves and file_leaves.filename:
        organ_uploads.append(("leaves", file_leaves))
    if file_flowers and file_flowers.filename:
        organ_uploads.append(("flowers", file_flowers))
    if file_stems and file_stems.filename:
        organ_uploads.append(("stems_trunk", file_stems))

    if organ_uploads:
        saved_paths = [await _save_upload(item, UPLOAD_FOLDER) for _, item in organ_uploads]
        organ_labels = [label for label, _ in organ_uploads]
    else:
        uploads = files if files else ([file] if file else [])
        if not uploads:
            raise HTTPException(status_code=400, detail="請至少拍攝或上傳一張照片")
        saved_paths = [await _save_upload(item, UPLOAD_FOLDER) for item in uploads]
        organ_labels = None

    result = await _run_identify(
        saved_paths,
        organ_labels=organ_labels,
        user_provided_crop=user_provided_crop.strip(),
        user_notes=user_notes.strip(),
        latitude=latitude,
        longitude=longitude,
    )
    db_paths = [db_path_for_saved(UPLOAD_FOLDER, path) for path in saved_paths]
    record_id = await save_identification(
        {
            "image_path": db_paths[0],
            **{k: v for k, v in result.items() if k in {
                "crop", "issue_type", "issue_name", "confidence", "treatment", "prevention"
            }},
        }
    )
    image_urls = [_image_url(path) for path in db_paths]
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
        item["image_url"] = _image_url(item["image_path"])
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
    saved = await _save_upload(file, TRAINING_FOLDER)
    db_path = db_path_for_saved(TRAINING_FOLDER, saved)
    vector = vector_to_json(image_vector(saved))
    record_id = await save_training_sample(
        {
            "image_path": db_path,
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
        image_path=db_path,
        crop=crop.strip(),
        issue_type=issue_type.strip(),
        issue_name=issue_name.strip(),
        treatment=treatment.strip(),
        prevention=prevention.strip(),
    )
    meta = await get_knowledge_stats()
    return {
        "id": record_id,
        "image_url": _image_url(db_path),
        "message": f"已同步至辨識知識庫（共 {meta['entries']} 類、{meta['indexed_images']} 張參考圖）",
        **meta,
    }


@app.get("/api/training")
async def training_samples(limit: int = 100):
    items = await list_training_samples(limit=limit)
    for item in items:
        item["image_url"] = _image_url(item["image_path"])
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
    payload = await read_file_response(folder, filename)
    if not payload:
        raise HTTPException(status_code=404, detail="檔案不存在")
    data, content_type = payload
    return Response(content=data, media_type=content_type)


@app.get("/")
async def frontend_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="找不到前端 index.html")
    html = index_path.read_text(encoding="utf-8").replace("{{APP_VERSION}}", APP_VERSION)
    return Response(content=html, media_type="text/html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
