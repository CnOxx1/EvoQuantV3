"""flow_decomposition 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlowDecomposition:
    """资金流分解结果。"""
    ts: str
    symbol: str
    vpin: float                # Volume-synchronized PIN
    informed_flow_ratio: float
    retail_flow_ratio: float
    smart_money_direction: str  # accumulating / distributing / neutral
    accumulation_phase: bool
    distribution_phase: bool


@dataclass(frozen=True)
class VpinHistory:
    """VPIN 历史记录。"""
    ts: str
    symbol: str
    vpin_value: float
    vpin_percentile: float     # 历史分位 0-100
    alert_level: str           # normal / elevated / critical
