"""Unit tests for AlphaDecayService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.alpha_decay.service import AlphaDecayService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create signal_decay and crowding_index tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AlphaDecayService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "signal_decay" in tables
    assert "crowding_index" in tables


def test_init_storage_is_idempotent(tmp_path):
    """Calling init_storage twice should not raise."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AlphaDecayService(db=db)
    service.init_storage()
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_decay'"
    )
    assert cursor.fetchone() is not None


def test_load_latest_context_bundle_empty(tmp_path):
    """load_latest_context_bundle returns structure with empty data when no records."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = AlphaDecayService(db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert "as_of" in bundle
    assert "signal_decay" in bundle
    assert "crowding_index" in bundle
    assert bundle["signal_decay"] == []
    assert bundle["crowding_index"] is None
