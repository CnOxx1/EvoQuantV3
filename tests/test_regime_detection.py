"""Unit tests for RegimeDetectionService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.regime_detection.service import RegimeDetectionService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create regime_states and regime_transitions tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegimeDetectionService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "regime_states" in tables
    assert "regime_transitions" in tables


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data when DB is empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegimeDetectionService(db=db)
    service.init_storage()

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "no_data"
    assert "as_of" in result


def test_load_latest_context_bundle_with_data(tmp_path):
    """load_latest_context_bundle returns ready when regime data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegimeDetectionService(db=db)
    service.init_storage()

    # Insert regime state directly via repository
    service.repository.save_regime_state(
        "BTC", "trending_up", 0.85, 12,
        "normal", "high_corr", "bullish", "2025-01-01T00:00:00"
    )
    service.repository.save_regime_state(
        "ETH", "ranging", 0.6, 5,
        "low", "moderate_corr", "neutral", "2025-01-01T00:00:00"
    )

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "ready"
    assert "market_phase" in result
    assert "entities" in result
    assert result["coverage"]["symbols_with_data"] == 2


def test_run_detection_empty_market_data(tmp_path):
    """run_detection returns ok with empty results when no market data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegimeDetectionService(db=db)
    service.init_storage()

    result = service.run_detection(symbols=["BTC"], save=False)
    assert result["status"] == "ok"
    assert "as_of" in result
    assert result["results"] == {}
