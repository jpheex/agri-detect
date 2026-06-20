import json
from pathlib import Path

from PIL import Image

from backend.database import (
    add_knowledge_index,
    get_identification,
    upsert_knowledge_entry,
)

BASE_KNOWLEDGE = [
    {
        "crop": "番茄",
        "issue_type": "病害",
        "issue_name": "晚疫病",
        "keywords": ["tomato", "late", "blight", "dark", "spot"],
        "treatment": "移除病葉，噴灑代森錳鋅或烯酰嗎啉；改善通風，避免葉面長時間潮濕。",
        "prevention": "輪作、選抗病品種、避免傍晚澆水、保持株距通風。",
    },
    {
        "crop": "水稻",
        "issue_type": "蟲害",
        "issue_name": "稻飛蝨",
        "keywords": ["rice", "planthopper", "hopper"],
        "treatment": "田水排乾後施用吡蟲啉或噻蟲嗪；嚴重時需連續防治 2-3 次。",
        "prevention": "清除田邊雜草、合理施氮、使用誘蟲板監測蟲口密度。",
    },
    {
        "crop": "蘋果",
        "issue_type": "病害",
        "issue_name": "蘋果黑星病",
        "keywords": ["apple", "scab", "black"],
        "treatment": "發病初期噴多菌靈或戊唑醇；清除落葉減少病源。",
        "prevention": "冬季清園、選抗病品種、花期前後預防性噴藥。",
    },
    {
        "crop": "黃瓜",
        "issue_type": "病害",
        "issue_name": "霜霉病",
        "keywords": ["cucumber", "downy", "mildew", "yellow"],
        "treatment": "噴烯酰嗎啉或嘧菌酯；降低棚內濕度，增加通風。",
        "prevention": "控制澆水量、避免密植、發現病葉立即移除。",
    },
    {
        "crop": "玉米",
        "issue_type": "蟲害",
        "issue_name": "玉米螟",
        "keywords": ["corn", "maize", "borer"],
        "treatment": "心葉期撒施辛硫磷顆粒劑；或噴氯蟲苯甲酰胺。",
        "prevention": "秋後深翻滅蛹、性誘劑誘殺成蟲、適期播種避高峰。",
    },
]

DEFAULT_TREATMENT = "請依當地農會或植保人員建議，選擇核准藥劑並遵守安全間隔期。"
DEFAULT_PREVENTION = "保持田間通風、合理施肥、定期巡查，及早發現及早處理。"

MATCH_THRESHOLD = 0.82


def image_vector(image_path: Path) -> list[float]:
    with Image.open(image_path) as img:
        img = img.convert("RGB").resize((32, 32))
        pixels = list(img.getdata())
    return [channel / 255.0 for pixel in pixels for channel in pixel]


def vector_to_json(vector: list[float]) -> str:
    return json.dumps(vector)


def vector_from_json(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dist = sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)
    return max(0.0, 1.0 - dist * 4.0)


def lookup_builtin(crop: str, issue_name: str) -> tuple[str, str] | None:
    for item in BASE_KNOWLEDGE:
        if item["crop"] == crop and item["issue_name"] == issue_name:
            return item["treatment"], item["prevention"]
    return None


def resolve_advice(
    crop: str,
    issue_type: str,
    issue_name: str,
    treatment: str = "",
    prevention: str = "",
) -> tuple[str, str]:
    if treatment.strip() and prevention.strip():
        return treatment.strip(), prevention.strip()

    builtin = lookup_builtin(crop, issue_name)
    if builtin:
        return (
            treatment.strip() or builtin[0],
            prevention.strip() or builtin[1],
        )

    if issue_type == "健康":
        return (
            treatment.strip() or "目前無需治療，持續觀察即可。",
            prevention.strip() or "維持良好栽培管理與環境衛生。",
        )

    return (
        treatment.strip() or DEFAULT_TREATMENT,
        prevention.strip() or DEFAULT_PREVENTION,
    )


async def sync_training_sample(
    sample_id: int,
    image_path: Path,
    crop: str,
    issue_type: str,
    issue_name: str,
    treatment: str = "",
    prevention: str = "",
) -> None:
    vector = image_vector(image_path)
    advice = resolve_advice(crop, issue_type, issue_name, treatment, prevention)

    await upsert_knowledge_entry(
        crop=crop,
        issue_type=issue_type,
        issue_name=issue_name,
        treatment=advice[0],
        prevention=advice[1],
        source="site_training",
    )
    await add_knowledge_index(
        {
            "source_type": "training",
            "source_id": sample_id,
            "image_path": str(image_path),
            "image_vector": vector_to_json(vector),
            "crop": crop,
            "issue_type": issue_type,
            "issue_name": issue_name,
            "treatment": advice[0],
            "prevention": advice[1],
        }
    )


