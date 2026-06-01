"""Unit tests for MevDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.mev_data.service import MevDataService


class StaticMockClient:
    """Static mock client returning fake MEV data."""

    def fetch_flashbots_blocks(self, limit=100):
        return [
            {
                "block_number": 19000001,
                "slot": "",
                "value": 50000000000000000,
                "builder_pubkey": "0xabcdef1234567890abcdef",
            },
            {
                "block_number": 19000002,
                "slot": "",
                "value": 75000000000000000,
                "builder_pubkey": "0x1234567890abcdef1234ab",
            },
        ]

    def fetch_eigenphi_mev_summary(self, timeframe="1h"):
        return {
            "totalMev": "125000",
            "sandwichCount": 42,
            "arbCount": 18,
        }

    def fetch_eigenphi_sandwich(self, limit=50):
        return [
            {"tx_hash": "0xaaa", "profit_usd": 1200},
            {"tx_hash": "0xbbb", "profit_usd": 800},
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = MevDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "mev_blocks" in tables
    assert "mev_agg" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = MevDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once()

    block_count = db.conn.execute(
        "SELECT COUNT(*) FROM mev_blocks"
    ).fetchone()[0]
    assert block_count >= 2


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = MevDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "market_signals" in bundle
    assert "aggregations" in bundle
    assert "interpretation" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = MevDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "no_data"
