"""新闻情感标注数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SentimentLabel:
    """情感标注结果。"""

    sentiment: str  # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 ~ 1.0
    event_type: str  # "regulatory" | "technical" | "partnership" | "hack" | "macro" | "tokenomics" | "other"
    impact_scope: str  # "asset_specific" | "sector_wide" | "market_wide"
    impact_duration: str  # "short_term" | "medium_term" | "long_term"
