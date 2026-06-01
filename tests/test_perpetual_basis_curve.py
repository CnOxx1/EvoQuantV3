"""Unit tests for PerpBasisCurveService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.perpetual_basis_curve.service import PerpetualBasisCurveService


class StaticMockClient:
    """Static mock client returning fake basis curve data."""

    def fetch_spot_price(self, symbol="BTCUSDT"):
        prices = {
            "BTCUSDT": 67000.0,
            "ETHUSDT": 3800.0,
            "SOLUSDT": 170.0,
            "BNBUSDT": 600.0,
        }
        return prices.get(symbol, 67000.0)

    def fetch_binance_futures_prices(self, symbol="BTCUSDT"):
        return [
            {"markPrice": "67150.5", "symbol": symbol},
        ]

    def fetch_binance_delivery_prices(self, pair="BTCUSD"):
        return [
            {
                "markPrice": "67400.0",
                "symbol": f"{pair}_250627",
            },
        ]

    def fetch_okx_futures_prices(self, inst_type="FUTURES"):
        return [
            {"instId": "BTC-USDT-250627", "last": "67350.0"},
            {"instId": "ETH-USDT-250627", "last": "3820.0"},
        ]

    def fetch_bybit_futures_prices(self, category="linear"):
        return [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "67200.0",
                "deliveryTime": "0",
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = PerpetualBasisCurveService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "futures_term_structure" in tables
    assert "basis_curve_snapshot" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = PerpetualBasisCurveService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTCUSDT"])

    term_count = db.conn.execute(
        "SELECT COUNT(*) FROM futures_term_structure"
    ).fetchone()[0]
    snapshot_count = db.conn.execute(
        "SELECT COUNT(*) FROM basis_curve_snapshot"
    ).fetchone()[0]
    assert term_count >= 1
    assert snapshot_count >= 1


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = PerpetualBasisCurveService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTCUSDT"])

    bundle = service.load_latest_context_bundle(symbols=["BTCUSDT"])
    assert bundle["status"] == "ready"
    assert "market_structure" in bundle
    assert "entities" in bundle
    assert "BTCUSDT" in bundle["entities"]


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = PerpetualBasisCurveService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(symbols=["BTCUSDT"])
    assert bundle["status"] == "no_data"
