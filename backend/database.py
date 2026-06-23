import json

from backend.db_connection import execute, fetchall, fetchone, init_schema


async def init_db() -> None:
    await init_schema()


async def save_identification(record: dict) -> int:
    last_id, _ = await execute(
        """
        INSERT INTO identifications
        (image_path, crop, issue_type, issue_name, confidence, treatment, prevention)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["image_path"],
            record["crop"],
            record["issue_type"],
            record["issue_name"],
            record["confidence"],
            record["treatment"],
            record["prevention"],
        ),
    )
    return last_id


async def get_identification(record_id: int) -> dict | None:
    return await fetchone("SELECT * FROM identifications WHERE id = ?", (record_id,))


async def list_identifications(limit: int = 50) -> list[dict]:
    return await fetchall(
        "SELECT * FROM identifications ORDER BY id DESC LIMIT ?",
        (limit,),
    )


async def verify_identification(record_id: int, is_correct: bool) -> bool:
    _, changes = await execute(
        "UPDATE identifications SET verified = ? WHERE id = ?",
        (1 if is_correct else 0, record_id),
    )
    return changes > 0


async def correct_identification(record_id: int, data: dict) -> bool:
    _, changes = await execute(
        """
        UPDATE identifications SET
            crop = ?,
            issue_type = ?,
            issue_name = ?,
            treatment = ?,
            prevention = ?,
            confidence = ?,
            verified = 1
        WHERE id = ?
        """,
        (
            data["crop"],
            data["issue_type"],
            data["issue_name"],
            data["treatment"],
            data["prevention"],
            data.get("confidence", 0.95),
            record_id,
        ),
    )
    return changes > 0


async def get_verification_stats() -> dict:
    row = await fetchone(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) AS correct,
            SUM(CASE WHEN verified = 0 THEN 1 ELSE 0 END) AS incorrect,
            SUM(CASE WHEN verified IS NULL THEN 1 ELSE 0 END) AS pending
        FROM identifications
        """
    )
    if not row:
        return {"total": 0, "correct": 0, "incorrect": 0, "pending": 0, "accuracy": None}

    total = row.get("total") or 0
    correct = row.get("correct") or 0
    incorrect = row.get("incorrect") or 0
    pending = row.get("pending") or 0
    reviewed = correct + incorrect
    accuracy = round(correct / reviewed * 100, 1) if reviewed else None
    return {
        "total": total,
        "correct": correct,
        "incorrect": incorrect,
        "pending": pending,
        "accuracy": accuracy,
    }


async def save_training_sample(record: dict) -> int:
    last_id, _ = await execute(
        """
        INSERT INTO training_samples
        (image_path, crop, issue_type, issue_name, notes, treatment, prevention, image_vector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["image_path"],
            record["crop"],
            record["issue_type"],
            record["issue_name"],
            record.get("notes", ""),
            record.get("treatment", ""),
            record.get("prevention", ""),
            record.get("image_vector", ""),
        ),
    )
    return last_id


async def list_training_samples(limit: int = 100) -> list[dict]:
    return await fetchall(
        "SELECT * FROM training_samples ORDER BY id DESC LIMIT ?",
        (limit,),
    )


async def export_training_manifest() -> str:
    samples = await list_training_samples(limit=10000)
    return json.dumps(samples, ensure_ascii=False, indent=2)


async def upsert_knowledge_entry(
    crop: str,
    issue_type: str,
    issue_name: str,
    treatment: str,
    prevention: str,
    source: str = "site",
) -> None:
    await execute(
        """
        INSERT INTO knowledge_entries
        (crop, issue_type, issue_name, treatment, prevention, sample_count, source, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, datetime('now'))
        ON CONFLICT(crop, issue_type, issue_name) DO UPDATE SET
            treatment = excluded.treatment,
            prevention = excluded.prevention,
            sample_count = sample_count + 1,
            source = excluded.source,
            updated_at = datetime('now')
        """,
        (crop, issue_type, issue_name, treatment, prevention, source),
    )


async def add_knowledge_index(entry: dict) -> None:
    await execute(
        """
        INSERT INTO knowledge_index
        (source_type, source_id, image_path, image_vector, crop, issue_type, issue_name, treatment, prevention)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry["source_type"],
            entry["source_id"],
            entry["image_path"],
            entry["image_vector"],
            entry["crop"],
            entry["issue_type"],
            entry["issue_name"],
            entry["treatment"],
            entry["prevention"],
        ),
    )


async def list_knowledge_entries(limit: int = 200) -> list[dict]:
    return await fetchall(
        """
        SELECT * FROM knowledge_entries
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )


async def list_knowledge_index(limit: int = 5000) -> list[dict]:
    return await fetchall(
        "SELECT * FROM knowledge_index ORDER BY id DESC LIMIT ?",
        (limit,),
    )


async def add_knowledge_rejection(entry: dict) -> None:
    await execute(
        "DELETE FROM knowledge_rejections WHERE source_type = ? AND source_id = ?",
        (entry["source_type"], entry["source_id"]),
    )
    await execute(
        """
        INSERT INTO knowledge_rejections
        (source_type, source_id, image_path, image_vector,
         rejected_crop, rejected_issue_type, rejected_issue_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry["source_type"],
            entry["source_id"],
            entry["image_path"],
            entry["image_vector"],
            entry["rejected_crop"],
            entry["rejected_issue_type"],
            entry["rejected_issue_name"],
        ),
    )


async def list_knowledge_rejections(limit: int = 5000) -> list[dict]:
    return await fetchall(
        "SELECT * FROM knowledge_rejections ORDER BY id DESC LIMIT ?",
        (limit,),
    )


async def get_knowledge_stats() -> dict:
    entries_row = await fetchone("SELECT COUNT(*) AS count FROM knowledge_entries")
    images_row = await fetchone("SELECT COUNT(*) AS count FROM knowledge_index")
    rejections_row = await fetchone("SELECT COUNT(*) AS count FROM knowledge_rejections")
    entries = (entries_row or {}).get("count", 0) or 0
    images = (images_row or {}).get("count", 0) or 0
    rejections = (rejections_row or {}).get("count", 0) or 0
    return {"entries": entries, "indexed_images": images, "rejections": rejections}


async def save_farm_monitor(record: dict) -> int:
    last_id, _ = await execute(
        """
        INSERT INTO farm_monitors (label, crop_name, latitude, longitude, push_enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            record.get("label", "").strip(),
            record["crop_name"].strip(),
            float(record["latitude"]),
            float(record["longitude"]),
            1 if record.get("push_enabled", True) else 0,
        ),
    )
    return last_id


async def list_farm_monitors(limit: int = 100) -> list[dict]:
    return await fetchall(
        "SELECT * FROM farm_monitors ORDER BY id DESC LIMIT ?",
        (limit,),
    )


async def delete_farm_monitor(monitor_id: int) -> bool:
    _, changes = await execute("DELETE FROM farm_monitors WHERE id = ?", (monitor_id,))
    return changes > 0


async def update_farm_monitor_alert(monitor_id: int, disease_name: str) -> None:
    await execute(
        """
        UPDATE farm_monitors
        SET last_alert_at = datetime('now'), last_high_disease = ?
        WHERE id = ?
        """,
        (disease_name, monitor_id),
    )
