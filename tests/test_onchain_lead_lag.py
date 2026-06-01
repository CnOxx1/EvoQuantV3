"""Unit tests for OnchainLeadLagCalculator."""

import sys
import math
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logic_layer.onchain_lead_lag.calculator import OnchainLeadLagCalculator


def _generate_lagged_series(n=50, lag=3):
    """Generate a signal series that leads a price series by lag periods."""
    random.seed(42)
    signal = [math.sin(i * 0.3) + random.gauss(0, 0.1) for i in range(n)]
    price = [0.0] * n
    for i in range(lag, n):
        price[i] = signal[i - lag] * 0.8 + random.gauss(0, 0.05)
    return signal, price


def test_compute_cross_correlation_returns_lag_entries():
    calc = OnchainLeadLagCalculator()
    signal, price = _generate_lagged_series(n=50, lag=3)
    results = calc.compute_cross_correlation(signal, price, max_lag=10)
    assert len(results) > 0
    for entry in results:
        assert "lag" in entry
        assert "correlation" in entry
        assert -1.0 <= entry["correlation"] <= 1.0


def test_find_optimal_lag_detects_correct_lag():
    calc = OnchainLeadLagCalculator()
    signal, price = _generate_lagged_series(n=60, lag=3)
    result = calc.find_optimal_lag(signal, price, max_lag=10)
    assert "optimal_lag" in result
    assert "correlation" in result
    assert "direction" in result
    assert abs(result["optimal_lag"] - 3) <= 2


def test_compute_granger_causality_returns_f_stat():
    calc = OnchainLeadLagCalculator()
    signal, price = _generate_lagged_series(n=80, lag=3)
    result = calc.compute_granger_causality(signal, price, max_lag=4)
    assert "f_stat" in result
    assert "p_value_approx" in result
    assert "significant" in result
    assert result["f_stat"] >= 0.0
    assert 0.0 <= result["p_value_approx"] <= 1.0


def test_detect_signal_trigger_fires_on_extreme_value():
    calc = OnchainLeadLagCalculator()
    values = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.3, 9.7, 10.1, 10.0,
              10.2, 9.9, 10.0, 10.1, 9.8, 15.0]
    assert calc.detect_signal_trigger(values, threshold_sigma=2.0) is True
    normal_values = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0, 10.3, 9.7,
                     10.1, 10.0, 10.2, 9.9, 10.0, 10.1, 9.8, 10.05]
    assert calc.detect_signal_trigger(normal_values, threshold_sigma=2.0) is False
