"""Unit tests for BridgeFlowDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.bridge_flow_data.service import BridgeFlowDataService


class StaticMockClient:
    """Static mock client returning fake bridge flow data."""

    TRACKED_CHAINS = ["Ethereum", "Arbitrum", "Base"]

    def fetch_bridges_overview(self):
        return [
            {
                "displayName": "Stargate",
                "name": "stargate",
                "lastDailyVolume": 45000000,
            },
            {
                "displayName": "Across",
                "name": "across",
                "lastDailyVolume": 22000000,
            },
        ]

    def fetch_bridge_volume(self, bridge_id):
        return {"volume": 45000000, "txs": 1200}

    def fetch_chain_flows(self, chain):
        return {
            "currentDayDepositsUSD": 15000000,
            "currentDayWithdrawalsUSD": 8000000,
        }

    def fetch_chain_transactions(self, chain, limit=50):
        return [
            {"hash": "0xabc", "amount": 50000, "token": "USDC"},
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = BridgeFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "bridge_flows" in tables
    assert "chain_net_flows" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = BridgeFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(chains=StaticMockClient.TRACKED_CHAINS)

    bridge_count = db.conn.execute(
        "SELECT COUNT(*) FROM bridge_flows"
    ).fetchone()[0]
    chain_count = db.conn.execute(
        "SELECT COUNT(*) FROM chain_net_flows"
    ).fetchone()[0]
    assert bridge_count >= 1
    assert chain_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = BridgeFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(chains=StaticMockClient.TRACKED_CHAINS)

    bundle = service.load_latest_context_bundle(
        chains=StaticMockClient.TRACKED_CHAINS
    )
    assert bundle["status"] == "ready"
    assert "chain_flows" in bundle
    assert "bridge_volumes" in bundle
    assert "market_signal" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = BridgeFlowDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(
        chains=StaticMockClient.TRACKED_CHAINS
    )
    assert bundle["status"] == "no_data"
