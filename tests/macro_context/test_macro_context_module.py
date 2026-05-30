import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.macro_data.market import MacroMarketCollector
from data_layer.macro_data.models import MacroTimeSeriesPoint
from data_layer.macro_data.rates import MacroRateCollector
from data_layer.macro_data.service import MacroDataService
from logic_layer.macro_context.models import MacroContextConfig
from logic_layer.macro_context.service import MacroContextService


def seed_macro_points(db: DBManager):
    MacroDataService(db=db).sync_factor_catalog()
    market_collector = MacroMarketCollector(object(), db)
    rate_collector = MacroRateCollector(object(), db)

    base_time = MacroDataService._utc_now_naive().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    market_points = [
        MacroTimeSeriesPoint(
            factor_id="dxy",
            category="dollar",
            factor_type="market_price",
            interval="1d",
            observation_time=base_time - timedelta(days=5),
            close=100.0,
            value=100.0,
            unit="index_points",
            currency="USD",
            source_name="yahoo_finance",
            source_symbol="DX-Y.NYB",
        ),
        MacroTimeSeriesPoint(
            factor_id="dxy",
            category="dollar",
            factor_type="market_price",
            interval="1d",
            observation_time=base_time - timedelta(days=1),
            close=102.0,
            value=102.0,
            unit="index_points",
            currency="USD",
            source_name="yahoo_finance",
            source_symbol="DX-Y.NYB",
        ),
        MacroTimeSeriesPoint(
            factor_id="dxy",
            category="dollar",
            factor_type="market_price",
            interval="1d",
            observation_time=base_time,
            close=104.0,
            value=104.0,
            unit="index_points",
            currency="USD",
            source_name="yahoo_finance",
            source_symbol="DX-Y.NYB",
            quality_flag="stale",
        ),
    ]
    rate_points = [
        MacroTimeSeriesPoint(
            factor_id="ust_2y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time - timedelta(days=5),
            value=4.00,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS2",
        ),
        MacroTimeSeriesPoint(
            factor_id="ust_2y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time - timedelta(days=1),
            value=4.10,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS2",
        ),
        MacroTimeSeriesPoint(
            factor_id="ust_2y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time,
            value=4.20,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS2",
        ),
        MacroTimeSeriesPoint(
            factor_id="ust_10y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time - timedelta(days=5),
            value=4.30,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS10",
        ),
        MacroTimeSeriesPoint(
            factor_id="ust_10y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time - timedelta(days=1),
            value=4.40,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS10",
        ),
        MacroTimeSeriesPoint(
            factor_id="ust_10y_yield",
            category="rates",
            factor_type="macro_level",
            interval="1d",
            observation_time=base_time,
            value=4.50,
            unit="percent",
            currency="USD",
            source_name="fred",
            source_symbol="DGS10",
        ),
    ]

    market_collector.save_to_db(market_points)
    rate_collector.save_to_db(rate_points)


def seed_partial_only_macro_point(db: DBManager):
    MacroDataService(db=db).sync_factor_catalog()
    market_collector = MacroMarketCollector(object(), db)
    base_time = MacroDataService._utc_now_naive().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    market_collector.save_to_db(
        [
            MacroTimeSeriesPoint(
                factor_id="dxy",
                category="dollar",
                factor_type="market_price",
                interval="1d",
                observation_time=base_time,
                close=104.0,
                value=104.0,
                unit="index_points",
                currency="USD",
                source_name="yahoo_finance",
                source_symbol="DX-Y.NYB",
            )
        ]
    )


def test_macro_context_builds_changes_for_ai(tmp_path):
    db = DBManager(str(tmp_path / "macro_context.sqlite"))
    db.init_tables()
    seed_macro_points(db)

    service = MacroContextService(
        db=db,
        config=MacroContextConfig(interval_filter="1d"),
    )
    snapshots = service.build_latest_snapshots(
        factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"],
        persist=False,
    )

    by_factor = {snapshot.factor_id: snapshot for snapshot in snapshots}

    assert by_factor["dxy"].change_1d_abs == 2.0
    assert by_factor["dxy"].change_5d_abs == 4.0
    assert by_factor["dxy"].change_1d_pct == pytest.approx((104.0 - 102.0) / 102.0 * 100)
    assert by_factor["ust_2y_yield"].change_1d_bps == pytest.approx(10.0)
    assert by_factor["ust_10y_yield"].change_5d_bps == pytest.approx(20.0)

    service.close()


