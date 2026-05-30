from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Optional

from pydantic import BaseModel, Field


class MacroContextConfig(BaseModel):
    """宏观上下文聚合模块的可调参数。"""

    short_lookback_days: int = Field(
        default=1,
        ge=1,
        description="短周期回看窗口，默认 1 天。",
    )
    medium_lookback_days: int = Field(
        default=5,
        ge=1,
        description="中周期回看窗口，默认 5 天。",
    )
    include_disabled_factors: bool = Field(
        default=False,
        description="是否包含目录中已禁用的 P1 因子。",
    )
    interval_filter: str | None = Field(
        default=None,
        description="按 interval 过滤，例如 1d 或 1h。",
    )


class MacroContextSnapshot(BaseModel):
    """AI 可直接消费的单因子宏观上下文快照。"""

    TABLE_COLUMNS: ClassVar[list[str]] = [
        "factor_id",
        "name",
        "category",
        "factor_type",
        "interval",
        "snapshot_time",
        "observation_time",
        "latest_value",
        "unit",
        "currency",
        "quality_flag",
        "source_name",
        "source_symbol",
        "source_priority",
        "freshness_seconds",
        "staleness_ttl_seconds",
        "is_stale",
        "reference_1d_time",
        "reference_1d_value",
        "change_1d_abs",
        "change_1d_pct",
        "change_1d_bps",
        "reference_5d_time",
        "reference_5d_value",
        "change_5d_abs",
        "change_5d_pct",
        "change_5d_bps",
        "context_completeness_score",
        "raw_context_json",
    ]

    factor_id: str
    name: str
    category: str
    factor_type: str
    interval: str
    snapshot_time: datetime
    observation_time: datetime
    latest_value: float
    unit: Optional[str] = None
    currency: Optional[str] = None
    quality_flag: str = "ok"
    source_name: str
    source_symbol: str
    source_priority: str = "primary"
    freshness_seconds: Optional[float] = None
    staleness_ttl_seconds: Optional[int] = None
    is_stale: bool = False
    reference_1d_time: Optional[datetime] = None
    reference_1d_value: Optional[float] = None
    change_1d_abs: Optional[float] = None
    change_1d_pct: Optional[float] = None
    change_1d_bps: Optional[float] = None
    reference_5d_time: Optional[datetime] = None
    reference_5d_value: Optional[float] = None
    change_5d_abs: Optional[float] = None
    change_5d_pct: Optional[float] = None
    change_5d_bps: Optional[float] = None
    context_completeness_score: float = 0.0
    raw_context_json: Optional[str] = None

    def to_db_tuple(self) -> tuple:
        def iso_or_none(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value is not None else None

        return (
            self.factor_id,
            self.name,
            self.category,
            self.factor_type,
            self.interval,
            self.snapshot_time.isoformat(),
            self.observation_time.isoformat(),
            self.latest_value,
            self.unit,
            self.currency,
            self.quality_flag,
            self.source_name,
            self.source_symbol,
            self.source_priority,
            self.freshness_seconds,
            self.staleness_ttl_seconds,
            int(self.is_stale),
            iso_or_none(self.reference_1d_time),
            self.reference_1d_value,
            self.change_1d_abs,
            self.change_1d_pct,
            self.change_1d_bps,
            iso_or_none(self.reference_5d_time),
            self.reference_5d_value,
            self.change_5d_abs,
            self.change_5d_pct,
            self.change_5d_bps,
            self.context_completeness_score,
            self.raw_context_json,
        )
