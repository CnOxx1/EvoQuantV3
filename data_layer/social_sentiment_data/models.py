"""social_sentiment_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SocialMention:
    """单条社交媒体提及记录。"""
    platform: str          # twitter, discord, telegram, reddit
    entity_key: str        # BTC, ETH, etc.
    mention_time: str      # ISO 8601
    author_tier: str       # kol, whale, retail
    content_hash: str      # 内容去重哈希
    sentiment_score: float # -1.0 ~ 1.0
    engagement: int        # likes + retweets + replies
    reach: int             # 作者粉丝数
    raw_text_snippet: str  # 前 200 字符


@dataclass(frozen=True)
class SentimentAggregation:
    """某实体在某时间窗口的情绪聚合。"""
    entity_key: str
    platform: str
    interval: str          # 1h, 4h, 1d
    window_start: str
    window_end: str
    mention_count: int
    avg_sentiment: float
    weighted_sentiment: float  # engagement 加权
    bullish_ratio: float       # sentiment > 0.2 的比例
    bearish_ratio: float       # sentiment < -0.2 的比例
    kol_sentiment: float       # KOL 群体情绪
    volume_zscore: float       # 提及量 z-score（相对 7d 均值）
