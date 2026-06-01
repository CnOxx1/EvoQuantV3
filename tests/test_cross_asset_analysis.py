"""Unit tests for CrossAssetAnalysisService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = CrossAssetAnalysisService(db=db)
    svc.init_storage()

    tables = db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    )
    table_names = [row["name"] for row in tables]
    assert "cross_asset_correlation_snapshots" in table_names
    assert "cross_asset_relative_strength" in table_names
    assert "cross_asset_sector_rotation" in table_names
    assert "cross_asset_fund_flow" in table_names
    svc.close()


def test_load_latest_context_bundle_empty(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = CrossAssetAnalysisService(db=db)
    svc.init_storage()

    bundle = svc.load_latest_context_bundle()
    assert "as_of" in bundle
    assert bundle["correlation"] is None
    assert bundle["correlation_regime"] == "unknown"
    svc.close()


def test_load_latest_context_bundle_with_correlation(tmp_path):
    import json

    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = CrossAssetAnalysisService(db=db)
    svc.init_storage()

    # Insert a correlation snapshot directly
    matrix = {"BTC/USDT": {"BTC/USDT": 1.0, "ETH/USDT": 0.8},
              "ETH/USDT": {"BTC/USDT": 0.8, "ETH/USDT": 1.0}}
    db.conn.execute(
        """INSERT INTO cross_asset_correlation_snapshots
           (snapshot_time, window_hours, matrix_json, symbols_json,
            avg_correlation, max_correlation, min_correlation)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2025-01-01T00:00:00", 168, json.dumps(matrix),
         json.dumps(["BTC/USDT", "ETH/USDT"]), 0.8, 0.8, 0.8),
    )
    db.conn.commit()

    bundle = svc.load_latest_context_bundle()
    assert bundle["correlation"] is not None
    assert bundle["correlation"]["avg_correlation"] == 0.8
    assert bundle["correlation_regime"] == "high_correlation"
    svc.close()


def test_classify_correlation_regime_thresholds():
    classify = CrossAssetAnalysisService._classify_correlation_regime
    assert classify(None) == "unknown"
    assert classify({"avg_correlation": 0.75}) == "high_correlation"
    assert classify({"avg_correlation": 0.5}) == "moderate_correlation"
    assert classify({"avg_correlation": 0.2}) == "low_correlation"
    assert classify({"avg_correlation": 0.05}) == "decorrelated"
