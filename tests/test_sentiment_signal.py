"""Unit tests for SentimentSignalService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.sentiment_signal.service import SentimentSignalService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create sentiment_signals and causality_results tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SentimentSignalService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "sentiment_signals" in tables
    assert "causality_results" in tables


def test_init_storage_is_idempotent(tmp_path):
    """Calling init_storage twice should not raise."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SentimentSignalService(db=db)
    service.init_storage()
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sentiment_signals'"
    )
    assert cursor.fetchone() is not None


def test_load_latest_context_bundle_no_data(tmp_path):
    """load_latest_context_bundle returns no_data status when tables are empty."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SentimentSignalService(db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "no_data"
    assert "as_of" in bundle
