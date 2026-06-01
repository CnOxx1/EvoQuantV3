"""Unit tests for OrderflowDataService."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.orderflow_data.service import OrderflowDataService


def _recent_iso(minutes_ago=0):
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class StaticMockClient:
    """Static mock client returning fake orderflow trade data."""

    def fetch_recent_trades_binance(self, symbol):
        return [
            {
                "time": _recent_iso(5),
                "price": 60000.0,
                "quantity": 0.5,
                "is_buyer_maker": False,
                "trade_id": "bn_001",
            },
            {
                "time": _recent_iso(4),
                "price": 60010.0,
                "quantity": 1.2,
                "is_buyer_maker": True,
                "trade_id": "bn_002",
            },
        ]

    def fetch_recent_trades_bybit(self, symbol):
        return [
            {
                "time": _recent_iso(3),
                "price": 60005.0,
                "quantity": 0.8,
                "is_buyer_maker": False,
                "trade_id": "bb_001",
            },
        ]

    def fetch_recent_trades_okx(self, symbol):
        return [
            {
                "time": _recent_iso(2),
                "price": 59995.0,
                "quantity": 2.0,
                "is_buyer_maker": True,
                "trade_id": "okx_001",
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = OrderflowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "orderflow_trades" in tables
    assert "orderflow_agg" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = OrderflowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC"])

    trade_count = db.conn.execute(
        "SELECT COUNT(*) FROM orderflow_trades"
    ).fetchone()[0]
    assert trade_count >= 3


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = OrderflowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC"])

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "ready"
    assert "summaries" in bundle
    assert "coverage" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = OrderflowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "no_data"
