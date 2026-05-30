"""数据管道延迟追踪数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainLatency:
    """单域延迟指标。"""

    domain: str
    latest_data_time: str | None = None
    measured_at: str | None = None
    latency_seconds: float | None = None
    status: str = "unknown"  # "fresh" | "acceptable" | "stale" | "unavailable"
    record_count: int = 0


@dataclass
class PipelineLatencyReport:
    """全管道延迟报告。"""

    measured_at: str
    domains: dict[str, DomainLatency] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
