"""API 端点单元测试。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# 确保项目根目录在 sys.path 最前面
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def client():
    from api.app import app
    return TestClient(app)


class TestSymbolsEndpoint:
    def test_get_symbols(self, client):
        resp = client.get("/symbols")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 18
        assert len(data["symbols"]) == 18
        first = data["symbols"][0]
        assert first["symbol"] == "BTC/USDT"
        assert first["tier"] == "core"
        assert first["sector"] == "store_of_value"


class TestBundleEndpoint:
    @patch("api.routers.bundle.get_ai_market_context_service")
    def test_get_bundle_success(self, mock_get_svc, client):
        mock_svc = MagicMock()
        mock_svc.build_bundle_for_entity.return_value = {
            "entity": "BTC/USDT",
            "data_quality_flag": "ok",
            "coverage_score": 0.85,
            "world_model_index": {"wmi": 0.7},
        }
        mock_get_svc.return_value = mock_svc

        resp = client.get("/bundle/BTC-USDT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity"] == "BTC/USDT"

    def test_get_bundle_not_found(self, client):
        resp = client.get("/bundle/FAKE-USDT")
        assert resp.status_code == 404

    @patch("api.routers.bundle.get_ai_market_context_service")
    def test_get_bundle_summary(self, mock_get_svc, client):
        mock_svc = MagicMock()
        mock_svc.build_bundle_for_entity.return_value = {
            "data_quality_flag": "ok",
            "coverage_score": 0.9,
            "world_model_index": {"wmi": 0.75},
        }
        mock_get_svc.return_value = mock_svc

        resp = client.get("/bundle/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 18
        assert "BTC/USDT" in data["symbols"]


class TestDomainsEndpoint:
    @patch("api.routers.domains.get_pipeline_latency_service")
    def test_list_domains(self, mock_get_svc, client):
        @dataclass
        class FakeDL:
            status: str = "fresh"
            latest_data_time: str = "2025-05-20T12:00:00"
            latency_seconds: float = 60.0

        @dataclass
        class FakeReport:
            measured_at: str = "2025-05-20T12:05:00"
            domains: dict = field(default_factory=lambda: {"klines": FakeDL()})
            summary: dict = field(default_factory=dict)

        mock_svc = MagicMock()
        mock_svc.measure_all.return_value = FakeReport()
        mock_get_svc.return_value = mock_svc

        resp = client.get("/domains/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["domains"]) > 0
        names = [d["name"] for d in data["domains"]]
        assert "klines" in names


class TestHealthEndpoint:
    @patch("api.routers.health.get_ai_market_context_service")
    @patch("api.routers.health.get_pipeline_latency_service")
    def test_health(self, mock_latency, mock_ai, client):
        @dataclass
        class FakeReport:
            measured_at: str = "2025-05-20T12:05:00"
            domains: dict = field(default_factory=dict)
            summary: dict = field(
                default_factory=lambda: {"health": "healthy"}
            )

        mock_latency_svc = MagicMock()
        mock_latency_svc.measure_all.return_value = FakeReport()
        mock_latency.return_value = mock_latency_svc

        mock_ai_svc = MagicMock()
        mock_ai_svc.build_bundle_for_entity.return_value = {
            "world_model_index": {
                "wmi": 0.8,
                "interpretation": "sufficient",
                "should_ai_abstain": False,
            }
        }
        mock_ai.return_value = mock_ai_svc

        resp = client.get("/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


class TestTimeSliceEndpoint:
    @patch("api.routers.time_slice.get_time_slice_service")
    def test_time_slice(self, mock_get_svc, client):
        @dataclass
        class FakeSlice:
            requested_at: str = "2025-05-20T12:00:00"
            domains: dict = field(default_factory=dict)
            coverage_summary: dict = field(default_factory=dict)

        mock_svc = MagicMock()
        mock_svc.get_slice_at.return_value = FakeSlice()
        mock_get_svc.return_value = mock_svc

        resp = client.get("/time-slice/?timestamp=2025-05-20T12:00:00")
        assert resp.status_code == 200

    def test_time_slice_invalid_timestamp(self, client):
        resp = client.get("/time-slice/?timestamp=not-a-date")
        assert resp.status_code == 400

    @patch("api.routers.time_slice.get_time_slice_service")
    def test_feature_history(self, mock_get_svc, client):
        @dataclass
        class FakeHistory:
            symbol: str = "BTC/USDT"
            rows: list = field(default_factory=list)
            row_count: int = 0

        mock_svc = MagicMock()
        mock_svc.get_feature_history.return_value = FakeHistory()
        mock_get_svc.return_value = mock_svc

        resp = client.get(
            "/time-slice/feature-history"
            "?symbol=BTC/USDT&start=2025-05-19T00:00:00"
            "&end=2025-05-20T00:00:00&features=rsi_14"
        )
        assert resp.status_code == 200
