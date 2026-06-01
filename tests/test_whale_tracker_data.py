"""Unit tests for WhaleTrackerDataService."""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.whale_tracker_data.service import WhaleTrackerDataService


def _recent_timestamp(hours_ago=0):
    """Return a unix timestamp for a recent time."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return int(dt.timestamp())


class StaticMockClient:
    """Static mock client returning fake whale transaction data."""

    def fetch_whale_alert_transactions(self, min_value_usd=500000):
        return [
            {
                "hash": "abc123def456",
                "symbol": "BTC",
                "blockchain": "bitcoin",
                "amount_usd": 2500000,
                "amount": 42.5,
                "timestamp": _recent_timestamp(1),
                "from": {"owner_type": "unknown", "address": "1A1zP1..."},
                "to": {"owner_type": "exchange", "address": "3J98t1..."},
            },
            {
                "hash": "def789ghi012",
                "symbol": "ETH",
                "blockchain": "ethereum",
                "amount_usd": 1200000,
                "amount": 350.0,
                "timestamp": _recent_timestamp(2),
                "from": {"owner_type": "exchange", "address": "0xabc..."},
                "to": {"owner_type": "unknown", "address": "0xdef..."},
            },
        ]

    def fetch_arkham_transfers(self, symbol):
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return [
            {
                "transactionHash": "0xarkham001",
                "chain": "ethereum",
                "unitValueUsd": 800000,
                "unitValue": 220.0,
                "fromAddress": "0xfrom1...",
                "toAddress": "0xto1...",
                "fromLabel": "whale_wallet",
                "toLabel": "Binance Exchange",
                "blockTimestamp": now_iso,
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = WhaleTrackerDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "whale_transactions" in tables
    assert "whale_flow_agg" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = WhaleTrackerDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC", "ETH"])

    tx_count = db.conn.execute(
        "SELECT COUNT(*) FROM whale_transactions"
    ).fetchone()[0]
    assert tx_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = WhaleTrackerDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC", "ETH"])

    bundle = service.load_latest_context_bundle(symbols=["BTC", "ETH"])
    assert bundle["status"] == "ready"
    assert "entities" in bundle
    assert "market_signal" in bundle
    assert "coverage" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = WhaleTrackerDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "no_data"
