"""新闻情感标注分类器 — 基于规则的 NLP 标注（不依赖外部 LLM API）。"""

from __future__ import annotations

import re
from logic_layer.news_sentiment.models import SentimentLabel

# 关键词词典
_BULLISH_KEYWORDS = (
    "surge", "soar", "rally", "bullish", "breakout", "all-time high", "ath",
    "approval", "approved", "adopt", "adoption", "partnership", "launch",
    "upgrade", "milestone", "record", "institutional", "inflow", "accumulate",
    "利好", "突破", "创新高", "暴涨", "通过", "批准", "合作", "上线",
)
_BEARISH_KEYWORDS = (
    "crash", "plunge", "dump", "bearish", "hack", "exploit", "vulnerability",
    "ban", "banned", "lawsuit", "sec", "fraud", "bankrupt", "insolvency",
    "liquidat", "outflow", "sell-off", "selloff", "crackdown", "sanction",
    "利空", "暴跌", "黑客", "攻击", "禁止", "诉讼", "破产", "清算",
)

_EVENT_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("regulatory", re.compile(r"sec|regulat|compliance|ban|legal|lawsuit|sanction|cftc|crackdown|监管|合规|禁令", re.I)),
    ("hack", re.compile(r"hack|exploit|breach|vulnerability|attack|stolen|drain|黑客|攻击|漏洞|盗", re.I)),
    ("partnership", re.compile(r"partner|collaborat|integrat|alliance|合作|联盟|集成", re.I)),
    ("tokenomics", re.compile(r"burn|unlock|halving|supply|airdrop|staking|vesting|销毁|解锁|减半|空投", re.I)),
    ("technical", re.compile(r"upgrade|fork|mainnet|testnet|v2|layer|protocol|升级|主网|分叉", re.I)),
    ("macro", re.compile(r"fed|fomc|rate|inflation|gdp|cpi|treasury|yield|利率|通胀|美联储", re.I)),
]

_MARKET_WIDE_KEYWORDS = re.compile(
    r"market|crypto market|btc|bitcoin|全市场|加密市场|整体", re.I
)
_SECTOR_KEYWORDS = re.compile(
    r"defi|nft|layer.?2|l2|meme|ai.?token|板块|赛道", re.I
)


class NewsSentimentClassifier:
    """基于关键词和规则的新闻情感/事件分类器。"""

    def classify(self, title: str, summary: str | None = None) -> SentimentLabel:
        """对单条新闻进行情感和事件类型分类。"""
        text = f"{title} {summary or ''}".lower()

        sentiment, confidence = self._classify_sentiment(text)
        event_type = self._classify_event_type(text)
        impact_scope = self._classify_impact_scope(text)
        impact_duration = self._estimate_duration(event_type)

        return SentimentLabel(
            sentiment=sentiment,
            confidence=confidence,
            event_type=event_type,
            impact_scope=impact_scope,
            impact_duration=impact_duration,
        )

    def _classify_sentiment(self, text: str) -> tuple[str, float]:
        bullish_hits = sum(1 for kw in _BULLISH_KEYWORDS if kw in text)
        bearish_hits = sum(1 for kw in _BEARISH_KEYWORDS if kw in text)
        total = bullish_hits + bearish_hits
        if total == 0:
            return "neutral", 0.5
        if bullish_hits > bearish_hits:
            confidence = min(0.6 + (bullish_hits - bearish_hits) * 0.1, 0.95)
            return "bullish", round(confidence, 2)
        if bearish_hits > bullish_hits:
            confidence = min(0.6 + (bearish_hits - bullish_hits) * 0.1, 0.95)
            return "bearish", round(confidence, 2)
        return "neutral", 0.4

    def _classify_event_type(self, text: str) -> str:
        for event_type, pattern in _EVENT_TYPE_PATTERNS:
            if pattern.search(text):
                return event_type
        return "other"

    def _classify_impact_scope(self, text: str) -> str:
        if _MARKET_WIDE_KEYWORDS.search(text):
            return "market_wide"
        if _SECTOR_KEYWORDS.search(text):
            return "sector_wide"
        return "asset_specific"

    @staticmethod
    def _estimate_duration(event_type: str) -> str:
        duration_map = {
            "regulatory": "long_term",
            "hack": "short_term",
            "partnership": "medium_term",
            "tokenomics": "medium_term",
            "technical": "medium_term",
            "macro": "long_term",
            "other": "short_term",
        }
        return duration_map.get(event_type, "short_term")

