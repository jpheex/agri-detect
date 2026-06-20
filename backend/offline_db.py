"""
離線同步任務：SQLAlchemy 非同步持久層。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.config import DATA_DIR
from backend.offline_schemas import SyncStatus

OFFLINE_DB_PATH = DATA_DIR / "offline_queue.db"
DATABASE_URL = f"sqlite+aiosqlite:///{OFFLINE_DB_PATH.as_posix()}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class OfflineDiagnosticTaskORM(Base):
    """雲端離線同步佇列表。"""

    __tablename__ = "offline_diagnostic_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    crop_name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    saved_image_paths: Mapped[str] = mapped_column(Text, default="[]")
    offline_self_check: Mapped[str] = mapped_column(Text, default="{}")
    sync_status: Mapped[str] = mapped_column(String(20), default=SyncStatus.PENDING.value)
    push_registration_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    diagnosis_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


async def init_offline_db() -> None:
    """建立離線佇列表（若不存在）。"""
    OFFLINE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_offline_task(
    *,
    task_id: str,
    crop_name: str,
    latitude: float,
    longitude: float,
    saved_image_paths: list[str],
    offline_self_check: dict[str, Any],
    push_registration_id: str | None,
    sync_status: SyncStatus = SyncStatus.PENDING,
) -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OfflineDiagnosticTaskORM).where(OfflineDiagnosticTaskORM.task_id == task_id)
        )
        row = result.scalar_one_or_none()
        payload = {
            "crop_name": crop_name,
            "latitude": latitude,
            "longitude": longitude,
            "saved_image_paths": json.dumps(saved_image_paths, ensure_ascii=False),
            "offline_self_check": json.dumps(offline_self_check, ensure_ascii=False),
            "push_registration_id": push_registration_id,
            "sync_status": sync_status.value,
        }
        if row:
            for key, value in payload.items():
                setattr(row, key, value)
        else:
            row = OfflineDiagnosticTaskORM(
                task_id=task_id,
                created_at=now,
                **payload,
            )
            session.add(row)
        await session.commit()


async def update_task_status(
    task_id: str,
    sync_status: SyncStatus,
    *,
    diagnosis_result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OfflineDiagnosticTaskORM).where(OfflineDiagnosticTaskORM.task_id == task_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return
        row.sync_status = sync_status.value
        if diagnosis_result is not None:
            row.diagnosis_result = json.dumps(diagnosis_result, ensure_ascii=False)
        if error_message is not None:
            row.error_message = error_message
        if sync_status == SyncStatus.COMPLETED:
            row.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def get_offline_task(task_id: str) -> OfflineDiagnosticTaskORM | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OfflineDiagnosticTaskORM).where(OfflineDiagnosticTaskORM.task_id == task_id)
        )
        return result.scalar_one_or_none()
