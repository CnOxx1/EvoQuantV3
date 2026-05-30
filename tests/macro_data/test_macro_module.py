import sys
import threading
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.macro_data import runner as macro_runner
from data_layer.macro_data.market import MacroMarketCollector
from data_layer.macro_data.models import MacroTimeSeriesPoint, utc_now_naive
from data_layer.macro_data.rates import MacroRateCollector
from data_layer.macro_data.service import MacroDataService
from data_layer.macro_data.sources import load_macro_factors


def build_yahoo_payload(*timestamps: int) -> dict:
    opens = [100.0 + index for index, _ in enumerate(timestamps)]
    highs = [101.0 + index for index, _ in enumerate(timestamps)]
    lows = [99.0 + index for index, _ in enumerate(timestamps)]
    closes = [100.5 + index for index, _ in enumerate(timestamps)]
    volumes = [1000.0 + index for index, _ in enumerate(timestamps)]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": list(timestamps),
                    "indicators": {
                        "quote": [
                            {
                                "open": opens,
                                "high": highs,
                                "low": lows,
                                "close": closes,
                                "volume": volumes,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


class StaticMacroClient:
    def __init__(self, yahoo_payloads=None, fred_payloads=None):
        self.yahoo_payloads = yahoo_payloads or {}
        self.fred_payloads = fred_payloads or {}

    def fetch_yahoo_chart(self, symbol, interval, start_at, end_at=None):
        return self.yahoo_payloads.get(
            (symbol, interval),
            build_yahoo_payload(int(utc_now_naive().timestamp()) - 3600),
        )

    def fetch_fred_series(self, series_id, start_date=None, end_date=None):
        rows = self.fred_payloads.get(
            series_id,
            [
                {"DATE": utc_now_naive().date().isoformat(), series_id: "4.25"},
            ],
        )
        if start_date is None and end_date is None:
            return rows

        filtered = []
        start_day = start_date.date() if start_date is not None else None
        end_day = end_date.date() if end_date is not None else None
        for row in rows:
            date_text = (
                row.get("observation_date")
                or row.get("DATE")
                or row.get("date")
                or ""
            ).strip()
            if not date_text:
                continue
            row_day = datetime.fromisoformat(date_text).date()
            if start_day is not None and row_day < start_day:
                continue
            if end_day is not None and row_day > end_day:
                continue
            filtered.append(dict(row))
        return filtered


class PartiallyFailingMacroClient(StaticMacroClient):
    def __init__(self, yahoo_payloads=None, fred_payloads=None, failing_fred_series=None):
        super().__init__(yahoo_payloads=yahoo_payloads, fred_payloads=fred_payloads)
        self.failing_fred_series = {
            str(value).strip()
            for value in (failing_fred_series or [])
            if str(value).strip()
        }

    def fetch_fred_series(self, series_id, start_date=None, end_date=None):
        if series_id in self.failing_fred_series:
            raise TimeoutError(f"timeout for {series_id}")
        return super().fetch_fred_series(
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
        )


P1_MACRO_CONFIG_PATCH = {
    "enable_fed_funds_upper": True,
    "enable_sp500": True,
    "enable_vix": True,
    "enable_ust_3m_yield": True,
    "enable_ust_30y_yield": True,
    "enable_ust_10y_real_yield": True,
    "enable_us_10y_breakeven_inflation": True,
    "enable_us_bbb_oas": True,
    "enable_us_high_yield_oas": True,
    "enable_wti_crude": True,
}


def test_market_price_normalization_uses_close_as_value(tmp_path):
    now = utc_now_naive()
    timestamps = [
        int((now - timedelta(hours=2)).timestamp()),
        int((now - timedelta(hours=1)).timestamp()),
    ]
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(*timestamps),
        }
    )
    collector = MacroMarketCollector(client, DBManager(str(tmp_path / "macro_market.sqlite")))
    factor = load_macro_factors(factor_type="market_price", factor_ids=["dxy"])[0]

    points = collector.fetch_factor_history(
        factor=factor,
        interval="1h",
        lookback_days=5,
        ingest_run_id="run-1",
    )

    assert len(points) == 2
    assert all(point.value == point.close for point in points)
    assert points[-1].quality_flag == "ok"

    collector.db.close()


def test_macro_level_save_to_db_keeps_newer_latest_snapshot(tmp_path):
    db = DBManager(str(tmp_path / "macro_latest.sqlite"))
    db.init_tables()
    collector = MacroRateCollector(StaticMacroClient(), db)

    newer_point = MacroTimeSeriesPoint(
        factor_id="ust_2y_yield",
        category="rates",
        factor_type="macro_level",
        interval="1d",
        observation_time=utc_now_naive(),
        value=4.35,
        unit="percent",
        currency="USD",
        source_name="fred",
        source_symbol="DGS2",
        quality_flag="ok",
    )
    older_point = MacroTimeSeriesPoint(
        factor_id="ust_2y_yield",
        category="rates",
        factor_type="macro_level",
        interval="1d",
        observation_time=utc_now_naive() - timedelta(days=1),
        value=4.10,
        unit="percent",
        currency="USD",
        source_name="fred",
        source_symbol="DGS2",
        quality_flag="stale",
    )

    collector.save_to_db([newer_point])
    collector.save_to_db([older_point])

    latest = db.fetch_one(
        """
        SELECT value, observation_time, quality_flag
        FROM latest_macro_timeseries
        WHERE factor_id = ? AND interval = ?
        """,
        ("ust_2y_yield", "1d"),
    )

    assert latest["value"] == 4.35
    assert latest["observation_time"] == newer_point.observation_time.isoformat()
    assert latest["quality_flag"] == "ok"

    db.close()


def test_macro_rate_collector_accepts_observation_date_header(tmp_path):
    now = utc_now_naive()
    client = StaticMacroClient(
        fred_payloads={
            "DGS2": [
                {"observation_date": (now - timedelta(days=1)).date().isoformat(), "DGS2": "4.21"},
                {"observation_date": now.date().isoformat(), "DGS2": "4.25"},
            ]
        }
    )
    collector = MacroRateCollector(client, DBManager(str(tmp_path / "macro_rates.sqlite")))
    factor = load_macro_factors(factor_type="macro_level", factor_ids=["ust_2y_yield"])[0]

    points = collector.fetch_factor_history(
        factor=factor,
        lookback_days=30,
        ingest_run_id="run-rates",
    )

    assert len(points) == 2
    assert points[-1].value == 4.25
    assert points[-1].interval == "1d"

    collector.db.close()




def test_macro_rate_collect_can_continue_after_single_fred_timeout(tmp_path):
    now = utc_now_naive()
    client = PartiallyFailingMacroClient(
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.25"}],
        },
        failing_fred_series={"DGS10"},
    )
    collector = MacroRateCollector(
        client,
        DBManager(str(tmp_path / "macro_rate_collect_partial.sqlite")),
    )
    collector.db.init_tables()

    points = collector.collect(
        factor_ids=["ust_2y_yield", "ust_10y_yield"],
        continue_on_error=True,
    )

    assert points
    assert {point.factor_id for point in points} == {"ust_2y_yield"}

    latest_rows = collector.db.fetch_all(
        """
        SELECT factor_id, value
        FROM latest_macro_timeseries
        ORDER BY factor_id
        """
    )
    assert [row["factor_id"] for row in latest_rows] == ["ust_2y_yield"]

    collector.db.close()


