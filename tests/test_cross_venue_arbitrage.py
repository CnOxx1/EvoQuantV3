"""Unit tests for CrossVenueArbCalculator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic_layer.cross_venue_arbitrage.calculator import CrossVenueArbCalculator


def test_compute_spread_bps_basic():
    calc = CrossVenueArbCalculator()
    spread = calc.compute_spread_bps(100.0, 101.0)
    assert 99.0 < spread < 101.0
    assert calc.compute_spread_bps(50.0, 50.0) == 0.0
    assert calc.compute_spread_bps(0.0, 100.0) == 0.0


def test_detect_arbitrage_finds_opportunities():
    calc = CrossVenueArbCalculator()
    prices = [
        {"venue": "binance", "price": 60000.0},
        {"venue": "dydx", "price": 60050.0},
        {"venue": "hyperliquid", "price": 59980.0},
    ]
    opps = calc.detect_arbitrage(prices, min_spread_bps=5.0)
    assert len(opps) >= 1
    for opp in opps:
        assert "venue_buy" in opp
        assert "venue_sell" in opp
        assert opp["spread_bps"] >= 5.0
        assert opp["price_buy"] < opp["price_sell"]


def test_detect_arbitrage_no_opportunities_when_tight():
    calc = CrossVenueArbCalculator()
    prices = [
        {"venue": "binance", "price": 60000.0},
        {"venue": "dydx", "price": 60001.0},
    ]
    opps = calc.detect_arbitrage(prices, min_spread_bps=5.0)
    assert opps == []


def test_compute_persistence_groups_by_venue_pair():
    calc = CrossVenueArbCalculator()
    history = [
        {"venue_pair": "binance_dydx", "spread_bps": 8.0,
         "timestamp_epoch": 1000},
        {"venue_pair": "binance_dydx", "spread_bps": 10.0,
         "timestamp_epoch": 2000},
        {"venue_pair": "binance_dydx", "spread_bps": 9.0,
         "timestamp_epoch": 3000},
        {"venue_pair": "binance_hyper", "spread_bps": 12.0,
         "timestamp_epoch": 1500},
        {"venue_pair": "binance_hyper", "spread_bps": 14.0,
         "timestamp_epoch": 2500},
    ]
    results = calc.compute_persistence(history, window_minutes=60)
    assert len(results) == 2
    pair_names = {r["venue_pair"] for r in results}
    assert "binance_dydx" in pair_names
    assert "binance_hyper" in pair_names
    for r in results:
        assert "avg_spread_bps" in r
        assert "duration_seconds" in r
        assert "frequency_per_hour" in r


def test_compute_market_efficiency_score():
    calc = CrossVenueArbCalculator()
    assert calc.compute_market_efficiency_score([]) == 100.0
    opps = [
        {"spread_bps": 15.0},
        {"spread_bps": 20.0},
        {"spread_bps": 10.0},
    ]
    score = calc.compute_market_efficiency_score(opps)
    assert 0 <= score < 100.0
