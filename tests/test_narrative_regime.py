"""Unit tests for NarrativeRegimeService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from logic_layer.narrative_regime.service import NarrativeRegimeService


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = NarrativeRegimeService(db=db)
    svc.init_storage()

    # Verify both tables exist
    tables = db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", ()
    )
    table_names = [row["name"] for row in tables]
    assert "market_narratives" in table_names
    assert "narrative_transitions" in table_names
    svc.close()


def test_load_latest_context_bundle_empty(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = NarrativeRegimeService(db=db)
    svc.init_storage()

    bundle = svc.load_latest_context_bundle()
    assert "as_of" in bundle
    assert bundle["active_narratives"] == []
    assert bundle["recent_transitions"] == []
    assert bundle["narrative_count"] == 0
    svc.close()


def test_load_latest_context_bundle_with_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    svc = NarrativeRegimeService(db=db)
    svc.init_storage()

    # Insert a narrative directly
    db.conn.execute(
        """INSERT INTO market_narratives
           (ts, narrative_id, narrative_name, lifecycle_phase,
            attention_score, capital_flow_correlation, related_tokens)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2025-01-01T00:00:00", "n1", "DeFi Summer",
         "growing", 0.85, 0.3, '["UNI","AAVE"]'),
    )
    db.conn.commit()

    bundle = svc.load_latest_context_bundle()
    assert bundle["narrative_count"] == 1
    assert len(bundle["active_narratives"]) == 1
    assert bundle["active_narratives"][0]["narrative_name"] == "DeFi Summer"
    svc.close()
