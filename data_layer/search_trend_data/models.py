"""search_trend_data 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchTrend:
    """搜索趋势快照。"""
    keyword: str            # bitcoin, ethereum, crypto
    interest_score: int     # Google Trends 0~100
    interest_change_7d: float  # 7日变化率
    timestamp: str          # ISO 8601
    category: str           # crypto, defi, nft


@dataclass(frozen=True)
class TrendHistory:
    """搜索趋势历史数据点。"""
    keyword: str
    interest_score: int
    date: str               # YYYY-MM-DD
    category: str
