"""时间切片查询模块单元测试。"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from logic_layer.time_slice.models import DomainSlice, TimeSlice, TimeSliceRange
from logic_layer.time_slice.repository import TimeSliceRepository
from logic_layer.time_slice.service import TimeSliceService


@pytest.fixture
def mock_db():
    """创建内存 SQLite 数据库并填充测试数据。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")

    # merged_klines
    conn.execute("""
        CREATE TABLE merged_klines (
            id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT,
            open_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL
        )
    """)
    conn.executemany(
        "INSERT INTO merged_klines (symbol,timeframe,open_time,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("BTC/USDT", "1h", "2025-05-20T10:00:00", 67000, 67500, 66800, 67200, 100),
            ("BTC/USDT", "1h", "2025-05-20T11:00:00", 67200, 67800, 67100, 67600, 120),
            ("ETH/USDT", "1h", "2025-05-20T10:00:00", 3100, 3150, 3080, 3120, 500),
            ("ETH/USDT", "1h", "2025-05-20T11:00:00", 3120, 3180, 3100, 3160, 600),
        ],
    )

    # technical_indicators
    conn.execute("""
        CREATE TABLE technical_indicators (
            id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT,
            open_time TEXT, rsi_14 REAL, macd_histogram REAL
        )
    """)
    conn.executemany(
        "INSERT INTO technical_indicators (symbol,timeframe,open_time,rsi_14,macd_histogram) VALUES (?,?,?,?,?)",
        [
            ("BTC/USDT", "1h", "2025-05-20T10:00:00", 55.0, 120.5),
            ("BTC/USDT", "1h", "2025-05-20T11:00:00", 58.0, 150.2),
            ("ETH/USDT", "1h", "2025-05-20T11:00:00", 52.0, -30.1),
        ],
    )

    # feature_standardization_snapshots
    conn.execute("""
        CREATE TABLE feature_standardization_snapshots (
            id INTEGER PRIMARY KEY, snapshot_time TEXT, symbol_count INTEGER,
            feature_count INTEGER, composite_count INTEGER, bundle_json TEXT
        )
    """)
    bundle = json.dumps({
        "as_of": "2025-05-20T10:30:00", "status": "ready", "symbol_count": 2,
        "assets": [
            {"symbol": "BTC/USDT", "overall_extremity_score": 1.2},
            {"symbol": "ETH/USDT", "overall_extremity_score": 0.8},
        ],
        "market_extremes": {"regime_distribution": {"normal": 10}},
    })
    conn.execute(
        "INSERT INTO feature_standardization_snapshots (snapshot_time,symbol_count,feature_count,composite_count,bundle_json) VALUES (?,?,?,?,?)",
        ("2025-05-20T10:30:00", 2, 5, 4, bundle),
    )

    # cross_asset tables
    conn.execute("CREATE TABLE cross_asset_correlation_snapshots (id INTEGER PRIMARY KEY, snapshot_time TEXT, window_hours INTEGER, matrix_json TEXT, symbols_json TEXT)")
    conn.execute("INSERT INTO cross_asset_correlation_snapshots (snapshot_time,window_hours,matrix_json,symbols_json) VALUES (?,?,?,?)",
                 ("2025-05-20T10:00:00", 168, '[[1,0.5],[0.5,1]]', '["BTC/USDT","ETH/USDT"]'))
    conn.execute("CREATE TABLE cross_asset_relative_strength (id INTEGER PRIMARY KEY, snapshot_time TEXT, symbol TEXT, rs_score REAL)")
    conn.execute("CREATE TABLE cross_asset_sector_rotation (id INTEGER PRIMARY KEY, snapshot_time TEXT, sector TEXT, phase TEXT)")
    conn.execute("CREATE TABLE cross_asset_fund_flow (id INTEGER PRIMARY KEY, snapshot_time TEXT, scope TEXT, net_flow REAL)")

    # other snapshot tables (empty)
    conn.execute("CREATE TABLE portfolio_risk_snapshots (id INTEGER PRIMARY KEY, snapshot_time TEXT, portfolio_name TEXT, weights_json TEXT, risk_contributions_json TEXT, concentration_json TEXT)")
    conn.execute("CREATE TABLE macro_context_snapshots (id INTEGER PRIMARY KEY, snapshot_time TEXT, factor_id TEXT)")
    conn.execute("CREATE TABLE market_breadth_snapshots (id INTEGER PRIMARY KEY, snapshot_time TEXT, breadth_score REAL)")
    conn.execute("CREATE TABLE asset_readiness_snapshots (id INTEGER PRIMARY KEY, snapshot_time TEXT, scope_kind TEXT)")
    conn.execute("CREATE TABLE ai_market_context_snapshots (id INTEGER PRIMARY KEY, entity_key TEXT, snapshot_time TEXT, bundle_json TEXT)")
    conn.execute("CREATE TABLE exchange_comparison_snapshots (id INTEGER PRIMARY KEY, symbol TEXT, exchange_a TEXT, exchange_b TEXT, timestamp TEXT, net_spread REAL)")
    conn.commit()

    db = MagicMock()
    db.conn = conn
    yield db
    conn.close()


