import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from logic_layer.technical_indicators.enricher import MarketFeatureEnricher


def test_market_feature_enricher_does_not_carry_stale_ticker_or_orderbook_forward():
    indicators = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T12:00:00+00:00",
                "close": 100.0,
                "volume": 10.0,
            },
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T12:10:00+00:00",
                "close": 101.0,
                "volume": 11.0,
            },
        ]
    )
    tickers = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "last_price": 100.1,
                "mid_price": 100.0,
                "spread_bps": 2.0,
                "quote_volume_24h": 1_000_000.0,
                "change_24h": 0.01,
                "vwap_24h": 99.8,
                "timestamp": "2026-05-06T12:00:50+00:00",
            }
        ]
    )
    orderbooks = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "mid_price": 100.0,
                "spread_bps": 1.5,
                "bid_depth_notional": 50_000.0,
                "ask_depth_notional": 48_000.0,
                "depth_imbalance": 0.02,
                "timestamp": "2026-05-06T12:00:52+00:00",
            }
        ]
    )

    result = MarketFeatureEnricher().enrich(
        indicators=indicators,
        tickers=tickers,
        funding_rates=pd.DataFrame(),
        orderbooks=orderbooks,
    )

    assert result.loc[0, "ticker_exchange_count"] == 1
    assert result.loc[0, "orderbook_exchange_count"] == 1
    assert result.loc[0, "ticker_last_price_mean"] == 100.1
    assert result.loc[0, "orderbook_total_depth_notional"] == 98_000.0

    assert result.loc[1, "ticker_exchange_count"] == 0
    assert result.loc[1, "orderbook_exchange_count"] == 0
    assert pd.isna(result.loc[1, "ticker_last_price_mean"])
    assert pd.isna(result.loc[1, "orderbook_total_depth_notional"])
    assert result.loc[0, "ticker_context_status"] == "ready"
    assert result.loc[1, "ticker_context_status"] == "stale_only"
    assert result.loc[0, "orderbook_context_status"] == "ready"
    assert result.loc[1, "orderbook_context_status"] == "stale_only"
    assert result.loc[1, "market_context_quality_flag"] == "thin"
    assert "ticker_context_stale_only" in result.loc[1, "market_context_quality_flags"]
    assert "orderbook_context_stale_only" in result.loc[1, "market_context_quality_flags"]


def test_market_feature_enricher_keeps_recent_funding_but_drops_stale_funding():
    indicators = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T12:00:00+00:00",
                "close": 100.0,
                "volume": 10.0,
            },
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T12:40:00+00:00",
                "close": 101.0,
                "volume": 11.0,
            },
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T13:00:00+00:00",
                "close": 102.0,
                "volume": 12.0,
            },
        ]
    )
    funding_rates = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "funding_rate": 0.0001,
                "mark_price": 100.2,
                "index_price": 100.0,
                "timestamp": "2026-05-06T12:00:30+00:00",
            }
        ]
    )

    result = MarketFeatureEnricher().enrich(
        indicators=indicators,
        tickers=pd.DataFrame(),
        funding_rates=funding_rates,
        orderbooks=pd.DataFrame(),
    )

    assert result.loc[0, "funding_exchange_count"] == 1
    assert result.loc[1, "funding_exchange_count"] == 1
    assert result.loc[2, "funding_exchange_count"] == 0

    assert result.loc[0, "funding_rate_mean"] == 0.0001
    assert pd.notna(result.loc[1, "funding_basis_bps_mean"])
    assert pd.isna(result.loc[2, "funding_rate_mean"])
    assert pd.isna(result.loc[2, "funding_basis_bps_mean"])
    assert result.loc[0, "funding_context_status"] == "ready"
    assert result.loc[1, "funding_context_status"] == "ready"
    assert result.loc[2, "funding_context_status"] == "stale_only"


def test_market_feature_enricher_marks_partial_and_missing_context_explicitly():
    indicators = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "timeframe": "1m",
                "open_time": "2026-05-06T12:00:00+00:00",
                "close": 100.0,
                "volume": 10.0,
            }
        ]
    )
    tickers = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "last_price": 100.1,
                "mid_price": 100.0,
                "spread_bps": 2.0,
                "quote_volume_24h": 1_000_000.0,
                "change_24h": 0.01,
                "vwap_24h": 99.8,
                "timestamp": "2026-05-06T12:00:50+00:00",
            },
            {
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "last_price": 100.2,
                "mid_price": 100.1,
                "spread_bps": 2.5,
                "quote_volume_24h": 900_000.0,
                "change_24h": 0.015,
                "vwap_24h": 99.9,
                "timestamp": "2026-05-06T11:59:00+00:00",
            },
        ]
    )

    result = MarketFeatureEnricher().enrich(
        indicators=indicators,
        tickers=tickers,
        funding_rates=pd.DataFrame(),
        orderbooks=pd.DataFrame(),
    )

    assert result.loc[0, "ticker_context_status"] == "partial"
    assert result.loc[0, "ticker_context_known_exchange_count"] == 2
    assert result.loc[0, "ticker_context_raw_exchange_count"] == 2
    assert result.loc[0, "ticker_context_fresh_exchange_count"] == 1
    assert result.loc[0, "ticker_context_stale_exchange_count"] == 1
    assert result.loc[0, "ticker_context_missing_exchange_count"] == 0
    assert result.loc[0, "ticker_context_fresh_exchange_ratio"] == 0.5
    assert result.loc[0, "funding_context_status"] == "missing"
    assert result.loc[0, "orderbook_context_status"] == "missing"
    assert result.loc[0, "market_context_quality_flag"] == "thin"
    assert "ticker_context_partial" in result.loc[0, "market_context_quality_flags"]
    assert "funding_context_missing" in result.loc[0, "market_context_quality_flags"]
    assert "orderbook_context_missing" in result.loc[0, "market_context_quality_flags"]
