"""volatility_forecast 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class VolatilitySnapshot:
    """波动率快照。"""
    entity_key: str
    realized_vol_1d: float     # 1 天已实现波动率（年化）
    realized_vol_7d: float     # 7 天已实现波动率
    realized_vol_30d: float    # 30 天已实现波动率
    implied_vol: float         # 隐含波动率（来自期权）
    rv_iv_spread: float        # RV - IV 差值
    vol_regime: str            # low, normal, high, extreme
    forecast_1d: float         # 未来 1 天波动率预测
    forecast_7d: float         # 未来 7 天波动率预测
    vol_percentile: float      # 当前波动率在历史中的百分位
    as_of: str


@dataclass(frozen=True)
class VolatilityCone:
    """波动率锥数据点。"""
    entity_key: str
    window_days: int           # 观察窗口（7, 14, 30, 60, 90）
    current: float             # 当前值
    percentile_25: float       # 25 分位
    percentile_50: float       # 中位数
    percentile_75: float       # 75 分位
    min_val: float
    max_val: float
    as_of: str
