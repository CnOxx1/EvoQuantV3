"""Unit tests for AnomalyDetectionService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.anomaly_detection.service import AnomalyDetectionService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create anomaly detection tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AnomalyDetectionService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert len(tables) > 0


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data when DB is empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AnomalyDetectionService(db=db)
    service.init_storage()

    result = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert result["status"] == "no_data"
    assert "as_of" in result


def test_load_latest_context_bundle_with_anomalies(tmp_path):
    """load_latest_context_bundle returns ready when anomaly data exists."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AnomalyDetectionService(db=db)
    service.init_storage()

    # Insert anomaly directly via repository
    anomaly = {
        "type": "price_spike",
        "severity": "critical",
        "score": 0.95,
        "description": "Abnormal price movement detected",
        "metric_name": "return_zscore",
        "metric_value": 3.5,
        "threshold": 3.0,
        "zscore": 3.5,
    }
    now_iso = service._utc_now_iso()
    service.repository.save_anomaly("BTC", anomaly, now_iso)

    result = service.load_latest_context_bundle(symbols=["BTC"])
    assert result["status"] == "ready"
    assert "market_risk_level" in result
    assert "summary" in result
    assert result["summary"]["total_anomalies"] >= 1


def test_run_detection_empty_market_data(tmp_path):
    """run_detection returns ok with empty results when no market data."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AnomalyDetectionService(db=db)
    service.init_storage()

    result = service.run_detection(symbols=["BTC"], save=False)
    assert result["status"] == "ok"
    assert "as_of" in result
    assert result["total_anomalies"] == 0
