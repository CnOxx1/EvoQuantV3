"""Unit tests for FundingRateModelService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.funding_rate_model.service import FundingRateModelService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create funding and basis snapshot tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FundingRateModelService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "funding_rate_snapshots" in tables
    assert "basis_snapshots" in tables


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data when DB is empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FundingRateModelService(db=db)
    service.init_storage()

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "no_data"
    assert "as_of" in result


def test_load_latest_context_bundle_with_funding_data(tmp_path):
    """load_latest_context_bundle returns ready when funding data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FundingRateModelService(db=db)
    service.init_storage()

    funding_data = {
        "current_rate": 0.0003,
        "predicted_next": 0.00025,
        "rate_zscore": 1.2,
        "rate_percentile": 75.0,
        "cumulative_7d": 0.0021,
        "direction_bias": "long_crowded",
        "mean_reversion_signal": -0.6,
    }
    now_iso = service._utc_now_iso()
    service.repository.save_funding_snapshot("BTC", funding_data, now_iso)

    result = service.load_latest_context_bundle(symbols=["BTC"])
    assert result["status"] == "ready"
    assert "market_positioning" in result
    assert "funding" in result
    assert result["coverage"]["funding_symbols"] == 1


def test_run_model_empty_market_data(tmp_path):
    """run_model returns ok with empty results when no market data."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FundingRateModelService(db=db)
    service.init_storage()

    result = service.run_model(symbols=["BTC"], save=False)
    assert result["status"] == "ok"
    assert "as_of" in result
    assert result["funding"] == {}
    assert result["basis"] == {}
