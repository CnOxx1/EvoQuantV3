"""API v3 端点单元测试。

Mock 数据库层（路由模块中引用的 DB getter），验证路由逻辑。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def mock_dbs():
    """Patch DB getters at the router module level where they are imported."""
    exchange_db = MagicMock(name="exchange_db")
    market_db = MagicMock(name="market_db")
    analytics_db = MagicMock(name="analytics_db")

    patches = [
        # v3_system imports all three
        patch("api.routers.v3_system.get_exchange_db", return_value=exchange_db),
        patch("api.routers.v3_system.get_market_db", return_value=market_db),
        patch("api.routers.v3_system.get_analytics_db", return_value=analytics_db),
        # v3_market imports exchange + market + analytics
        patch("api.routers.v3_market.get_exchange_db", return_value=exchange_db),
        patch("api.routers.v3_market.get_market_db", return_value=market_db),
        patch("api.routers.v3_market.get_analytics_db", return_value=analytics_db),
        # v3_technical imports analytics only
        patch("api.routers.v3_technical.get_analytics_db", return_value=analytics_db),
    ]

    for p in patches:
        p.start()
    yield {
        "exchange": exchange_db,
        "market": market_db,
        "analytics": analytics_db,
    }
    for p in patches:
        p.stop()


@pytest.fixture
def client(mock_dbs):
    from api.app import app
    return TestClient(app)


class TestSystemHealth:
    """GET /system/health — DB 连通性检查。"""

    def test_health_all_ok(self, client, mock_dbs):
        for db in mock_dbs.values():
            db.fetch_one.return_value = (1,)

        resp = client.get("/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert all(v == "ok" for v in data["databases"].values())

    def test_health_degraded(self, client, mock_dbs):
        mock_dbs["exchange"].fetch_one.return_value = (1,)
        mock_dbs["market"].fetch_one.side_effect = Exception("connection refused")
        mock_dbs["analytics"].fetch_one.return_value = (1,)

        resp = client.get("/system/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert "error" in data["databases"]["market"]


class TestSystemStatus:
    """GET /system/status — 域可用性扫描。"""

    def test_status_with_data(self, client, mock_dbs):
        for db in mock_dbs.values():
            db.fetch_one.return_value = (1,)

        resp = client.get("/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["active"] > 0
        assert data["summary"]["total"] == data["summary"]["active"] + data["summary"]["empty"]
        assert "klines" in data["domains"]

    def test_status_empty_tables(self, client, mock_dbs):
        for db in mock_dbs.values():
            db.fetch_one.return_value = None

        resp = client.get("/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["active"] == 0
        assert all(v == "empty" for v in data["domains"].values())


class TestTechnicalIndicators:
    """GET /technical/indicators/{symbol} — 符号校验 + 查询。"""

    def test_valid_symbol(self, client, mock_dbs):
        mock_dbs["analytics"].fetch_all.return_value = [
            {"open_time": "2025-05-20T12:00:00", "rsi_14": 55.2, "macd": 0.003}
        ]

        resp = client.get("/technical/indicators/BTC")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "BTC/USDT"
        assert data["timeframe"] == "1h"

    def test_symbol_with_dash(self, client, mock_dbs):
        mock_dbs["analytics"].fetch_all.return_value = [
            {"open_time": "2025-05-20T12:00:00", "rsi_14": 40.0}
        ]

        resp = client.get("/technical/indicators/ETH-USDT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "ETH/USDT"

    def test_invalid_symbol_404(self, client, mock_dbs):
        resp = client.get("/technical/indicators/FAKECOIN123")
        assert resp.status_code == 404
        assert "not in universe" in resp.json()["detail"]

    def test_invalid_timeframe_400(self, client, mock_dbs):
        resp = client.get("/technical/indicators/BTC?timeframe=2h")
        assert resp.status_code == 400
        assert "timeframe" in resp.json()["detail"].lower()


class TestMarketTickers:
    """GET /market/tickers — 基本行情查询。"""

    def test_tickers_all(self, client, mock_dbs):
        mock_dbs["exchange"].fetch_all.return_value = [
            {"symbol": "BTC/USDT", "exchange": "binance", "price": 67000.0,
             "volume_24h": 1e9, "change_pct_24h": 2.1, "timestamp": "2025-05-20T12:00:00"},
        ]

        resp = client.get("/market/tickers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["tickers"][0]["symbol"] == "BTC/USDT"

    def test_tickers_by_symbol(self, client, mock_dbs):
        mock_dbs["exchange"].fetch_all.return_value = [
            {"symbol": "ETH/USDT", "exchange": "okx", "price": 3400.0,
             "volume_24h": 5e8, "change_pct_24h": -0.5, "timestamp": "2025-05-20T12:00:00"},
        ]

        resp = client.get("/market/tickers?symbol=ETH")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_tickers_empty_404(self, client, mock_dbs):
        mock_dbs["exchange"].fetch_all.return_value = []

        resp = client.get("/market/tickers")
        assert resp.status_code == 404
        assert "No ticker data" in resp.json()["detail"]


class TestNotFoundScenarios:
    """404 场景 — 无效符号、空数据表。"""

    def test_data_quality_empty(self, client, mock_dbs):
        mock_dbs["analytics"].fetch_one.return_value = None

        resp = client.get("/system/data-quality")
        assert resp.status_code == 404
        assert "No data quality" in resp.json()["detail"]

    def test_market_structure_empty(self, client, mock_dbs):
        mock_dbs["analytics"].fetch_one.return_value = None

        resp = client.get("/system/market-structure")
        assert resp.status_code == 200 or resp.status_code == 404

    def test_unknown_route(self, client, mock_dbs):
        resp = client.get("/nonexistent/path")
        assert resp.status_code == 404
