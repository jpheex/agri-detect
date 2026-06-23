import json
from pathlib import Path

from PIL import Image

from backend.database import (
    add_knowledge_index,
    get_identification,
    upsert_knowledge_entry,
)
from backend.config import BASE_DIR
from backend.file_storage import materialize_image

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
STRONG_MATCH_THRESHOLD = 0.88
CONTEXT_MIN_SCORE = 0.75

SOURCE_TYPE_LABELS = {
    "training": "預防訓練",
    "verified": "成果驗收",
    "corrected": "手動更正",
}


def community_source_label(source_type: str) -> str:
    label = SOURCE_TYPE_LABELS.get(source_type, "累積案例")
    return f"群眾知識庫（{label}）"


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


async def _resolve_image_path(image_path: str | Path, base_dir: Path = BASE_DIR) -> Path | None:
    path = Path(image_path)
    if path.is_absolute() and path.exists():
        return path
    local = base_dir / str(image_path)
    if local.exists():
        return local
    return await materialize_image(str(image_path))


async def sync_training_sample(
    sample_id: int,
    image_path: str | Path,
    crop: str,
    issue_type: str,
    issue_name: str,
    treatment: str = "",
    prevention: str = "",
) -> None:
    stored_path = str(image_path)
    resolved = await _resolve_image_path(image_path)
    if resolved is None:
        resolved = await materialize_image(stored_path)
    if resolved is None:
        return

    vector = image_vector(resolved)
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
            "image_path": stored_path,
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

    stored_path = record["image_path"]
    resolved = await _resolve_image_path(stored_path, base_dir)
    if resolved is None:
        return

    vector = image_vector(resolved)
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
            "image_path": stored_path,
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

    stored_path = record["image_path"]
    resolved = await _resolve_image_path(stored_path, base_dir)
    if resolved is None:
        return

    advice = resolve_advice(crop, issue_type, issue_name, treatment, prevention)
    vector = image_vector(resolved)

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
            "image_path": stored_path,
            "image_vector": vector_to_json(vector),
            "crop": crop,
            "issue_type": issue_type,
            "issue_name": issue_name,
            "treatment": advice[0],
            "prevention": advice[1],
        }
    )


def find_top_matches(
    query_vector: list[float],
    index_rows: list[dict],
    top_k: int = 3,
    min_score: float = CONTEXT_MIN_SCORE,
) -> list[tuple[dict, float]]:
    scored: list[tuple[dict, float]] = []
    for row in index_rows:
        ref = vector_from_json(row.get("image_vector"))
        if not ref:
            continue
        score = similarity(query_vector, ref)
        if score >= min_score:
            scored.append((row, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def format_community_context(matches: list[tuple[dict, float]]) -> str:
    if not matches:
        return ""
    lines = [
        "【群眾累積辨識知識庫 — 相似參考案例】",
        "以下為其他使用者預防訓練或成果驗收確認的案例，請優先參考：",
    ]
    for index, (row, score) in enumerate(matches, start=1):
        source = SOURCE_TYPE_LABELS.get(row.get("source_type", ""), "累積案例")
        lines.append(
            f"{index}. 作物：{row['crop']} | {row['issue_type']} | {row['issue_name']} "
            f"| 相似度：{round(score * 100)}% | 來源：{source}"
        )
    lines.append(
        "若與你的視覺判斷一致，請提高信心度；若不一致，請依影像特徵獨立判斷並在 photo_feedback 說明。"
    )
    return "\n".join(lines)


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _diagnosis_agrees(gemini_result: dict, community: dict) -> bool:
    if _normalize_label(gemini_result.get("issue_name")) == _normalize_label(community.get("issue_name")):
        return True
    return (
        _normalize_label(gemini_result.get("crop")) == _normalize_label(community.get("crop"))
        and _normalize_label(gemini_result.get("issue_type")) == _normalize_label(community.get("issue_type"))
    )


def resolve_with_community(gemini_result: dict, community: dict | None) -> dict:
    """將 Gemini 結果與群眾知識庫比對結果合併。"""
    if not community:
        return gemini_result

    score = float(community.get("match_score") or 0)
    if score < MATCH_THRESHOLD:
        gemini_result["community_match_score"] = round(score, 2)
        return gemini_result

    gemini_confidence = float(gemini_result.get("confidence") or 0)
    agrees = _diagnosis_agrees(gemini_result, community)

    if score >= STRONG_MATCH_THRESHOLD and (gemini_confidence < 0.75 or not agrees):
        out = dict(community)
        out["source"] = community_source_label(community.get("source_type", ""))
        out["gemini_suggestion"] = {
            "crop": gemini_result.get("crop"),
            "issue_name": gemini_result.get("issue_name"),
            "confidence": gemini_confidence,
        }
        return out

    if agrees:
        gemini_result["confidence"] = round(
            min(0.99, max(gemini_confidence, 0.7 + score * 0.29)),
            2,
        )
        gemini_result["source"] = f"Gemini + {community_source_label(community.get('source_type', ''))}"
        gemini_result["community_match_score"] = round(score, 2)
        return gemini_result

    gemini_result["community_match_score"] = round(score, 2)
    gemini_result["community_suggestion"] = {
        "crop": community.get("crop"),
        "issue_type": community.get("issue_type"),
        "issue_name": community.get("issue_name"),
        "match_score": round(score, 2),
        "source": community_source_label(community.get("source_type", "")),
    }
    return gemini_result


def match_from_image(image_path: Path, index_rows: list[dict]) -> dict | None:
    query_vector = image_vector(image_path)
    return predict_from_index(query_vector, index_rows)


def match_context_from_image(
    image_path: Path,
    index_rows: list[dict],
    top_k: int = 3,
) -> tuple[dict | None, str]:
    query_vector = image_vector(image_path)
    community = predict_from_index(query_vector, index_rows)
    matches = find_top_matches(query_vector, index_rows, top_k=top_k)
    return community, format_community_context(matches)


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

    return {
        "crop": best["crop"],
        "issue_type": best["issue_type"],
        "issue_name": best["issue_name"],
        "treatment": best["treatment"],
        "prevention": best["prevention"],
        "confidence": round(min(0.99, 0.7 + best_score * 0.29), 2),
        "source": community_source_label(best.get("source_type", "")),
        "source_type": best.get("source_type"),
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
