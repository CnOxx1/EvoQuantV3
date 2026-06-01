"""Unit tests for DefiProtocolDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.defi_protocol_data.service import DefiProtocolDataService


class StaticMockClient:
    """Static mock client returning fake DeFi protocol data."""

    TRACKED_PROTOCOLS = ["aave-v3", "uniswap", "lido"]

    def fetch_all_protocols_tvl(self):
        return [
            {
                "slug": "aave-v3",
                "tvl": 12000000000,
                "change_1d": 1.5,
                "change_7d": 3.2,
                "chain": "Ethereum",
            },
            {
                "slug": "uniswap",
                "tvl": 5000000000,
                "change_1d": -0.8,
                "change_7d": 2.1,
                "chain": "Multi",
            },
            {
                "slug": "lido",
                "tvl": 15000000000,
                "change_1d": 0.3,
                "change_7d": 1.0,
                "chain": "Ethereum",
            },
        ]

    def fetch_yields_pools(self):
        return [
            {
                "project": "aave-v3",
                "symbol": "USDC",
                "chain": "Ethereum",
                "apy": 3.5,
                "apyBorrow": 4.2,
                "tvlUsd": 2000000000,
            },
            {
                "project": "compound-v3",
                "symbol": "WETH",
                "chain": "Ethereum",
                "apy": 1.8,
                "apyBorrow": 2.5,
                "tvlUsd": 800000000,
            },
        ]

    def fetch_dex_overview(self):
        return {
            "protocols": [
                {
                    "name": "Uniswap",
                    "total24h": 1500000000,
                    "change_1d": 5.2,
                },
                {
                    "name": "Curve",
                    "total24h": 300000000,
                    "change_1d": -2.1,
                },
            ]
        }

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = DefiProtocolDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "defi_tvl" in tables
    assert "defi_lending_rates" in tables
    assert "defi_dex_volume" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = DefiProtocolDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(protocols=["aave-v3", "uniswap", "lido"])

    tvl_count = db.conn.execute(
        "SELECT COUNT(*) FROM defi_tvl"
    ).fetchone()[0]
    lending_count = db.conn.execute(
        "SELECT COUNT(*) FROM defi_lending_rates"
    ).fetchone()[0]
    assert tvl_count >= 2
    assert lending_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = DefiProtocolDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(protocols=["aave-v3", "uniswap", "lido"])

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "tvl" in bundle
    assert "lending" in bundle
    assert "dex" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = DefiProtocolDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "no_data"
