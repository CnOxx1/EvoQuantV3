"""Unit tests for DexLiquidityService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.dex_liquidity_data.service import DexLiquidityService


class StaticDexLiquidityClient:
    """Static mock client returning fake pool data, ticks, events."""

    def fetch_uniswap_pools(self, first=50):
        return [
            {
                "id": "0xpool1",
                "token0": {"symbol": "WETH"},
                "token1": {"symbol": "USDC"},
                "totalValueLockedUSD": "50000000",
                "volumeUSD": "12000000",
                "feeTier": "3000",
            },
        ]

    def fetch_uniswap_pool_ticks(self, pool_id, first=100):
        return [
            {"tickIdx": "200400", "liquidityGross": "5000000",
             "price0": "1800.5", "price1": "0.000555"},
        ]

    def fetch_uniswap_mints_burns(self, pool_id, first=50):
        return {
            "mints": [
                {
                    "transaction": {"id": f"0xmint_{pool_id}"},
                    "sender": "0xuser1",
                    "amountUSD": "250000",
                    "timestamp": "2026-05-10T10:00:00",
                },
            ],
            "burns": [],
        }

    def fetch_curve_pools(self, first=50):
        return [
            {
                "id": "0xcurve1",
                "name": "3pool",
                "coins": ["DAI", "USDC", "USDT"],
                "totalValueLockedUSD": "20000000",
                "volumeUSD": "5000000",
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_dex_tables(tmp_path):
    db = DBManager(str(tmp_path / "dex.sqlite"))
    service = DexLiquidityService(client=StaticDexLiquidityClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "dex_pools" in tables
    assert "dex_tick_liquidity" in tables
    assert "dex_liquidity_events" in tables


def test_collect_once_stores_pool_data(tmp_path):
    db = DBManager(str(tmp_path / "dex_collect.sqlite"))
    service = DexLiquidityService(client=StaticDexLiquidityClient(), db=db)
    service.init_storage()
    service.collect_once()

    pool_count = db.conn.execute(
        "SELECT COUNT(*) FROM dex_pools"
    ).fetchone()[0]
    tick_count = db.conn.execute(
        "SELECT COUNT(*) FROM dex_tick_liquidity"
    ).fetchone()[0]
    assert pool_count >= 2
    assert tick_count >= 1


def test_collect_once_stores_liquidity_events(tmp_path):
    db = DBManager(str(tmp_path / "dex_events.sqlite"))
    service = DexLiquidityService(client=StaticDexLiquidityClient(), db=db)
    service.init_storage()
    service.collect_once()

    event_count = db.conn.execute(
        "SELECT COUNT(*) FROM dex_liquidity_events"
    ).fetchone()[0]
    assert event_count >= 1


def test_load_latest_context_bundle_returns_tvl_distribution(tmp_path):
    db = DBManager(str(tmp_path / "dex_bundle.sqlite"))
    service = DexLiquidityService(client=StaticDexLiquidityClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "tvl_distribution" in bundle
    assert "market_signals" in bundle
    assert "top5_tvl_ratio" in bundle["market_signals"]
