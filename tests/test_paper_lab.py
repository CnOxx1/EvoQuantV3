"""Tests for paper-serving production APIs (BandPIT, ACWMI, availability shocks)."""

from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from data_layer.data_quality.availability import (
    load_availability_shocks,
    tag_availability_shock_metadata,
)
from logic_layer.ai_market_context.service import AIMarketContextService
from logic_layer.technical_indicators.repository import TechnicalIndicatorRepository
from logic_layer.time_slice.band_pit import BandObservation, BandPITService
from logic_layer.time_slice.service import TimeSliceService


def test_technical_indicators_merged_open_time_uses_dt_strftime():
    """Regression: Series.strftime must be Series.dt.strftime."""
    frame = pd.DataFrame(
        {
            "open_time": pd.to_datetime(["2026-01-01 00:00:00", "2026-01-02 00:00:00"]),
            "open": [1.0, 2.0],
            "high": [1.0, 2.0],
            "low": [1.0, 2.0],
            "close": [1.0, 2.0],
            "volume": [10.0, 11.0],
        }
    )
    open_time_iso = pd.to_datetime(frame["open_time"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    assert list(open_time_iso) == ["2026-01-01T00:00:00", "2026-01-02T00:00:00"]
    assert hasattr(TechnicalIndicatorRepository, "save_merged_klines")


def test_compute_world_model_index_acwmi_mode():
    out = AIMarketContextService._compute_world_model_index(
        coverage_score=0.8,
        pipeline_latency_context={"summary": {"total_domains": 10, "fresh": 8, "acceptable": 1}},
        data_quality_flag="ok",
        data_quality_flags=[],
        signal_integrity=0.9,
        cross_evidence=0.7,
        index_mode="acwmi",
        abstain_threshold=0.35,
    )
    assert out["wmi"] > 0
    assert out["acwmi"] is not None
    assert out["index_mode"] == "acwmi"
    assert out["abstain_threshold"] == 0.35
    assert "should_ai_abstain" in out


def test_compute_world_model_index_wmi_backward_compatible():
    out = AIMarketContextService._compute_world_model_index(
        coverage_score=0.5,
        pipeline_latency_context={"summary": {"total_domains": 4, "fresh": 2, "acceptable": 1}},
        data_quality_flag="thin",
        data_quality_flags=["x"],
        index_mode="wmi",
    )
    assert "acwmi" not in out
    assert out["index_mode"] == "wmi"


def test_acwmi_proxies_from_readiness():
    s, c, src = AIMarketContextService._acwmi_proxies(
        asset_readiness_row={
            "ready_band_count": 4,
            "limited_band_count": 2,
            "missing_band_count": 2,
        },
        data_quality_flags=["a", "b"],
    )
    assert 0.05 <= s <= 1.0
    assert 0.05 <= c <= 1.0
    assert src == "production_proxy"
    assert c == pytest.approx((4 + 0.7 * 2) / 8)


def test_acwmi_proxies_prefer_paper_engine_fields():
    s, c, src = AIMarketContextService._acwmi_proxies(
        asset_readiness_row={"S": 0.81, "C": 0.66, "ready_band_count": 1},
        data_quality_flags=["ignored"],
    )
    assert src == "paper_engines"
    assert s == pytest.approx(0.81)
    assert c == pytest.approx(0.66)


def test_tag_availability_shock_metadata():
    raw = tag_availability_shock_metadata(band="macro", planted=True, extra={"note": "test"})
    payload = json.loads(raw)
    assert payload["event_kind"] == "availability_shock"
    assert payload["band"] == "macro"
    assert payload["planted"] is True
    assert payload["note"] == "test"


class _FakeMgr:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)


def test_load_availability_shocks_reads_collection_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "market.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE collection_runs (
            id INTEGER PRIMARY KEY,
            module_name TEXT,
            source_name TEXT,
            job_name TEXT,
            status TEXT,
            item_count INTEGER,
            started_at TEXT,
            finished_at TEXT,
            duration_seconds REAL,
            message TEXT,
            metadata_json TEXT,
            created_at TEXT
        )
        """
    )
    meta = tag_availability_shock_metadata(band="news", planted=False)
    conn.execute(
        """
        INSERT INTO collection_runs
        (module_name, source_name, job_name, status, item_count, started_at, finished_at,
         duration_seconds, message, metadata_json, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "news_data",
            "rss",
            "once",
            "error",
            0,
            "2026-01-01T10:00:00",
            "2026-01-01T10:01:00",
            60,
            "timeout",
            meta,
            "2026-01-01T10:01:00",
        ),
    )
    conn.commit()
    conn.close()

    empty = tmp_path / "empty.sqlite"
    sqlite3.connect(empty).close()

    from database.router import Domain

    class FakeRouter:
        def get_manager(self, domain):
            if domain == Domain.MARKET_DATA:
                return _FakeMgr(db_path)
            return _FakeMgr(empty)

        def get_analytics_db(self):
            return _FakeMgr(empty)

    monkeypatch.setattr("database.router.DatabaseRouter", FakeRouter)
    shocks = load_availability_shocks(limit=10)
    assert len(shocks) == 1
    assert shocks[0]["band"] == "news"
    assert shocks[0]["event_kind"] == "availability_shock"
    assert shocks[0]["status"] == "error"