def test_macro_rate_collect_raises_without_continue_on_error(tmp_path):
    collector = MacroRateCollector(
        PartiallyFailingMacroClient(failing_fred_series={"DGS2"}),
        DBManager(str(tmp_path / "macro_rate_collect_raise.sqlite")),
    )

    with pytest.raises(TimeoutError):
        collector.collect(
            factor_ids=["ust_2y_yield"],
            continue_on_error=False,
        )

    collector.db.close()


def test_macro_collect_once_keeps_partial_rate_success_when_fred_partially_times_out(tmp_path):
    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = PartiallyFailingMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
        },
        failing_fred_series={"DGS10"},
    )
    service = MacroDataService(
        client=client,
        db=DBManager(str(tmp_path / "macro_collect_once_partial.sqlite")),
    )
    service.init_storage()

    summary = service.collect_once(factor_ids=["dxy", "ust_2y_yield", "ust_10y_yield"])
    latest_rows = service.db.fetch_all(
        """
        SELECT factor_id, interval
        FROM latest_macro_timeseries
        ORDER BY factor_id, interval
        """
    )
    run_rows = service.db.fetch_all(
        """
        SELECT source_name, status, item_count
        FROM collection_runs
        WHERE module_name = 'macro_data'
        ORDER BY id
        """
    )

    assert summary["market_points"] >= 2
    assert summary["rate_points"] == 1
    assert [
        (row["factor_id"], row["interval"])
        for row in latest_rows
    ] == [
        ("dxy", "1d"),
        ("dxy", "1h"),
        ("ust_2y_yield", "1d"),
    ]
    assert any(
        row["source_name"] == "fred" and row["status"] == "success" and row["item_count"] == 1
        for row in run_rows
    )

    service.close()

