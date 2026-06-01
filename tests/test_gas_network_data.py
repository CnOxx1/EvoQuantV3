"""Unit tests for GasNetworkService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.gas_network_data.service import GasNetworkService


class StaticGasNetworkClient:
    """Static mock client returning fake gas prices, congestion, spikes."""

    def fetch_etherscan_gas_oracle(self):
        return {
            "suggestBaseFee": "35.5",
            "FastGasPrice": "42.0",
            "gasUsedRatio": "0.85,0.72,0.91",
            "LastBlock": "19500000",
        }

    def fetch_blocknative_gas(self):
        return {}

    def fetch_blocknative_mempool_stats(self):
        return {}

    def fetch_pending_tx_count(self):
        return 3500

    def fetch_etherscan_gas_history(self, startblock, endblock):
        return []

    def close(self):
        pass


def test_init_storage_creates_gas_tables(tmp_path):
    db = DBManager(str(tmp_path / "gas.sqlite"))
    service = GasNetworkService(client=StaticGasNetworkClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "gas_prices" in tables
    assert "network_congestion" in tables
    assert "gas_spikes" in tables


def test_collect_once_stores_gas_prices(tmp_path):
    db = DBManager(str(tmp_path / "gas_collect.sqlite"))
    service = GasNetworkService(client=StaticGasNetworkClient(), db=db)
    service.init_storage()
    service.collect_once()

    gas_count = db.conn.execute(
        "SELECT COUNT(*) FROM gas_prices"
    ).fetchone()[0]
    assert gas_count >= 1

    row = db.conn.execute(
        "SELECT base_fee_gwei, block_number FROM gas_prices LIMIT 1"
    ).fetchone()
    assert row[0] == 35.5
    assert row[1] == 19500000


def test_collect_once_stores_congestion(tmp_path):
    db = DBManager(str(tmp_path / "gas_congestion.sqlite"))
    service = GasNetworkService(client=StaticGasNetworkClient(), db=db)
    service.init_storage()
    service.collect_once()

    cong_count = db.conn.execute(
        "SELECT COUNT(*) FROM network_congestion"
    ).fetchone()[0]
    assert cong_count >= 1

    row = db.conn.execute(
        "SELECT pending_tx_count, congestion_level FROM network_congestion LIMIT 1"
    ).fetchone()
    assert row[0] == 3500
    assert row[1] == "high"


def test_load_latest_context_bundle_returns_gas_info(tmp_path):
    db = DBManager(str(tmp_path / "gas_bundle.sqlite"))
    service = GasNetworkService(client=StaticGasNetworkClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "current_gas" in bundle
    assert bundle["current_gas"]["base_fee_gwei"] == 35.5
    assert bundle["current_gas"]["level"] == "moderate"
    assert "congestion" in bundle
    assert bundle["congestion"]["pending_tx_count"] == 3500
