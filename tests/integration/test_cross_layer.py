"""集成测试：跨层数据流验证。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
os.environ.setdefault("DB_SPLIT_ENABLED", "0")

from database.db_manager import DBManager


def test_data_layer_to_logic_layer_flow(tmp_path):
    """数据层 init_storage → 逻辑层 init_storage → bundle 读取不崩溃。"""
    from data_layer.perpetual_dex_data.service import PerpDexDataService
    from logic_layer.regime_detection.service import RegimeDetectionService

    db = DBManager(str(tmp_path / "flow.sqlite"))
    db.init_tables()

    class MockClient:
        def fetch_dydx_markets(self): return []
        def fetch_hyperliquid_meta(self): return []
        def fetch_hyperliquid_funding(self): return []
        def fetch_gmx_positions(self): return []
        def close(self): pass

    data_svc = PerpDexDataService(client=MockClient(), db=db)
    data_svc.init_storage()

    logic_svc = RegimeDetectionService(db=db)
    logic_svc.init_storage()

    bundle = logic_svc.load_latest_context_bundle()
    assert bundle["status"] in ("no_data", "ready")
    db.close()


def test_multiple_logic_modules_share_db(tmp_path):
    """多个逻辑模块共享同一 DB 实例不冲突。"""
    from logic_layer.regime_detection.service import RegimeDetectionService
    from logic_layer.anomaly_detection.service import AnomalyDetectionService
    from logic_layer.liquidity_analysis.service import LiquidityAnalysisService

    db = DBManager(str(tmp_path / "shared.sqlite"))
    db.init_tables()

    services = [
        RegimeDetectionService(db=db),
        AnomalyDetectionService(db=db),
        LiquidityAnalysisService(db=db),
    ]

    for svc in services:
        svc.init_storage()

    bundles = [svc.load_latest_context_bundle() for svc in services]
    assert all(b["status"] in ("no_data", "ready") for b in bundles)
    db.close()


def test_db_init_tables_creates_all_expected_tables(tmp_path):
    """DBManager.init_tables() 创建所有核心表，不抛异常。"""
    db = DBManager(str(tmp_path / "init.sqlite"))
    db.init_tables()

    tables = {
        row["name"]
        for row in db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    # 验证关键表存在
    assert "klines" in tables
    assert "technical_indicators" in tables
    assert "collection_runs" in tables
    assert "data_quality_audit_snapshots" in tables
    db.close()


def test_exception_hierarchy_import():
    """exceptions.py 可正常导入且继承关系正确。"""
    from exceptions import (
        EvoQuantError,
        DataLayerError,
        DataAcquisitionError,
        LogicLayerError,
        DatabaseError,
        APIError,
        NotFoundError,
        ValidationError,
    )

    assert issubclass(DataLayerError, EvoQuantError)
    assert issubclass(DataAcquisitionError, DataLayerError)
    assert issubclass(LogicLayerError, EvoQuantError)
    assert issubclass(DatabaseError, EvoQuantError)
    assert issubclass(APIError, EvoQuantError)
    assert issubclass(NotFoundError, APIError)
    assert issubclass(ValidationError, APIError)

    err = NotFoundError("test", context={"symbol": "BTC"})
    assert err.status_code == 404
    assert err.error_code == "NOT_FOUND"
    assert "BTC" in str(err)
