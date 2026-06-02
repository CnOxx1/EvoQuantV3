"""exchange_announcement 数据模型。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeAnnouncement:
    """交易所公告记录。"""
    exchange: str           # binance, okx, bybit
    title: str
    category: str           # listing, delisting, maintenance, upgrade
    affected_tokens_json: str  # JSON 字符串，如 '["BTC","ETH"]'
    published_at: str       # ISO 8601
    url: str
    severity: str           # high, medium, low
    timestamp: str          # 采集时间 ISO 8601


@dataclass(frozen=True)
class ListingEvent:
    """上币/下币事件。"""
    exchange: str
    token: str
    event_type: str         # listing, delisting, suspension
    announced_at: str       # ISO 8601
    effective_at: str       # ISO 8601
    url: str
