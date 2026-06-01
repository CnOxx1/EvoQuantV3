"""Unit tests for VolatilityForecastService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.volatility_forecast.service import VolatilityForecastService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create volatility_snapshots and volatility_cone tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = VolatilityForecastService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "volatility_snapshots" in tables
    assert "volatility_cone" in tables


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data when DB is empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = VolatilityForecastService(db=db)
    service.init_storage()

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "no_data"
    assert "as_of" in result


def test_load_latest_context_bundle_with_snapshots(tmp_path):
    """load_latest_context_bundle returns ready when snapshot data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = VolatilityForecastService(db=db)
    service.init_storage()

    snapshot = {
        "realized_vol_1d": 0.025,
        "realized_vol_7d": 0.032,
        "realized_vol_30d": 0.045,
        "implied_vol": 0.05,
        "rv_iv_spread": -0.005,
        "vol_regime": "normal",
        "forecast_1d": 0.028,
        "forecast_7d": 0.035,
        "vol_percentile": 55.0,
    }
    now_iso = service._utc_now_iso()
    service.repository.save_snapshot("BTC", snapshot, now_iso)

    result = service.load_latest_context_bundle(symbols=["BTC"])
    assert result["status"] == "ready"
    assert "market_volatility_state" in result
    assert "entities" in result
    assert result["coverage"]["symbols_with_data"] == 1


def test_run_forecast_empty_market_data(tmp_path):
    """run_forecast returns ok with empty results when no market data."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = VolatilityForecastService(db=db)
    service.init_storage()

    result = service.run_forecast(symbols=["BTC"], save=False)
    assert result["status"] == "ok"
    assert "as_of" in result
    assert result["results"] == {}
