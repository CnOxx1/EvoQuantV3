"""temporal_pattern 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalPattern:
    """时间模式检测结果。"""
    ts: str
    symbol: str
    pattern_type: str          # hourly / daily / monthly / halving / expiry
    pattern_value: float
    confidence: float
    historical_avg: float
    current_deviation: float


@dataclass(frozen=True)
class SeasonalProfile:
    """季节性统计画像。"""
    symbol: str
    dimension: str             # return / volume / volatility
    hour_of_day: int           # 0-23
    day_of_week: int           # 0-6
    month: int                 # 1-12
    avg_value: float
    std_value: float
    sample_count: int
