"""資料庫連線抽象層：本機 SQLite 或 Cloudflare D1。"""

from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from backend.cloudflare_config import d1_enabled
from backend.config import BASE_DIR, DATA_DIR
from backend.d1_client import D1Error, get_d1_client

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "app.db"
_SCHEMA_PATH = BASE_DIR / "schema" / "d1.sql"

_d1_active = False


def use_d1() -> bool:
    """D1 已設定且啟動時連線成功。"""
    return _d1_active


async def fetchall(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if use_d1():
        return await get_d1_client().fetchall(sql, params)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def fetchone(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    if use_d1():
        return await get_d1_client().fetchone(sql, params)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None


async def execute(sql: str, params: tuple[Any, ...] = ()) -> tuple[int, int]:
    if use_d1():
        return await get_d1_client().execute(sql, params)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, params)
        await db.commit()
        return int(cursor.lastrowid or 0), int(cursor.rowcount or 0)


async def _init_sqlite_schema() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        await _migrate_sqlite_columns(db)
        await db.commit()


async def init_schema() -> None:
    global _d1_active
    _d1_active = False

    if d1_enabled():
        try:
            await get_d1_client().executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            _d1_active = True
            logger.info("Cloudflare D1 connected")
            return
        except D1Error as exc:
            logger.warning("D1 init failed (%s), falling back to SQLite", exc)
        except Exception as exc:
            logger.warning("D1 init error (%s), falling back to SQLite", exc)

    await _init_sqlite_schema()


async def _migrate_sqlite_columns(db: aiosqlite.Connection) -> None:
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