def test_band_pit_service_from_history_tables(tmp_path, monkeypatch):
    ex_path = tmp_path / "ex.sqlite"
    mk_path = tmp_path / "mk.sqlite"
    an_path = tmp_path / "an.sqlite"

    ex = sqlite3.connect(ex_path)
    ex.execute(
        "CREATE TABLE klines (symbol TEXT, timeframe TEXT, open_time TEXT, close REAL)"
    )
    ex.execute(
        "INSERT INTO klines VALUES (?,?,?,?)",
        ("BTC/USDT", "1d", "2026-01-10T00:00:00", 100.0),
    )
    ex.commit()
    ex.close()

    mk = sqlite3.connect(mk_path)
    mk.execute(
        """
        CREATE TABLE macro_timeseries (
            observation_time TEXT, available_at TEXT, series_id TEXT, value REAL
        )
        """
    )
    mk.execute(
        "INSERT INTO macro_timeseries VALUES (?,?,?,?)",
        ("2026-01-08T00:00:00", "2026-01-09T00:00:00", "DFF", 5.0),
    )
    mk.execute(
        "CREATE TABLE alternative_timeseries (observation_time TEXT, metric TEXT, value REAL)"
    )
    mk.execute(
        "INSERT INTO alternative_timeseries VALUES (?,?,?)",
        ("2026-01-09T00:00:00", "fear_greed", 40),
    )
    mk.commit()
    mk.close()
    sqlite3.connect(an_path).close()

    from database.router import Domain

    class DomainRouter:
        def get_manager(self, domain):
            if domain == Domain.EXCHANGE_DATA:
                return _FakeMgr(ex_path)
            return _FakeMgr(mk_path)

        def get_analytics_db(self):
            return _FakeMgr(an_path)

    monkeypatch.setattr("database.router.DatabaseRouter", DomainRouter)
    svc = BandPITService()
    obs = svc.observe_band("exchange", "2026-01-11T00:00:00", symbol="BTC/USDT")
    assert isinstance(obs, BandObservation)
    assert obs.status in {"ready", "limited", "missing"}
    assert obs.observation_time is not None

    panel = svc.get_band_readiness_at("2026-01-11T00:00:00", symbols=["BTC/USDT"])
    assert panel["source"] == "raw_history_band_pit"
    assert panel["market_band_statuses"]["macro"] in {"ready", "limited", "missing"}
    assert panel["assets"][0]["symbol"] == "BTC/USDT"


def test_time_slice_includes_band_readiness_domain():
    assert "band_readiness" in TimeSliceService.DOMAINS
