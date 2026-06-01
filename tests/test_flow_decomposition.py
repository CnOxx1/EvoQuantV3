"""Unit tests for FlowDecompositionService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.flow_decomposition.service import FlowDecompositionService


def test_init_storage_creates_tables(tmp_path):
    """init_storage should create flow decomposition tables."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FlowDecompositionService(db=db)
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    assert "flow_decomposition" in tables or "vpin_alerts" in tables


def test_init_storage_is_idempotent(tmp_path):
    """Calling init_storage twice should not raise."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FlowDecompositionService(db=db)
    service.init_storage()
    service.init_storage()

    cursor = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    assert len(cursor.fetchall()) > 0


def test_load_latest_context_bundle_empty(tmp_path):
    """load_latest_context_bundle returns structure with empty decompositions."""
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = FlowDecompositionService(db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert "as_of" in bundle
    assert "decompositions" in bundle
    assert isinstance(bundle["decompositions"], dict)
    assert len(bundle["decompositions"]) == 0
