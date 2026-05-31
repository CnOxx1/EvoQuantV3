"""regime_detection 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeState:
    """市场状态分类结果。"""
    entity_key: str
    regime: str            # trending_up, trending_down, ranging, high_vol, crisis
    confidence: float      # 0~1 置信度
    duration_hours: int    # 当前状态持续时间
    volatility_regime: str # low, normal, high, extreme
    correlation_regime: str # high_corr, moderate_corr, decorrelated
    momentum_regime: str   # strong_up, weak_up, neutral, weak_down, strong_down
    as_of: str             # ISO 8601


@dataclass(frozen=True)
class RegimeTransition:
    """状态转换记录。"""
    entity_key: str
    from_regime: str
    to_regime: str
    transition_time: str
    trigger_factors: str   # 触发因素（逗号分隔）
    transition_speed: str  # gradual, sudden