def test_macro_rate_bootstrap_history_can_continue_after_fred_timeout(tmp_path):
    now = utc_now_naive()
    client = PartiallyFailingMacroClient(
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.25"}],
        },
        failing_fred_series={"DGS10"},
    )
    collector = MacroRateCollector(client, DBManager(str(tmp_path / "macro_rates_timeout.sqlite")))

    points = collector.bootstrap_history(
        factor_ids=["ust_2y_yield", "ust_10y_yield"],
        daily_history_years=1,
        continue_on_error=True,
    )

    assert points
    assert {point.factor_id for point in points} == {"ust_2y_yield"}

    collector.db.close()


def test_macro_rate_bootstrap_history_raises_without_continue_on_error(tmp_path):
    collector = MacroRateCollector(
        PartiallyFailingMacroClient(failing_fred_series={"DGS2"}),
        DBManager(str(tmp_path / "macro_rates_timeout_raise.sqlite")),
    )

    with pytest.raises(TimeoutError):
        collector.bootstrap_history(
            factor_ids=["ust_2y_yield"],
            daily_history_years=1,
            continue_on_error=False,
        )

    collector.db.close()


def test_macro_runner_bootstrap_defaults_to_continue_on_error(monkeypatch):
    captured: dict[str, object] = {}

    class DummyService:
        def init_storage(self):
            captured["initialized"] = True

        def bootstrap(self, **kwargs):
            captured["bootstrap_kwargs"] = kwargs

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(macro_runner, "setup_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(macro_runner, "MacroDataService", DummyService)
    monkeypatch.setattr(sys, "argv", ["macro_data.runner", "--mode", "bootstrap"])

    macro_runner.main()

    assert captured["initialized"] is True
    assert captured["closed"] is True
    assert captured["bootstrap_kwargs"]["continue_on_error"] is True


def test_macro_runner_strict_bootstrap_can_fail_fast(monkeypatch):
    captured: dict[str, object] = {}

    class DummyService:
        def init_storage(self):
            captured["initialized"] = True

        def bootstrap(self, **kwargs):
            captured["bootstrap_kwargs"] = kwargs

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(macro_runner, "setup_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(macro_runner, "MacroDataService", DummyService)
    monkeypatch.setattr(
        sys,
        "argv",
        ["macro_data.runner", "--mode", "bootstrap", "--strict-bootstrap"],
    )

    macro_runner.main()

    assert captured["initialized"] is True
    assert captured["closed"] is True
    assert captured["bootstrap_kwargs"]["continue_on_error"] is False


def test_macro_runner_scheduler_keeps_running_when_bootstrap_fails_in_best_effort_mode(
    monkeypatch,
):
    captured: dict[str, object] = {}

    class DummyScheduler:
        def shutdown(self, wait=False):
            captured["shutdown_called"] = True

        def start(self):
            captured["scheduler_started"] = True

    class DummyService:
        def init_storage(self):
            captured["initialized"] = True

        def bootstrap(self, **kwargs):
            captured["bootstrap_kwargs"] = kwargs
            raise TimeoutError("fred timed out")

        def build_scheduler(self, **kwargs):
            captured["scheduler_kwargs"] = kwargs
            return DummyScheduler()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(macro_runner, "setup_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(macro_runner, "MacroDataService", DummyService)
    monkeypatch.setattr(sys, "argv", ["macro_data.runner", "--mode", "scheduler"])

    macro_runner.main()

    assert captured["initialized"] is True
    assert captured["bootstrap_kwargs"]["continue_on_error"] is True
    assert captured["scheduler_started"] is True
    assert captured["closed"] is True


def test_macro_runner_scheduler_strict_bootstrap_still_raises(monkeypatch):
    captured: dict[str, object] = {}

    class DummyService:
        def init_storage(self):
            captured["initialized"] = True

        def bootstrap(self, **kwargs):
            captured["bootstrap_kwargs"] = kwargs
            raise TimeoutError("fred timed out")

        def build_scheduler(self, **kwargs):
            captured["scheduler_kwargs"] = kwargs
            raise AssertionError("strict bootstrap 失败时不应继续构建 scheduler")

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(macro_runner, "setup_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(macro_runner, "MacroDataService", DummyService)
    monkeypatch.setattr(
        sys,
        "argv",
        ["macro_data.runner", "--mode", "scheduler", "--strict-bootstrap"],
    )

    with pytest.raises(TimeoutError):
        macro_runner.main()

    assert captured["initialized"] is True
    assert captured["bootstrap_kwargs"]["continue_on_error"] is False
    assert captured["closed"] is True


def test_sync_factor_catalog_persists_p0_and_p1_flags(tmp_path):
    from unittest.mock import patch

    with patch.dict("config.settings.MACRO_CONFIG", P1_MACRO_CONFIG_PATCH, clear=False):
        service = MacroDataService(db=DBManager(str(tmp_path / "macro_catalog.sqlite")))
        service.init_storage()

        dxy = service.db.fetch_one(
            "SELECT enabled, factor_type FROM macro_factor_catalog WHERE factor_id = ?",
            ("dxy",),
        )
        fed = service.db.fetch_one(
            "SELECT enabled, factor_type FROM macro_factor_catalog WHERE factor_id = ?",
            ("fed_funds_upper",),
        )
        real_yield = service.db.fetch_one(
            "SELECT enabled, factor_type FROM macro_factor_catalog WHERE factor_id = ?",
            ("ust_10y_real_yield",),
        )

        assert dxy["enabled"] == 1
        assert dxy["factor_type"] == "market_price"
        assert fed["enabled"] == 1
        assert fed["factor_type"] == "macro_level"
        assert real_yield["enabled"] == 1
        assert real_yield["factor_type"] == "macro_level"

        service.close()


def test_scheduler_jobs_use_thread_safe_wrappers(tmp_path):
    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [
                {"DATE": now.date().isoformat(), "DGS2": "4.31"},
            ]
        },
    )
    db_path = str(tmp_path / "macro_scheduler.sqlite")
    service = MacroDataService(
        client=client,
        db=DBManager(db_path),
    )
    service.init_storage()

    errors: list[str] = []

    def worker():
        try:
            service._run_market_job(factor_ids=["dxy"])
            service._run_rate_job(factor_ids=["ust_2y_yield"])
        except Exception as exc:  # pragma: no cover - explicit failure capture
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []

    verify_db = DBManager(db_path)
    market_row = verify_db.fetch_one(
        "SELECT COUNT(*) AS count FROM macro_timeseries WHERE factor_id = ?",
        ("dxy",),
    )
    rate_row = verify_db.fetch_one(
        "SELECT COUNT(*) AS count FROM macro_timeseries WHERE factor_id = ?",
        ("ust_2y_yield",),
    )

    assert market_row["count"] >= 1
    assert rate_row["count"] >= 1

    verify_db.close()
    service.close()


def test_build_scheduler_uses_macro_wrappers(tmp_path):
    service = MacroDataService(db=DBManager(str(tmp_path / "macro_build.sqlite")))

    scheduler = service.build_scheduler(factor_ids=["dxy"])

    assert isinstance(scheduler, BlockingScheduler)
    assert scheduler.get_job("macro_market").func == service._run_market_job
    assert scheduler.get_job("macro_rates").func == service._run_rate_job

    service.close()


def test_collect_once_records_collection_runs_and_macro_coverage(tmp_path):
    from unittest.mock import patch

    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
            ("^NDX", "60m"): build_yahoo_payload(market_ts),
            ("^NDX", "1d"): build_yahoo_payload(market_ts),
            ("GC=F", "60m"): build_yahoo_payload(market_ts),
            ("GC=F", "1d"): build_yahoo_payload(market_ts),
            ("^GSPC", "60m"): build_yahoo_payload(market_ts),
            ("^GSPC", "1d"): build_yahoo_payload(market_ts),
            ("^VIX", "60m"): build_yahoo_payload(market_ts),
            ("^VIX", "1d"): build_yahoo_payload(market_ts),
            ("CL=F", "60m"): build_yahoo_payload(market_ts),
            ("CL=F", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
            "DGS10": [{"DATE": now.date().isoformat(), "DGS10": "4.49"}],
            "DFEDTARU": [{"DATE": now.date().isoformat(), "DFEDTARU": "5.50"}],
            "DGS3MO": [{"DATE": now.date().isoformat(), "DGS3MO": "4.82"}],
            "DGS30": [{"DATE": now.date().isoformat(), "DGS30": "4.63"}],
            "DFII10": [{"DATE": now.date().isoformat(), "DFII10": "2.21"}],
            "T10YIE": [{"DATE": now.date().isoformat(), "T10YIE": "2.28"}],
            "BAMLC0A4CBBB": [{"DATE": now.date().isoformat(), "BAMLC0A4CBBB": "1.74"}],
            "BAMLH0A0HYM2": [{"DATE": now.date().isoformat(), "BAMLH0A0HYM2": "3.92"}],
        },
    )
    with patch.dict("config.settings.MACRO_CONFIG", P1_MACRO_CONFIG_PATCH, clear=False):
        service = MacroDataService(
            client=client,
            db=DBManager(str(tmp_path / "macro_coverage.sqlite")),
        )
        service.init_storage()

        summary = service.collect_once()
        coverage = service.load_source_coverage()
        bundle = service.load_latest_context_bundle()
        run_count = service.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM collection_runs
            WHERE module_name = 'macro_data'
            """
        )["count"]
        coverage_map = {row["source_name"]: row for row in coverage["sources"]}

        assert summary["market_points"] == 12
        assert summary["rate_points"] == 9
        assert run_count == 2
        assert coverage["source_count"] == 2
        assert coverage["ready_source_count"] == 2
        assert coverage["stale_source_count"] == 0
        assert coverage["problem_source_count"] == 0
        assert coverage["total_latest_point_count"] == 21
        assert coverage_map["yahoo_finance"]["expected_factor_count"] == 6
        assert coverage_map["yahoo_finance"]["latest_factor_count"] == 6
        assert coverage_map["yahoo_finance"]["latest_ok_point_count"] == 12
        assert coverage_map["yahoo_finance"]["latest_quality_ready_ratio"] == 1.0
        assert coverage_map["yahoo_finance"]["data_quality_flags"] == []
        assert coverage_map["fred"]["expected_factor_count"] == 9
        assert coverage_map["fred"]["latest_factor_count"] == 9
        assert coverage_map["fred"]["latest_ok_point_count"] == 9
        assert coverage_map["fred"]["latest_quality_ready_ratio"] == 1.0
        assert coverage_map["fred"]["data_quality_flags"] == []
        assert bundle["row_count"] == 15
        assert bundle["coverage_summary"]["expected_factor_count"] == 15
        assert bundle["coverage_summary"]["observed_factor_count"] == 15
        assert bundle["coverage_summary"]["missing_factor_ids"] == []
        assert bundle["coverage_summary"]["expected_category_count"] == 9
        assert bundle["coverage_summary"]["observed_category_count"] == 9
        assert bundle["configured_universe_summary"] == {
            "scope_kind": "default",
            "configured_factor_ids": [
                "dxy",
                "fed_funds_upper",
                "gold_spot",
                "nasdaq_100",
                "sp500",
                "us_10y_breakeven_inflation",
                "us_bbb_oas",
                "us_high_yield_oas",
                "ust_10y_real_yield",
                "ust_10y_yield",
                "ust_2y_yield",
                "ust_30y_yield",
                "ust_3m_yield",
                "vix",
                "wti_crude",
            ],
            "configured_categories": [
                "commodity",
                "credit_spread",
                "dollar",
                "equity_index",
                "inflation_expectation",
                "policy_rate",
                "rates",
                "real_rates",
                "volatility",
            ],
            "configured_source_names": ["fred", "yahoo_finance"],
            "configured_market_regions": ["US", "global"],
            "configured_market_sessions": [
                "global_commodity",
                "us_credit",
                "us_equity",
                "us_macro",
                "us_rates",
            ],
            "factor_count": 15,
            "category_count": 9,
            "source_count": 2,
            "market_region_count": 2,
            "market_session_count": 5,
            "minimum_factor_count_for_market_breadth": 12,
            "minimum_category_count_for_market_breadth": 8,
            "minimum_source_count_for_market_breadth": 2,
            "minimum_market_region_count_for_market_breadth": 2,
            "required_semantic_groups_for_market_breadth": [
                "dollar_anchor",
                "front_end_rates",
                "rates_curve",
                "real_rates",
                "inflation_expectation",
                "credit_stress",
                "equity_risk",
                "volatility_risk",
                "defensive_asset",
                "energy_shock",
            ],
            "covered_semantic_groups": [
                "dollar_anchor",
                "front_end_rates",
                "rates_curve",
                "real_rates",
                "inflation_expectation",
                "credit_stress",
                "equity_risk",
                "volatility_risk",
                "defensive_asset",
                "energy_shock",
            ],
            "missing_semantic_groups": [],
            "breadth_status": "sufficient",
            "is_market_breadth_sufficient": True,
        }
        assert bundle["source_health_summary"]["source_count"] == 2
        assert bundle["source_health_summary"]["ready_source_count"] == 2
        assert bundle["latest_quality_ready_ratio"] == 1.0
        assert bundle["leaders"]["highest_vix"]["factor_id"] == "vix"
        assert bundle["leaders"]["highest_fed_funds_upper"]["factor_id"] == "fed_funds_upper"
        assert bundle["leaders"]["highest_us_high_yield_oas"]["factor_id"] == "us_high_yield_oas"
        assert bundle["data_quality_flags"] == []
        assert bundle["quality_notes"] == []
        service.close()


def test_macro_service_bootstrap_scheduler_mode_keeps_partial_success(tmp_path):
    now = utc_now_naive()
    service = MacroDataService(
        client=PartiallyFailingMacroClient(
            fred_payloads={
                "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.25"}],
            },
            failing_fred_series={"DGS10"},
        ),
        db=DBManager(str(tmp_path / "macro_bootstrap_partial.sqlite")),
    )
    service.init_storage()

    summary = service.bootstrap(
        factor_ids=["ust_2y_yield", "ust_10y_yield"],
        daily_history_years=1,
        continue_on_error=True,
    )

    latest_rows = service.db.fetch_all(
        """
        SELECT factor_id, value
        FROM latest_macro_timeseries
        ORDER BY factor_id
        """
    )

    assert summary["market_points"] == 0
    assert summary["rate_points"] == 1
    assert [row["factor_id"] for row in latest_rows] == ["ust_2y_yield"]

    service.close()


def test_macro_coverage_respects_factor_filter(tmp_path):
    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
        },
    )
    service = MacroDataService(
        client=client,
        db=DBManager(str(tmp_path / "macro_filtered_coverage.sqlite")),
    )
    service.init_storage()

    service.collect_once(factor_ids=["dxy", "ust_2y_yield"])
    coverage = service.load_source_coverage(factor_ids=["dxy", "ust_2y_yield"])
    bundle = service.load_latest_context_bundle(factor_ids=["dxy", "ust_2y_yield"])
    coverage_map = {row["source_name"]: row for row in coverage["sources"]}

    assert coverage["source_count"] == 2
    assert coverage["total_latest_point_count"] == 3
    assert coverage["ready_for_ai_source_count"] == 2
    assert coverage["not_ready_for_ai_source_count"] == 0
    assert coverage_map["yahoo_finance"]["expected_factor_count"] == 1
    assert coverage_map["yahoo_finance"]["latest_factor_count"] == 1
    assert coverage_map["yahoo_finance"]["latest_point_count"] == 2
    assert coverage_map["yahoo_finance"]["latest_ok_point_count"] == 2
    assert coverage_map["fred"]["expected_factor_count"] == 1
    assert coverage_map["fred"]["latest_factor_count"] == 1
    assert coverage_map["fred"]["latest_point_count"] == 1
    assert coverage_map["fred"]["latest_ok_point_count"] == 1
    assert bundle["configured_universe_summary"] == {
        "scope_kind": "filtered",
        "configured_factor_ids": ["dxy", "ust_2y_yield"],
        "configured_categories": ["dollar", "rates"],
        "configured_source_names": ["fred", "yahoo_finance"],
        "configured_market_regions": ["US"],
        "configured_market_sessions": ["us_macro", "us_rates"],
        "factor_count": 2,
        "category_count": 2,
        "source_count": 2,
        "market_region_count": 1,
        "market_session_count": 2,
        "minimum_factor_count_for_market_breadth": 12,
        "minimum_category_count_for_market_breadth": 8,
        "minimum_source_count_for_market_breadth": 2,
        "minimum_market_region_count_for_market_breadth": 2,
        "required_semantic_groups_for_market_breadth": [
            "dollar_anchor",
            "front_end_rates",
            "rates_curve",
            "real_rates",
            "inflation_expectation",
            "credit_stress",
            "equity_risk",
            "volatility_risk",
            "defensive_asset",
            "energy_shock",
        ],
        "covered_semantic_groups": ["dollar_anchor", "front_end_rates"],
        "missing_semantic_groups": [
            "rates_curve",
            "real_rates",
            "inflation_expectation",
            "credit_stress",
            "equity_risk",
            "volatility_risk",
            "defensive_asset",
            "energy_shock",
        ],
        "breadth_status": "filtered",
        "is_market_breadth_sufficient": None,
    }
    assert bundle["coverage_summary"]["expected_factor_count"] == 2
    assert bundle["coverage_summary"]["observed_factor_count"] == 2
    assert bundle["coverage_summary"]["missing_factor_ids"] == []
    assert "macro_factor_coverage_incomplete" not in bundle["data_quality_flags"]

    service.close()


def test_macro_source_ready_but_not_ready_for_ai_when_only_fallback_points(tmp_path):
    now = utc_now_naive()
    service = MacroDataService(
        client=StaticMacroClient(),
        db=DBManager(str(tmp_path / "macro_fallback_ready.sqlite")),
    )
    service.init_storage()
    started_at = now.isoformat()
    finished_at = now.isoformat()

    service.rate_collector.save_to_db(
        [
            MacroTimeSeriesPoint(
                factor_id="ust_2y_yield",
                category="rates",
                factor_type="macro_level",
                interval="1d",
                observation_time=now,
                value=4.31,
                unit="percent",
                currency="USD",
                source_name="fred",
                source_symbol="DGS2",
                quality_flag="fallback",
            )
        ]
    )
    service.db.record_collection_run(
        module_name="macro_data",
        source_name="fred",
        job_name="macro_rates_timeseries",
        status="success",
        item_count=1,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=0.0,
        message=None,
        metadata_json="{}",
    )

    coverage = service.load_source_coverage(factor_ids=["ust_2y_yield"])
    row = coverage["sources"][0]
    bundle = service.load_latest_context_bundle(factor_ids=["ust_2y_yield"])

    assert row["health_status"] == "ready"
    assert row["is_ready_for_ai"] is False
    assert coverage["ready_source_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 1
    assert bundle["source_health_summary"]["ready_source_count"] == 1
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
    assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 1
    assert bundle["coverage_summary"]["coverage_by_source"] == [
        {
            "source_name": "fred",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "expected_factor_count": 1,
            "latest_factor_count": 1,
            "latest_point_count": 1,
            "latest_quality_ready_ratio": 0.0,
            "data_quality_flags": ["fallback_points_present"],
        }
    ]
    assert "macro_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert any("fred" in note for note in bundle["quality_notes"])
    assert bundle["source_health"][0]["data_quality_flags"] == ["fallback_points_present"]

    service.close()


def test_macro_source_ready_but_not_ready_for_ai_when_factor_coverage_incomplete(tmp_path):
    from unittest.mock import patch

    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
            ("^NDX", "60m"): build_yahoo_payload(market_ts),
            ("^NDX", "1d"): build_yahoo_payload(market_ts),
            ("GC=F", "60m"): build_yahoo_payload(market_ts),
            ("GC=F", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
            "DGS10": [{"DATE": now.date().isoformat(), "DGS10": "4.49"}],
        },
    )
    with patch.dict("config.settings.MACRO_CONFIG", P1_MACRO_CONFIG_PATCH, clear=False):
        service = MacroDataService(
            client=client,
            db=DBManager(str(tmp_path / "macro_source_incomplete.sqlite")),
        )
        service.init_storage()
        service.collect_once(
            factor_ids=[
                "dxy",
                "nasdaq_100",
                "gold_spot",
                "ust_2y_yield",
                "ust_10y_yield",
            ]
        )

        coverage = service.load_source_coverage()
        coverage_map = {
            row["source_name"]: row
            for row in coverage["sources"]
        }
        bundle = service.load_latest_context_bundle()

        assert coverage["ready_source_count"] == 2
        assert coverage["ready_for_ai_source_count"] == 0
        assert coverage["not_ready_for_ai_source_count"] == 2
        assert coverage_map["yahoo_finance"]["health_status"] == "ready"
        assert coverage_map["yahoo_finance"]["is_ready_for_ai"] is False
        assert "factor_coverage_incomplete" in coverage_map["yahoo_finance"]["data_quality_flags"]
        assert coverage_map["fred"]["health_status"] == "ready"
        assert coverage_map["fred"]["is_ready_for_ai"] is False
        assert "factor_coverage_incomplete" in coverage_map["fred"]["data_quality_flags"]
        assert bundle["source_health_summary"]["ready_source_count"] == 2
        assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
        assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 2
        assert "macro_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
        assert "macro_factor_coverage_incomplete" in bundle["data_quality_flags"]

        service.close()


def test_macro_bundle_flags_missing_expected_factors(tmp_path):
    from unittest.mock import patch

    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
            ("^NDX", "60m"): build_yahoo_payload(market_ts),
            ("^NDX", "1d"): build_yahoo_payload(market_ts),
            ("GC=F", "60m"): build_yahoo_payload(market_ts),
            ("GC=F", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
            "DGS10": [{"DATE": now.date().isoformat(), "DGS10": "4.49"}],
        },
    )
    with patch.dict("config.settings.MACRO_CONFIG", P1_MACRO_CONFIG_PATCH, clear=False):
        service = MacroDataService(
            client=client,
            db=DBManager(str(tmp_path / "macro_bundle_gap.sqlite")),
        )
        service.init_storage()

        service.collect_once(
            factor_ids=[
                "dxy",
                "ust_2y_yield",
                "ust_10y_yield",
                "nasdaq_100",
                "gold_spot",
            ]
        )
        bundle = service.load_latest_context_bundle()

        assert bundle["row_count"] == 0
        assert bundle["raw_row_count"] == 5
        assert bundle["source_counts"] == {}
        assert bundle["raw_source_counts"] == {
            "yahoo_finance": 3,
            "fred": 2,
        }
        assert bundle["ai_ready_source_names"] == []
        assert bundle["ai_excluded_source_names"] == ["yahoo_finance", "fred"]
        assert bundle["coverage_summary"]["expected_factor_count"] == 15
        assert bundle["coverage_summary"]["observed_factor_count"] == 0
        assert bundle["coverage_summary"]["raw_observed_factor_count"] == 5
        assert bundle["coverage_summary"]["observed_point_count"] == 0
        assert bundle["coverage_summary"]["raw_observed_point_count"] == 5
        assert "us_high_yield_oas" in bundle["coverage_summary"]["missing_factor_ids"]
        assert "credit_spread" in bundle["coverage_summary"]["missing_categories"]
        assert "macro_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
        assert "macro_factor_coverage_incomplete" in bundle["data_quality_flags"]
        assert "macro_context_empty" in bundle["data_quality_flags"]
        assert any("尚未达到 AI-ready 门槛" in note for note in bundle["quality_notes"])

        service.close()


def test_macro_bundle_flags_narrow_default_configured_universe(tmp_path):
    now = utc_now_naive()
    market_ts = int((now - timedelta(hours=1)).timestamp())
    client = StaticMacroClient(
        yahoo_payloads={
            ("DX-Y.NYB", "60m"): build_yahoo_payload(market_ts),
            ("DX-Y.NYB", "1d"): build_yahoo_payload(market_ts),
            ("^NDX", "60m"): build_yahoo_payload(market_ts),
            ("^NDX", "1d"): build_yahoo_payload(market_ts),
            ("GC=F", "60m"): build_yahoo_payload(market_ts),
            ("GC=F", "1d"): build_yahoo_payload(market_ts),
        },
        fred_payloads={
            "DGS2": [{"DATE": now.date().isoformat(), "DGS2": "4.31"}],
            "DGS10": [{"DATE": now.date().isoformat(), "DGS10": "4.49"}],
        },
    )
    narrow_factor_ids = {
        "dxy",
        "ust_2y_yield",
        "ust_10y_yield",
        "nasdaq_100",
        "gold_spot",
    }

    def narrow_load_macro_factors(enabled_only=True, factor_type=None, factor_ids=None):
        factors = load_macro_factors(enabled_only=False, factor_type=factor_type)
        if factor_ids:
            normalized_ids = {
                str(value).strip().lower()
                for value in factor_ids
                if str(value).strip()
            }
            factors = [
                factor
                for factor in factors
                if factor.factor_id.lower() in normalized_ids
            ]
        elif enabled_only:
            factors = [
                factor
                for factor in factors
                if factor.factor_id in narrow_factor_ids
            ]
        return factors

    from unittest.mock import patch

    with patch("data_layer.macro_data.service.load_macro_factors", side_effect=narrow_load_macro_factors), \
         patch("data_layer.macro_data.market.load_macro_factors", side_effect=narrow_load_macro_factors), \
         patch("data_layer.macro_data.rates.load_macro_factors", side_effect=narrow_load_macro_factors):
        service = MacroDataService(
            client=client,
            db=DBManager(str(tmp_path / "macro_narrow_config.sqlite")),
        )
        service.init_storage()
        service.collect_once()

        coverage = service.load_source_coverage()
        bundle = service.load_latest_context_bundle()

        assert coverage["ready_for_ai_source_count"] == 2
        assert coverage["not_ready_for_ai_source_count"] == 0
        assert bundle["row_count"] == 5
        assert bundle["coverage_summary"]["expected_factor_count"] == 5
        assert bundle["coverage_summary"]["observed_factor_count"] == 5
        assert "macro_factor_coverage_incomplete" not in bundle["data_quality_flags"]
        assert bundle["configured_universe_summary"] == {
            "scope_kind": "default",
            "configured_factor_ids": [
                "dxy",
                "gold_spot",
                "nasdaq_100",
                "ust_10y_yield",
                "ust_2y_yield",
            ],
            "configured_categories": [
                "commodity",
                "dollar",
                "equity_index",
                "rates",
            ],
            "configured_source_names": ["fred", "yahoo_finance"],
            "configured_market_regions": ["US", "global"],
            "configured_market_sessions": [
                "global_commodity",
                "us_equity",
                "us_macro",
                "us_rates",
            ],
            "factor_count": 5,
            "category_count": 4,
            "source_count": 2,
            "market_region_count": 2,
            "market_session_count": 4,
            "minimum_factor_count_for_market_breadth": 12,
            "minimum_category_count_for_market_breadth": 8,
            "minimum_source_count_for_market_breadth": 2,
            "minimum_market_region_count_for_market_breadth": 2,
            "required_semantic_groups_for_market_breadth": [
                "dollar_anchor",
                "front_end_rates",
                "rates_curve",
                "real_rates",
                "inflation_expectation",
                "credit_stress",
                "equity_risk",
                "volatility_risk",
                "defensive_asset",
                "energy_shock",
            ],
            "covered_semantic_groups": [
                "dollar_anchor",
                "front_end_rates",
                "rates_curve",
                "equity_risk",
                "defensive_asset",
            ],
            "missing_semantic_groups": [
                "real_rates",
                "inflation_expectation",
                "credit_stress",
                "volatility_risk",
                "energy_shock",
            ],
            "breadth_status": "limited",
            "is_market_breadth_sufficient": False,
        }

        service.close()
         
