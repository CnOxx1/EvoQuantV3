"""Unit tests for CefiLendingRateService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.cefi_lending_rate.service import CefiLendingRateService


class StaticMockClient:
    """Static mock client returning fake CeFi lending rate data."""

    def fetch_binance_lending_rates(self, asset):
        return [
            {
                "latestAnnualPercentageRate": "0.05",
                "minPurchaseAmount": "0.01",
            },
        ]

    def fetch_binance_margin_rates(self, asset):
        return {
            "nextHourlyInterestRate": "0.00002",
        }

    def fetch_okx_lending_rates(self):
        return [
            {"ccy": "BTC", "rate": "0.0001"},
            {"ccy": "ETH", "rate": "0.00015"},
            {"ccy": "USDT", "rate": "0.00012"},
        ]

    def fetch_bybit_lending_rates(self):
        return [
            {"coin": "BTC", "annualYieldRate": "0.04", "minAmount": "0.001"},
            {"coin": "ETH", "annualYieldRate": "0.035", "minAmount": "0.01"},
            {"coin": "USDT", "annualYieldRate": "0.06", "minAmount": "100"},
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = CefiLendingRateService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "cefi_lending_rates" in tables
    assert "lending_rate_spread" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = CefiLendingRateService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(assets=["BTC", "ETH", "USDT"])

    rate_count = db.conn.execute(
        "SELECT COUNT(*) FROM cefi_lending_rates"
    ).fetchone()[0]
    assert rate_count >= 3


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = CefiLendingRateService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(assets=["BTC", "ETH", "USDT"])

    bundle = service.load_latest_context_bundle(assets=["BTC", "ETH", "USDT"])
    assert bundle["status"] == "ready"
    assert "market_signal" in bundle
    assert "platform_rates" in bundle
    assert "cefi_defi_spreads" in bundle
    assert "rate_trends" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = CefiLendingRateService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(assets=["BTC"])
    assert bundle["status"] == "no_data"
