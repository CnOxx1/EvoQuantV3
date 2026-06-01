"""Unit tests for LiquidationCascadeCalculator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic_layer.liquidation_cascade.calculator import LiquidationCascadeCalculator


SAMPLE_POSITIONS = [
    {"liquidation_price": 58000, "size_usd": 500000,
     "leverage": 10, "direction": "long"},
    {"liquidation_price": 57500, "size_usd": 300000,
     "leverage": 20, "direction": "long"},
    {"liquidation_price": 57800, "size_usd": 200000,
     "leverage": 15, "direction": "long"},
    {"liquidation_price": 63000, "size_usd": 400000,
     "leverage": 10, "direction": "short"},
    {"liquidation_price": 64000, "size_usd": 250000,
     "leverage": 5, "direction": "short"},
]

CURRENT_PRICE = 60000.0


def test_compute_liquidation_clusters_groups_by_direction():
    calc = LiquidationCascadeCalculator()
    clusters = calc.compute_liquidation_clusters(
        SAMPLE_POSITIONS, CURRENT_PRICE, bins=5
    )
    assert len(clusters) > 0
    directions = {c["direction"] for c in clusters}
    assert "long" in directions
    assert "short" in directions
    for c in clusters:
        assert "price_level" in c
        assert "total_size_usd" in c
        assert "distance_pct" in c
        assert c["distance_pct"] >= 0


def test_compute_cascade_probability_near_price_is_higher():
    calc = LiquidationCascadeCalculator()
    prob_near = calc.compute_cascade_probability(
        cluster_size_usd=5_000_000,
        daily_volume_usd=50_000_000,
        distance_pct=1.0,
    )
    prob_far = calc.compute_cascade_probability(
        cluster_size_usd=5_000_000,
        daily_volume_usd=50_000_000,
        distance_pct=10.0,
    )
    assert 0 <= prob_near <= 1
    assert 0 <= prob_far <= 1
    assert prob_near > prob_far


def test_compute_cascade_severity_returns_valid_levels():
    calc = LiquidationCascadeCalculator()
    severity_high = calc.compute_cascade_severity(
        cascade_prob=0.9,
        cluster_size_usd=10_000_000,
        open_interest_usd=50_000_000,
    )
    severity_low = calc.compute_cascade_severity(
        cascade_prob=0.1,
        cluster_size_usd=100_000,
        open_interest_usd=500_000_000,
    )
    assert severity_high in ("critical", "high", "medium", "low")
    assert severity_low in ("critical", "high", "medium", "low")
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    assert severity_order[severity_high] >= severity_order[severity_low]


def test_compute_heatmap_returns_bins_with_pressure():
    calc = LiquidationCascadeCalculator()
    heatmap = calc.compute_heatmap(
        SAMPLE_POSITIONS, CURRENT_PRICE, range_pct=10.0, bins=10
    )
    assert len(heatmap) == 10
    for entry in heatmap:
        assert "price_from" in entry
        assert "price_to" in entry
        assert "long_liq_usd" in entry
        assert "short_liq_usd" in entry
        assert "net_pressure" in entry
    total_liq = sum(e["long_liq_usd"] + e["short_liq_usd"] for e in heatmap)
    assert total_liq > 0
