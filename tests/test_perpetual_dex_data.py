"""Unit tests for PerpDexDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.perpetual_dex_data.service import PerpDexDataService


class StaticPerpDexClient:
    """Static mock client returning fake funding/volume data."""

    def fetch_dydx_markets(self):
        return [
            {
                "ticker": "BTC-USD",
                "nextFundingRate": "0.000125",
                "openInterest": "500",
                "oraclePrice": "60000",
                "volume24H": "15000000",
                "trades24H": "4200",
            },
        ]

    def fetch_dydx_funding(self, symbol):
        return [{"rate": "0.000125", "effectiveAt": "2026-05-10T08:00:00Z"}]

    def fetch_hyperliquid_meta(self):
        return {}

    def fetch_hyperliquid_open_interest(self):
        return [
            {"universe": [{"name": "ETH"}]},
            [{"funding": "0.0003", "openInterest": "10000", "markPx": "3800", "dayNtlVlm": "8000000"}],
        ]

    def fetch_hyperliquid_funding(self):
        return []

    def fetch_gmx_positions(self):
        return []

    def fetch_gmx_funding(self):
        return [{"symbol": "BTC", "fundingRate": "0.0002", "openInterest": "25000000"}]

    def close(self):
        pass


def test_init_storage_creates_perp_tables(tmp_path):
    db = DBManager(str(tmp_path / "perp.sqlite"))
    service = PerpDexDataService(client=StaticPerpDexClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "perp_dex_funding" in tables
    assert "perp_dex_volume" in tables


def test_collect_once_stores_funding_and_volume(tmp_path):
    db = DBManager(str(tmp_path / "perp_collect.sqlite"))
    service = PerpDexDataService(client=StaticPerpDexClient(), db=db)
    service.init_storage()
    service.collect_once()

    funding_count = db.conn.execute(
        "SELECT COUNT(*) FROM perp_dex_funding"
    ).fetchone()[0]
    volume_count = db.conn.execute(
        "SELECT COUNT(*) FROM perp_dex_volume"
    ).fetchone()[0]
    assert funding_count >= 2
    assert volume_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "perp_bundle.sqlite"))
    service = PerpDexDataService(client=StaticPerpDexClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "market_signals" in bundle
    assert "funding_rate_comparison" in bundle["market_signals"]
    assert "oi_by_exchange" in bundle["market_signals"]


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "perp_empty.sqlite"))
    service = PerpDexDataService(client=StaticPerpDexClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "no_data"
