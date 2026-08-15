from __future__ import annotations

from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService
from logic_layer.technical_indicators.service import TechnicalIndicatorService


class _TickerOnlyDatabase:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def fetch_all(self, query: str, params: tuple[str, str]):
        self.queries.append(query)
        if "FROM klines" in query:
            return []
        return [{"last_price": 100.0}]


def test_as_utc_timestamp_normalizes_naive_and_aware_values():
    naive = TechnicalIndicatorService._as_utc_timestamp("2026-08-15T15:00:00")
    aware = TechnicalIndicatorService._as_utc_timestamp("2026-08-15T15:00:00+00:00")

    assert naive is not None
    assert aware is not None
    assert naive == aware
    assert str(naive.tz) == "UTC"


def test_cross_venue_ticker_fallback_uses_timestamp_column():
    database = _TickerOnlyDatabase()
    service = CrossVenueArbService(db=database)
    service.VENUES = ["okx"]

    prices = service._load_venue_prices("BTC")

    assert prices == [{"venue": "okx", "price": 100.0}]
    assert any("ORDER BY timestamp DESC" in query for query in database.queries)
