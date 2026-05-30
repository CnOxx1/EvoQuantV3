"""时间切片查询数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainSlice:
    """单域在某时刻的数据切片。"""

    domain: str
    status: str  # "ready" | "stale" | "missing"
    data_timestamp: str | None = None
    staleness_seconds: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeSlice:
    """某时刻的完整市场快照。"""

    requested_at: str
    generated_at: str
    symbols: list[str]
    domains: dict[str, DomainSlice] = field(default_factory=dict)
    coverage_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class TimeSliceRange:
    """多时间点切片集合。"""

    start: str
    end: str
    interval_seconds: int
    slice_count: int
    slices: list[TimeSlice] = field(default_factory=list)


@dataclass
class FeatureHistoryPoint:
    """单个特征在某时刻的值。"""

    timestamp: str
    symbol: str
    feature: str
    value: float | None = None


@dataclass
class FeatureHistory:
    """特征历史序列。"""

    symbol: str
    features: list[str]
    start: str
    end: str
    point_count: int = 0
    series: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