def test_macro_context_bundle_exposes_visible_vs_raw_quality(tmp_path):
    db = DBManager(str(tmp_path / "macro_context_bundle.sqlite"))
    db.init_tables()
    seed_macro_points(db)

    service = MacroContextService(
        db=db,
        config=MacroContextConfig(interval_filter="1d"),
    )
    service.build_latest_snapshots(
        factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"],
        persist=True,
    )
    bundle = service.load_latest_context_bundle(interval="1d")

    assert bundle["factor_count"] == 2
    assert bundle["raw_factor_count"] == 3
    assert bundle["excluded_factor_count"] == 1
    assert bundle["stale_factor_count"] == 1
    assert bundle["visibility_status"] == "partial"
    assert bundle["data_quality_flag"] == "partial"
    assert bundle["cross_asset_context"]["yield_curve_2s10s_bps"] == pytest.approx(30.0)
    assert bundle["cross_asset_context"]["yield_curve_2s10s_status"] == "ready"
    assert bundle["raw_cross_asset_context"]["yield_curve_2s10s_bps"] == pytest.approx(30.0)
    assert bundle["coverage_score"] > 0
    assert {row["factor_id"] for row in bundle["factors"]} == {
        "ust_2y_yield",
        "ust_10y_yield",
    }
    assert {row["factor_id"] for row in bundle["raw_factors"]} == {
        "dxy",
        "ust_2y_yield",
        "ust_10y_yield",
    }
    raw_map = {row["factor_id"]: row for row in bundle["raw_factors"]}
    assert raw_map["dxy"]["context_status"] == "stale_only"
    assert raw_map["dxy"]["is_ai_visible"] is False
    assert bundle["coverage_summary"]["excluded_factor_ids"] == ["dxy"]

    service.close()


def test_macro_context_bundle_marks_missing_reference_windows_as_partial(tmp_path):
    db = DBManager(str(tmp_path / "macro_context_partial.sqlite"))
    db.init_tables()
    seed_partial_only_macro_point(db)

    service = MacroContextService(
        db=db,
        config=MacroContextConfig(interval_filter="1d"),
    )
    service.build_latest_snapshots(
        factor_ids=["dxy"],
        persist=True,
    )
    bundle = service.load_latest_context_bundle(factor_ids=["dxy"], interval="1d")

    assert bundle["factor_count"] == 1
    assert bundle["raw_factor_count"] == 1
    assert bundle["ready_factor_count"] == 0
    assert bundle["partial_factor_count"] == 1
    assert bundle["missing_reference_1d_factor_count"] == 1
    assert bundle["missing_reference_5d_factor_count"] == 1
    assert bundle["data_quality_flag"] == "partial"
    assert bundle["visibility_status"] == "ready"
    assert bundle["coverage_summary"]["missing_reference_1d_factor_ids"] == ["dxy"]
    assert bundle["coverage_summary"]["missing_reference_5d_factor_ids"] == ["dxy"]
    assert bundle["factors"][0]["context_status"] == "partial"
    assert "missing_reference_1d" in bundle["factors"][0]["context_quality_flags"]
    assert "missing_reference_5d" in bundle["factors"][0]["context_quality_flags"]

    service.close()


def test_macro_context_bundle_marks_stale_only_subset_as_blocked(tmp_path):
    db = DBManager(str(tmp_path / "macro_context_raw_only.sqlite"))
    db.init_tables()
    seed_macro_points(db)

    service = MacroContextService(
        db=db,
        config=MacroContextConfig(interval_filter="1d"),
    )
    service.build_latest_snapshots(
        factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"],
        persist=True,
    )
    bundle = service.load_latest_context_bundle(factor_ids=["dxy"], interval="1d")

    assert bundle["factor_count"] == 0
    assert bundle["raw_factor_count"] == 1
    assert bundle["visibility_status"] == "raw_only"
    assert bundle["data_quality_flag"] == "blocked"
    assert bundle["factors"] == []
    assert bundle["raw_factors"][0]["factor_id"] == "dxy"
    assert bundle["raw_factors"][0]["context_status"] == "stale_only"
    assert "macro_context_raw_only" in bundle["data_quality_flags"]

    service.close()


def test_macro_context_persist_is_idempotent_for_same_observation(tmp_path):
    db = DBManager(str(tmp_path / "macro_context_idempotent.sqlite"))
    db.init_tables()
    seed_macro_points(db)

    service = MacroContextService(
        db=db,
        config=MacroContextConfig(interval_filter="1d"),
    )
    service.build_latest_snapshots(
        factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"],
        persist=True,
    )
    service.build_latest_snapshots(
        factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"],
        persist=True,
    )

    row = db.fetch_one(
        "SELECT COUNT(*) AS count FROM macro_context_snapshots"
    )
    assert row["count"] == 3

    service.close()
