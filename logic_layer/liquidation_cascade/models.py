"""清算级联预测数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiquidationCluster:
    """清算聚集区。"""
    symbol: str
    price_level: float          # 清算价格水平
    total_size_usd: float       # 该价位聚集的清算量（USD）
    leverage_avg: float         # 平均杠杆倍数
    distance_pct: float         # 距当前价格的百分比距离
    direction: str              # "long" / "short"


@dataclass(frozen=True)
class CascadeRisk:
    """级联清算风险评估。"""
    symbol: str
    cascade_probability: float  # 级联触发概率 [0, 1]
    estimated_liquidation_usd: float  # 预估清算金额
    price_trigger: float        # 触发价格
    direction: str              # "long" / "short"
    severity: str               # "critical" / "high" / "medium" / "low"


@dataclass(frozen=True)
class LiquidationHeatmap:
    """清算热力图单元格。"""
    symbol: str
    price_from: float           # 价格区间起点
    price_to: float             # 价格区间终点
    long_liq_usd: float         # 多头清算量（USD）
    short_liq_usd: float        # 空头清算量（USD）
    net_pressure: float         # 净压力（正=多头清算压力大）
