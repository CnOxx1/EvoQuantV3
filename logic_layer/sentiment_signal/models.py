"""sentiment_signal 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentSignal:
    """情绪交易信号。"""
    entity_key: str
    signal_type: str           # extreme_reversal, momentum_confirm, divergence
    direction: str             # bullish, bearish
    strength: float            # 0~1 信号强度
    sentiment_value: float     # 当前情绪值
    sentiment_zscore: float    # 情绪 z-score
    price_correlation: float   # 情绪-价格相关性
    lead_lag_hours: int        # 情绪领先/滞后价格的小时数
    confidence: float          # 0~1 置信度
    as_of: str


@dataclass(frozen=True)
class CausalityResult:
    """Granger 因果检验结果。"""
    entity_key: str
    direction: str             # sentiment_leads_price, price_leads_sentiment, bidirectional, none
    f_statistic: float
    p_value: float
    optimal_lag: int           # 最优滞后期数
    is_significant: bool       # p < 0.05
    as_of: str