class TestTimeSliceRepository:
    def test_fetch_klines_at(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        rows = repo.fetch_klines_at("2025-05-20T10:30:00")
        assert len(rows) == 2
        btc = next(r for r in rows if r["symbol"] == "BTC/USDT")
        assert btc["open_time"] == "2025-05-20T10:00:00"
        assert btc["close"] == 67200

    def test_fetch_klines_at_later(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        rows = repo.fetch_klines_at("2025-05-20T12:00:00")
        btc = next(r for r in rows if r["symbol"] == "BTC/USDT")
        assert btc["open_time"] == "2025-05-20T11:00:00"

    def test_fetch_klines_with_symbol_filter(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        rows = repo.fetch_klines_at("2025-05-20T12:00:00", symbols=["BTC/USDT"])
        assert len(rows) == 1
        assert rows[0]["symbol"] == "BTC/USDT"

    def test_fetch_technical_indicators_at(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        rows = repo.fetch_technical_indicators_at("2025-05-20T11:30:00")
        assert len(rows) == 2
        btc = next(r for r in rows if r["symbol"] == "BTC/USDT")
        assert btc["rsi_14"] == 58.0

    def test_fetch_feature_std_bundle_at(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        result = repo.fetch_feature_std_bundle_at("2025-05-20T11:00:00")
        assert result is not None
        assert result["snapshot_time"] == "2025-05-20T10:30:00"
        assert result["bundle"]["symbol_count"] == 2

    def test_fetch_feature_std_bundle_too_early(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        result = repo.fetch_feature_std_bundle_at("2025-05-20T09:00:00")
        assert result is None

    def test_fetch_correlation_at(self, mock_db):
        repo = TimeSliceRepository(mock_db)
        result = repo.fetch_correlation_at("2025-05-20T11:00:00")
        assert result is not None
        assert result["matrix_json"] == [[1, 0.5], [0.5, 1]]


class TestTimeSliceService:
    def test_get_slice_at_basic(self, mock_db):
        service = TimeSliceService(db=mock_db)
        result = service.get_slice_at(
            "2025-05-20T11:30:00",
            domains=["klines", "technical_indicators"],
        )
        assert isinstance(result, TimeSlice)
        assert result.requested_at == "2025-05-20T11:30:00"
        assert "klines" in result.domains
        assert result.domains["klines"].status == "ready"

    def test_get_slice_at_missing_domain(self, mock_db):
        service = TimeSliceService(db=mock_db)
        result = service.get_slice_at(
            "2025-05-20T11:30:00", domains=["portfolio_risk"]
        )
        assert result.domains["portfolio_risk"].status == "missing"

    def test_get_slice_at_with_symbols(self, mock_db):
        service = TimeSliceService(db=mock_db)
        result = service.get_slice_at(
            "2025-05-20T11:30:00", symbols=["BTC/USDT"], domains=["klines"]
        )
        assert "BTC/USDT" in result.domains["klines"].payload
        assert "ETH/USDT" not in result.domains["klines"].payload

    def test_coverage_summary(self, mock_db):
        service = TimeSliceService(db=mock_db)
        result = service.get_slice_at(
            "2025-05-20T11:30:00", domains=["klines", "portfolio_risk"]
        )
        assert result.coverage_summary["domains_ready"] == 1
        assert result.coverage_summary["domains_missing"] == 1
        assert result.coverage_summary["overall_freshness"] == "partial"