async def sync_verified_identification(record_id: int, base_dir: Path) -> None:
    record = await get_identification(record_id)
    if not record:
        return

    image_path = base_dir / record["image_path"]
    if not image_path.exists():
        return

    vector = image_vector(image_path)
    await upsert_knowledge_entry(
        crop=record["crop"],
        issue_type=record["issue_type"],
        issue_name=record["issue_name"],
        treatment=record["treatment"],
        prevention=record["prevention"],
        source="site_verified",
    )
    await add_knowledge_index(
        {
            "source_type": "verified",
            "source_id": record_id,
            "image_path": str(image_path),
            "image_vector": vector_to_json(vector),
            "crop": record["crop"],
            "issue_type": record["issue_type"],
            "issue_name": record["issue_name"],
            "treatment": record["treatment"],
            "prevention": record["prevention"],
        }
    )


async def sync_manual_correction(
    record_id: int,
    base_dir: Path,
    crop: str,
    issue_type: str,
    issue_name: str,
    treatment: str,
    prevention: str,
) -> None:
    record = await get_identification(record_id)
    if not record:
        return

    image_path = base_dir / record["image_path"]
    if not image_path.exists():
        return

    advice = resolve_advice(crop, issue_type, issue_name, treatment, prevention)
    vector = image_vector(image_path)

    await upsert_knowledge_entry(
        crop=crop,
        issue_type=issue_type,
        issue_name=issue_name,
        treatment=advice[0],
        prevention=advice[1],
        source="manual_correction",
    )
    await add_knowledge_index(
        {
            "source_type": "corrected",
            "source_id": record_id,
            "image_path": str(image_path),
            "image_vector": vector_to_json(vector),
            "crop": crop,
            "issue_type": issue_type,
            "issue_name": issue_name,
            "treatment": advice[0],
            "prevention": advice[1],
        }
    )


def predict_from_index(query_vector: list[float], index_rows: list[dict]) -> dict | None:
    best = None
    best_score = 0.0

    for row in index_rows:
        ref = vector_from_json(row.get("image_vector"))
        if not ref:
            continue
        score = similarity(query_vector, ref)
        if score > best_score:
            best_score = score
            best = row

    if not best or best_score < MATCH_THRESHOLD:
        return None

    source_label = "網站訓練資料" if best["source_type"] == "training" else "驗收確認資料"
    if best["source_type"] == "corrected":
        source_label = "手動更正資料"
    elif best["source_type"] == "verified":
        source_label = "驗收確認資料"
    elif best["source_type"] == "training":
        source_label = "網站訓練資料"
    return {
        "crop": best["crop"],
        "issue_type": best["issue_type"],
        "issue_name": best["issue_name"],
        "treatment": best["treatment"],
        "prevention": best["prevention"],
        "confidence": round(min(0.99, 0.7 + best_score * 0.29), 2),
        "source": source_label,
        "match_score": round(best_score, 2),
    }


def predict_from_builtin(image_path: Path, knowledge_entries: list[dict]) -> dict:
    name_hint = image_path.stem.lower()
    query_vector = image_vector(image_path)

    for entry in knowledge_entries:
        crop = entry["crop"].lower()
        issue = entry["issue_name"].lower()
        if crop in name_hint or issue in name_hint:
            return {
                "crop": entry["crop"],
                "issue_type": entry["issue_type"],
                "issue_name": entry["issue_name"],
                "treatment": entry["treatment"],
                "prevention": entry["prevention"],
                "confidence": 0.75,
                "source": "網站知識庫",
                "match_score": None,
            }

    for item in BASE_KNOWLEDGE:
        if any(keyword in name_hint for keyword in item["keywords"]):
            return {
                "crop": item["crop"],
                "issue_type": item["issue_type"],
                "issue_name": item["issue_name"],
                "treatment": item["treatment"],
                "prevention": item["prevention"],
                "confidence": 0.68,
                "source": "內建知識庫",
                "match_score": None,
            }

    if knowledge_entries:
        entry = knowledge_entries[0]
        return {
            "crop": entry["crop"],
            "issue_type": entry["issue_type"],
            "issue_name": entry["issue_name"],
            "treatment": entry["treatment"],
            "prevention": entry["prevention"],
            "confidence": 0.55,
            "source": "網站知識庫（低信心）",
            "match_score": None,
        }

    signature = sum(query_vector)
    item = BASE_KNOWLEDGE[int(signature * 1000) % len(BASE_KNOWLEDGE)]
    return {
        "crop": item["crop"],
        "issue_type": item["issue_type"],
        "issue_name": item["issue_name"],
        "treatment": item["treatment"],
        "prevention": item["prevention"],
        "confidence": 0.52,
        "source": "內建知識庫（低信心）",
        "match_score": None,
    }


async def predict(image_path: Path, index_rows: list[dict], knowledge_entries: list[dict]) -> dict:
    query_vector = image_vector(image_path)
    matched = predict_from_index(query_vector, index_rows)
    if matched:
        return matched
    return predict_from_builtin(image_path, knowledge_entries)
