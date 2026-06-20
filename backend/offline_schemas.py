"""
離線辨識任務：Pydantic 資料模型（前後端共用規格）。

手機本地 SQLite / Realm 與雲端 API 皆應對齊此結構。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SyncStatus(str, Enum):
    """同步狀態枚舉。"""

    PENDING = "PENDING"
    SYNCING = "SYNCING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OfflineSelfCheckForm(BaseModel):
    """農民在田間斷網時勾選的簡單視覺特徵表。"""

    has_webbing: bool = Field(default=False, description="是否有蛛絲網（蟎類典型特徵）")
    has_gummosis: bool = Field(default=False, description="是否有流膠/樹幹傷口腐爛")
    has_white_powder: bool = Field(default=False, description="葉片或果實表面是否有白粉狀物")
    has_water_soaked_spots: bool = Field(default=False, description="是否有水浸狀、暗褐色大型斑點")
    after_rain: bool = Field(default=False, description="是否在下雨後才出現症狀")
    affected_part: str = Field(
        default="leaves",
        description="受害部位：leaves | flowers | stems_trunk",
    )

    @field_validator("affected_part")
    @classmethod
    def validate_part(cls, value: str) -> str:
        allowed = {"leaves", "flowers", "stems_trunk"}
        normalized = (value or "leaves").strip().lower()
        if normalized not in allowed:
            raise ValueError(f"affected_part 必須為 {allowed} 之一")
        return normalized


class OfflineRuleEngineResult(BaseModel):
    """離線規則引擎輸出。"""

    preliminary_suggestion: str
    emergency_action: str
    matched_rules: list[str] = Field(default_factory=list)


class OfflineDiagnosticTask(BaseModel):
    """
    手機本地端離線任務完整結構（Mobile Local Database Schema）。

    對應 SQLite 表 offline_diagnostic_tasks 或 Realm Object。
    """

    task_id: str = Field(description="本地端 UUID")
    crop_name: str
    latitude: float
    longitude: float
    local_image_paths: list[str] = Field(default_factory=list, description="手機本地相片路徑")
    offline_self_check: OfflineSelfCheckForm
    sync_status: SyncStatus = SyncStatus.PENDING
    push_registration_id: str | None = Field(default=None, description="FCM/APNs 推播註冊 ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    diagnosis_result: dict[str, Any] | None = None
    error_message: str | None = None

    @field_validator("task_id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        UUID(value)
        return value


class OfflineSyncQueuedResponse(BaseModel):
    """同步接口立即回應。"""

    status: str = "queued"
    task_id: str
    message: str
    sync_time: datetime = Field(default_factory=datetime.utcnow)
    offline_rule_hint: OfflineRuleEngineResult | None = None


class OfflineSyncStatusResponse(BaseModel):
    """查詢任務狀態。"""

    task_id: str
    sync_status: SyncStatus
    diagnosis_result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class OfflineBatchSyncItem(BaseModel):
    """批次同步單筆中繼資料（不含二進位檔）。"""

    task_id: str
    crop_name: str
    latitude: float
    longitude: float
    push_registration_id: str | None = None
    offline_self_check: OfflineSelfCheckForm
    image_count: int = Field(ge=1, le=8)


class OfflineBatchSyncResponse(BaseModel):
    """批次同步立即回應。"""

    status: str = "queued"
    queued_task_ids: list[str]
    message: str
    sync_time: datetime = Field(default_factory=datetime.utcnow)
