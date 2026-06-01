"""链上领先-滞后分析数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeadLagSignal:
    """领先-滞后信号。"""
    signal_name: str
    lead_hours: int
    correlation: float
    p_value: float
    direction: str              # "positive" / "negative"
    last_triggered: str         # ISO timestamp
    timestamp: str


@dataclass(frozen=True)
class OnchainPriceRelation:
    """链上指标与价格的领先-滞后关系。"""
    metric_name: str
    symbol: str
    lead_lag_hours: int         # 正数=链上领先，负数=价格领先
    granger_f_stat: float
    predictive_power: float     # R-squared
    timestamp: str


@dataclass(frozen=True)
class SignalAlert:
    """信号触发告警。"""
    signal_name: str
    symbol: str
    current_value: float
    threshold: float
    triggered_at: str           # ISO timestamp
    expected_price_direction: str  # "up" / "down"
