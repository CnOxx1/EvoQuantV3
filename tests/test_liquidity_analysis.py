"""Unit tests for LiquidityAnalysisService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.liquidity_analysis.service import LiquidityAnalysisService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create liquidity analysis tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = LiquidityAnalysisService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert len(tables) > 0


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data when DB is empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = LiquidityAnalysisService(db=db)
    service.init_storage()

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "no_data"
    assert "as_of" in result


def test_load_latest_context_bundle_with_profiles(tmp_path):
    """load_latest_context_bundle returns ready when profile data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = LiquidityAnalysisService(db=db)
    service.init_storage()

    # Insert profile directly via repository
    profile = {
        "bid_depth_usd": 500000.0,
        "ask_depth_usd": 480000.0,
        "spread_bps": 1.5,
        "slippage_10k_bps": 2.0,
        "slippage_100k_bps": 5.0,
        "slippage_1m_bps": 25.0,
        "liquidity_score": 85,
    }
    now_iso = service._utc_now_iso()
    service.repository.save_profile("BTC", "binance", profile, now_iso)

    result = service.load_latest_context_bundle(symbols=["BTC"])
    assert result["status"] == "ready"
    assert "market_liquidity_state" in result
    assert "profiles" in result
    assert result["coverage"]["symbols_with_data"] == 1


def test_run_analysis_empty_market_data(tmp_path):
    """run_analysis returns ok with empty results when no market data."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = LiquidityAnalysisService(db=db)
    service.init_storage()

    result = service.run_analysis(symbols=["BTC"], save=False)
    assert result["status"] == "ok"
    assert "as_of" in result
    assert result["symbols_analyzed"] == 0
