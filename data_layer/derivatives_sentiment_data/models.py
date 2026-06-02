"""derivatives_sentiment_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentIndex:
    """恐惧与贪婪指数数据。"""
    fear_greed_index: int          # 0-100 指数值
    fear_greed_class: str          # Extreme Fear/Fear/Neutral/Greed/Extreme Greed
    collected_at: str              # ISO 8601


@dataclass(frozen=True)
class DerivativesSentiment:
    """衍生品情绪综合数据。"""
    btc_long_short_ratio: float    # BTC 多空比
    eth_long_short_ratio: float    # ETH 多空比
    total_open_interest_usd: float # 全网未平仓合约 (USD)
    oi_change_24h: float           # 24h OI 变化百分比
    estimated_leverage_ratio: float # 预估杠杆率
    put_call_ratio: float          # 看跌/看涨比率
    collected_at: str              # ISO 8601
