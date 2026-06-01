"""Unit tests for EtfFlowDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.etf_flow_data.service import EtfFlowDataService


class StaticMockClient:
    """Static mock client returning fake ETF flow data."""

    def fetch_etf_flows(self, asset="BTC", days=7):
        return [
            {
                "date": "2026-05-10",
                "etf_name": "iShares Bitcoin Trust",
                "ticker": "IBIT",
                "issuer": "BlackRock",
                "net_flow_usd": 250000000,
                "total_aum_usd": 18000000000,
                "shares_outstanding": 450000000,
                "price": 40.5,
                "premium_discount_pct": 0.02,
            },
            {
                "date": "2026-05-09",
                "etf_name": "Wise Origin Bitcoin Fund",
                "ticker": "FBTC",
                "issuer": "Fidelity",
                "net_flow_usd": 120000000,
                "total_aum_usd": 9500000000,
                "shares_outstanding": 200000000,
                "price": 47.8,
                "premium_discount_pct": -0.01,
            },
        ]

    def fetch_etf_aum(self, asset="BTC"):
        return [
            {"etf_name": "IBIT", "aum_usd": 18000000000},
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = EtfFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "etf_daily_flows" in tables
    assert "etf_flow_summary" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = EtfFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once()

    flow_count = db.conn.execute(
        "SELECT COUNT(*) FROM etf_daily_flows"
    ).fetchone()[0]
    summary_count = db.conn.execute(
        "SELECT COUNT(*) FROM etf_flow_summary"
    ).fetchone()[0]
    assert flow_count >= 1
    assert summary_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = EtfFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "assets" in bundle
    assert "BTC" in bundle["assets"] or "ETH" in bundle["assets"]


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = EtfFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    # When no data, assets should have no_data status
    for asset_data in bundle["assets"].values():
        assert asset_data == {"status": "no_data"}
