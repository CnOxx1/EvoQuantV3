"""Unit tests for OnchainAddressService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.onchain_address_data.service import OnchainAddressService


class StaticOnchainAddressClient:
    """Static mock client returning fake address labels, flows, whale moves."""

    def fetch_arkham_entity(self, address):
        return {
            "label": "Binance Hot Wallet",
            "entity": "Binance",
            "category": "exchange",
            "first_seen": "2020-01-01",
            "last_active": "2026-05-10",
        }

    def fetch_arkham_transfers(self, address, limit=50):
        return [
            {
                "tx_hash": f"0xabc{address[-4:]}",
                "token": "ETH",
                "amount_usd": 2500000.0,
                "counterparty": "0xdead...beef",
                "direction": "outflow",
                "timestamp": "2026-05-10T12:00:00",
            },
        ]

    def fetch_arkham_whale_alerts(self, min_usd=1_000_000):
        return [
            {
                "address": "0x28C6c06298d514Db089934071355E5743bf21d60",
                "entity": "Binance",
                "token": "ETH",
                "amount_usd": 5000000.0,
                "direction": "withdrawal",
                "from_exchange": "Binance",
                "to_exchange": "",
                "timestamp": "2026-05-10T11:00:00",
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_address_tables(tmp_path):
    db = DBManager(str(tmp_path / "addr.sqlite"))
    service = OnchainAddressService(client=StaticOnchainAddressClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "address_labels" in tables
    assert "address_flows" in tables
    assert "whale_moves" in tables


def test_collect_once_stores_whale_moves(tmp_path):
    db = DBManager(str(tmp_path / "addr_collect.sqlite"))
    service = OnchainAddressService(client=StaticOnchainAddressClient(), db=db)
    service.init_storage()
    service.collect_once()

    whale_count = db.conn.execute(
        "SELECT COUNT(*) FROM whale_moves"
    ).fetchone()[0]
    assert whale_count >= 1


def test_collect_once_stores_address_flows(tmp_path):
    db = DBManager(str(tmp_path / "addr_flows.sqlite"))
    service = OnchainAddressService(client=StaticOnchainAddressClient(), db=db)
    service.init_storage()
    service.collect_once()

    flow_count = db.conn.execute(
        "SELECT COUNT(*) FROM address_flows"
    ).fetchone()[0]
    assert flow_count >= 1


def test_load_latest_context_bundle_returns_whale_signals(tmp_path):
    db = DBManager(str(tmp_path / "addr_bundle.sqlite"))
    service = OnchainAddressService(client=StaticOnchainAddressClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "market_signals" in bundle
    assert bundle["market_signals"]["net_flow_direction"] == "net_withdrawal"
