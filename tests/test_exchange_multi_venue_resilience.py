"""Multi-venue collection resilience: one blocked exchange must not kill others."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import ccxt

from data_layer.exchange_data.client import (
    ExchangeClientManager,
    is_geo_restricted_error,
)
from data_layer.exchange_data.funding import FundingRateCollector
from data_layer.exchange_data.models import FundingRate


def test_is_geo_restricted_error_detects_binance_451_and_bybit_403():
    assert is_geo_restricted_error(
        ccxt.ExchangeNotAvailable(
            "binance GET https://api.binance.com/api/v3/exchangeInfo 451 "
            "Service unavailable from a restricted location"
        )
    )
    assert is_geo_restricted_error(
        ccxt.RateLimitExceeded(
            "bybit GET https://api.bybit.com/v5/market/instruments-info 403 "
            "The Amazon CloudFront distribution is configured to block access "
            "from your country"
        )
    )
    assert not is_geo_restricted_error(ccxt.NetworkError("connection reset"))


def test_binance_spot_client_uses_data_api_host(monkeypatch):
    monkeypatch.setattr(
        "data_layer.exchange_data.client.BINANCE_PUBLIC_API_BASE",
        "https://data-api.binance.vision",
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.client.BINANCE_LOAD_SPOT_MARKETS_ONLY",
        True,
    )
    mgr = ExchangeClientManager()
    client = mgr.get_client("binance", market_type="spot")
    assert client.urls["api"]["public"].startswith("https://data-api.binance.vision")
    assert client.options.get("fetchMarkets") == ["spot"]


def test_funding_skips_failed_venue_and_keeps_others(monkeypatch):
    mgr = MagicMock()

    def get_client(name, market_type="spot"):
        if name == "binance":
            client = MagicMock()
            client.markets = {}
            client.load_markets.side_effect = ccxt.ExchangeNotAvailable(
                "binance GET https://fapi.binance.com/fapi/v1/exchangeInfo 451 "
                "restricted location"
            )
            return client
        if name == "okx":
            client = MagicMock()
            client.markets = {"BTC/USDT:USDT": {}}
            client.has = {"fetchFundingRates": False}
            return client
        if name == "bybit":
            client = MagicMock()
            client.markets = {}
            client.load_markets.side_effect = ccxt.RateLimitExceeded(
                "bybit 403 CloudFront block access from your country"
            )
            return client
        raise AssertionError(name)

    mgr.get_client.side_effect = get_client

    collector = FundingRateCollector(mgr, db=MagicMock())
    monkeypatch.setattr(
        "data_layer.exchange_data.funding.TARGET_EXCHANGES",
        ["binance", "okx", "bybit"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.funding.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )

    def fake_fetch(exchange_name, symbol):
        if exchange_name != "okx":
            raise AssertionError("should not fetch blocked venues")
        return FundingRate(
            symbol=symbol,
            exchange=exchange_name,
            funding_rate=0.0001,
            mark_price=100.0,
            index_price=99.9,
            next_funding_time=None,
            timestamp=datetime(2026, 8, 7, 3, 0, 0),
        )

    monkeypatch.setattr(collector, "fetch_funding_rate", fake_fetch)
    monkeypatch.setattr(
        "data_layer.exchange_data.funding.parallel_fetch",
        lambda fn, tasks, task_label="": [fn(*t) for t in tasks],
    )

    rates = collector.fetch_all_funding_rates()
    assert len(rates) == 1
    assert rates[0].exchange == "okx"


def test_collect_once_continues_after_funding_error(monkeypatch, tmp_path):
    from database.db_manager import DBManager
    from data_layer.exchange_data.service import ExchangeDataService

    db = DBManager(db_path=str(tmp_path / "t.db"))
    svc = ExchangeDataService(db=db)

    calls: list[str] = []

    def job(source_name, job_name, func, metadata=None, *, reraise=True):
        calls.append(source_name)
        if source_name == "funding":
            # Simulate recorded failure without aborting when reraise=False.
            if reraise:
                raise RuntimeError("funding boom")
            return None
        return []

    monkeypatch.setattr(svc, "_run_collection_job", job)
    monkeypatch.setattr(svc, "collect_derivatives_once", lambda: calls.append("derivatives"))
    monkeypatch.setattr(
        "data_layer.exchange_data.service.KLINE_TIMEFRAMES",
        ["1m"],
    )

    svc.collect_once(include_backfill=False)
    assert "funding" in calls
    assert "orderbook" in calls
    assert "derivatives" in calls
