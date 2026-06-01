"""contagion_risk 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContagionMetric:
    """传染风险指标。"""
    ts: str
    symbol: str
    covar_95: float            # CoVaR at 95% confidence
    conditional_correlation: float
    tail_beta: float           # 极端下跌时的 beta
    systemic_contribution: float


@dataclass(frozen=True)
class CascadeRisk:
    """级联风险评估。"""
    ts: str
    risk_type: str             # defi_cascade / exchange_contagion / stablecoin_depeg
    risk_level: float          # 0-100
    affected_assets: str       # JSON list
    trigger_conditions: str    # JSON description
