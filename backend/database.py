import json
from pathlib import Path

import aiosqlite

from backend.config import DATA_DIR

DB_PATH = DATA_DIR / "app.db"


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS identifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                crop TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                issue_name TEXT NOT NULL,
                confidence REAL NOT NULL,
                treatment TEXT NOT NULL,
                prevention TEXT NOT NULL,
                verified INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS training_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                crop TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                issue_name TEXT NOT NULL,
                notes TEXT,
                treatment TEXT,
                prevention TEXT,
                image_vector TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crop TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                issue_name TEXT NOT NULL,
                treatment TEXT NOT NULL,
                prevention TEXT NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'site',
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(crop, issue_type, issue_name)
            );

            CREATE TABLE IF NOT EXISTS knowledge_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                source_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                image_vector TEXT NOT NULL,
                crop TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                issue_name TEXT NOT NULL,
                treatment TEXT NOT NULL,
                prevention TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await _migrate_columns(db)
        await db.commit()


async def _migrate_columns(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(training_samples)")
    cols = {row[1] for row in await cursor.fetchall()}
    migrations = {
        "treatment": "ALTER TABLE training_samples ADD COLUMN treatment TEXT",
        "prevention": "ALTER TABLE training_samples ADD COLUMN prevention TEXT",
        "image_vector": "ALTER TABLE training_samples ADD COLUMN image_vector TEXT",
    }
    for col, sql in migrations.items():
        if col not in cols:
            await db.execute(sql)


async def save_identification(record: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
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
        await db.commit()
        return cursor.lastrowid


async def get_identification(record_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM identifications WHERE id = ?", (record_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_identifications(limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM identifications ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def verify_identification(record_id: int, is_correct: bool) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE identifications SET verified = ? WHERE id = ?",
            (1 if is_correct else 0, record_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def correct_identification(record_id: int, data: dict) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
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
        await db.commit()
        return cursor.rowcount > 0


async def get_verification_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) AS correct,
                SUM(CASE WHEN verified = 0 THEN 1 ELSE 0 END) AS incorrect,
                SUM(CASE WHEN verified IS NULL THEN 1 ELSE 0 END) AS pending
            FROM identifications
            """
        )
        row = await cursor.fetchone()
        total, correct, incorrect, pending = row
        reviewed = (correct or 0) + (incorrect or 0)
        accuracy = round((correct or 0) / reviewed * 100, 1) if reviewed else None
        return {
            "total": total or 0,
            "correct": correct or 0,
            "incorrect": incorrect or 0,
            "pending": pending or 0,
            "accuracy": accuracy,
        }


async def save_training_sample(record: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
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
        await db.commit()
        return cursor.lastrowid


async def list_training_samples(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM training_samples ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
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
        await db.commit()


async def add_knowledge_index(entry: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
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
        await db.commit()


async def list_knowledge_entries(limit: int = 200) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM knowledge_entries
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def list_knowledge_index(limit: int = 5000) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM knowledge_index ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_knowledge_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM knowledge_entries")
        entries = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM knowledge_index")
        images = (await cursor.fetchone())[0]
        return {"entries": entries or 0, "indexed_images": images or 0}
