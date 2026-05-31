"""funding_rate_model 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FundingRateSnapshot:
    """资金费率快照。"""
    entity_key: str
    current_rate: float        # 当前 funding rate
    predicted_next: float      # 预测下一期
    rate_zscore: float         # 相对历史的 z-score
    rate_percentile: float     # 历史百分位
    cumulative_7d: float       # 7 天累积 funding
    direction_bias: str        # long_crowded, short_crowded, neutral
    mean_reversion_signal: float  # -1~1 均值回归信号
    as_of: str


@dataclass(frozen=True)
class BasisSnapshot:
    """期现价差快照。"""
    entity_key: str
    spot_price: float
    futures_price: float
    basis_pct: float           # (futures - spot) / spot * 100
    basis_zscore: float        # 基差 z-score
    annualized_basis: float    # 年化基差收益
    basis_regime: str          # contango, backwardation, flat
    mean_reversion_signal: float  # -1~1
    as_of: str
