"""Unit tests for RegulatoryDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.regulatory_data.service import RegulatoryDataService


class StaticMockClient:
    """Static mock client returning fake regulatory data."""

    def fetch_regulatory_news(self, categories="Regulation"):
        return [
            {
                "title": "SEC Approves New Bitcoin ETF Framework",
                "body": "The SEC has approved a new framework for Bitcoin ETF applications in the United States.",
                "url": "https://example.com/sec-btc-etf",
                "published_on": 1717200000,
            },
            {
                "title": "EU MiCA Regulation Takes Effect",
                "body": "Europe's MiCA regulation is now fully enforced across all member states.",
                "url": "https://example.com/mica-eu",
                "published_on": 1717100000,
            },
        ]

    def fetch_sec_filings(self, search_term="crypto", form_type=""):
        return [
            {
                "_source": {
                    "file_description": "Crypto Asset Filing",
                    "file_date": "2026-05-10",
                },
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegulatoryDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "regulatory_events" in tables
    assert "etf_tracker" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegulatoryDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once()

    event_count = db.conn.execute(
        "SELECT COUNT(*) FROM regulatory_events"
    ).fetchone()[0]
    assert event_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegulatoryDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.bootstrap()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "risk_signal" in bundle
    assert "recent_events" in bundle
    assert "etf_tracker" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = RegulatoryDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "no_data"
