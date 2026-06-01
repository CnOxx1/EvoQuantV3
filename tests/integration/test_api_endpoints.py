"""集成测试：API 端点验证。

使用 FastAPI TestClient 测试端点响应格式和错误处理。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
os.environ.setdefault("DB_SPLIT_ENABLED", "0")

from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)


def test_health_endpoint_returns_200():
    """GET /health 返回 200 且包含 status 字段。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_symbols_endpoint_returns_list():
    """GET /symbols 返回资产列表。"""
    resp = client.get("/symbols")
    assert resp.status_code == 200
    data = resp.json()
    assert "symbols" in data
    assert isinstance(data["symbols"], list)
    assert len(data["symbols"]) > 0


def test_invalid_symbol_returns_422():
    """请求不存在的 symbol 返回 422 标准错误格式。"""
    resp = client.get("/regime/INVALID_SYMBOL_XYZ/current")
    assert resp.status_code in (404, 422)
    data = resp.json()
    assert "error_code" in data
    assert "detail" in data
    assert "request_id" in data
    assert "timestamp" in data
