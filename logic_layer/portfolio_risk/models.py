"""组合风险数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PortfolioRiskSnapshot:
    snapshot_time: str
    portfolio_name: str
    asset_count: int
    weights_json: str
    annualized_volatility: float
    daily_var_95: float
    daily_var_99: float
    hhi: float
    effective_n: float
    max_weight: float
    diversification_ratio: float
    risk_contributions_json: str
    sector_concentration_json: str
