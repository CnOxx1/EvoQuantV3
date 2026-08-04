"""Tests for raw PIT construction path and return reconciliation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from pdf.sci.build_pit_archive import (
    archive_history_inventory,
    table_exists,
)
from pdf.sci.reconcile_returns import load_exchange_daily_returns, reconcile_asset


def _seed_exchange_db(path: Path, *, n: int = 30) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE klines (
            symbol TEXT, exchange TEXT, timeframe TEXT, open_time TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL
        )
        """
    )
    start = pd.Timestamp("2026-01-01")
    px = 100.0
    for i in range(n):
        d = start + pd.Timedelta(days=i)
        px *= 1.01
        con.execute(
            "INSERT INTO klines VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "BTC/USDT",
                "okx",
                "1d",
                d.strftime("%Y-%m-%dT00:00:00"),
                px,
                px,
                px,
                px,
                1.0,
            ),
        )
    con.commit()
    con.close()


def _seed_market_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE macro_timeseries (
            factor_id TEXT, interval TEXT, observation_time TEXT,
            available_at TEXT, value REAL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE alternative_timeseries (
            factor_id TEXT, entity_key TEXT, interval TEXT,
            observation_time TEXT, value REAL
        )
        """
    )
    for i in range(20):
        d = (pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)).strftime("%Y-%m-%dT00:00:00")
        con.execute(
            "INSERT INTO macro_timeseries VALUES (?,?,?,?,?)",
            ("vix", "1d", d, d, 20.0 - i * 0.1),
        )
        con.execute(
            "INSERT INTO alternative_timeseries VALUES (?,?,?,?,?)",
            ("stablecoin_net_supply_change_7d", "GLOBAL", "1d", d, 1e8),
        )
    con.commit()
    con.close()


def test_archive_history_inventory_prefers_merged_or_klines(tmp_path, monkeypatch):
    ex = tmp_path / "ex.db"
    mk = tmp_path / "mk.db"
    an = tmp_path / "an.db"
    _seed_exchange_db(ex, n=5)
    _seed_market_db(mk)
    # analytics empty except schema
    con = sqlite3.connect(an)
    con.execute(
        "CREATE TABLE merged_klines (symbol TEXT, timeframe TEXT, open_time TEXT, close REAL)"
    )
    con.commit()
    con.close()

    conns = {
        "exchange": sqlite3.connect(ex),
        "market": sqlite3.connect(mk),
        "analytics": sqlite3.connect(an),
    }
    inv = archive_history_inventory(conns)
    assert inv["usable_for_raw_rebuild"] is True
    assert inv["klines"] == 5
    assert inv["durable_content_present"] is True
    for c in conns.values():
        c.close()


def test_archive_history_inventory_merged_klines_alone_is_usable(tmp_path):
    ex = tmp_path / "ex.db"
    mk = tmp_path / "mk.db"
    an = tmp_path / "an.db"
    sqlite3.connect(ex).close()
    sqlite3.connect(mk).close()
    con = sqlite3.connect(an)
    con.execute(
        "CREATE TABLE merged_klines (symbol TEXT, timeframe TEXT, open_time TEXT, close REAL)"
    )
    con.execute(
        "INSERT INTO merged_klines VALUES (?,?,?,?)",
        ("BTC/USDT", "1d", "2026-01-01T00:00:00", 100.0),
    )
    con.commit()
    con.close()
    conns = {
        "exchange": sqlite3.connect(ex),
        "market": sqlite3.connect(mk),
        "analytics": sqlite3.connect(an),
    }
    inv = archive_history_inventory(conns)
    assert inv["usable_for_raw_rebuild"] is True
    assert inv["merged_klines"] == 1
    for c in conns.values():
        c.close()


def test_reconcile_from_exchange_klines(tmp_path):
    ex = tmp_path / "exchange_data.db"
    an = tmp_path / "analytics.db"
    # Varying closes so return correlation is well-defined
    con = sqlite3.connect(ex)
    con.execute(
        """
        CREATE TABLE klines (
            symbol TEXT, exchange TEXT, timeframe TEXT, open_time TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL
        )
        """
    )
    rng = [100.0]
    for i in range(1, 40):
        rng.append(rng[-1] * (1.0 + 0.01 * ((-1) ** i) + 0.002 * i))
    for i, px in enumerate(rng):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        con.execute(
            "INSERT INTO klines VALUES (?,?,?,?,?,?,?,?,?)",
            ("BTC/USDT", "okx", "1d", d.strftime("%Y-%m-%dT00:00:00"), px, px, px, px, 1.0),
        )
    con.commit()
    con.close()
    sqlite3.connect(an).close()

    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    closes = pd.Series(rng, index=dates)
    yahoo = closes.pct_change()

    row = reconcile_asset(
        "BTC",
        "BTC/USDT",
        yahoo,
        analytics_db=an,
        exchange_db=ex,
    )
    assert row["status"] == "ok"
    assert row["n_overlap"] >= 5
    assert row["corr"] >= 0.95
    assert row["source_table"] == "klines"


def test_reconcile_prefers_merged_klines(tmp_path):
    ex = tmp_path / "exchange_data.db"
    an = tmp_path / "analytics.db"
    sqlite3.connect(ex).close()
    con = sqlite3.connect(an)
    con.execute(
        """
        CREATE TABLE merged_klines (
            symbol TEXT, timeframe TEXT, open_time TEXT, close REAL
        )
        """
    )
    px = 50.0
    for i in range(20):
        d = pd.Timestamp("2026-02-01") + pd.Timedelta(days=i)
        px *= 1.02
        con.execute(
            "INSERT INTO merged_klines VALUES (?,?,?,?)",
            ("ETH/USDT", "1d", d.strftime("%Y-%m-%dT00:00:00"), px),
        )
    con.commit()
    con.close()

    series, meta = load_exchange_daily_returns(
        "ETH/USDT", analytics_db=an, exchange_db=ex
    )
    assert not series.empty
    assert meta["source_table"] == "merged_klines"


def test_reconcile_empty_dbs_graceful(tmp_path):
    ex = tmp_path / "missing_ex.db"
    an = tmp_path / "missing_an.db"
    yahoo = pd.Series([0.01, 0.02], index=pd.date_range("2026-01-01", periods=2, freq="D"))
    row = reconcile_asset("BTC", "BTC/USDT", yahoo, analytics_db=an, exchange_db=ex)
    assert row["status"] in {
        "skipped_no_exchange_db",
        "no_exchange_series",
        "no_exchange_table",
    }
    assert row["corr"] is None


def test_table_exists_helper(tmp_path):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE foo (x INTEGER)")
    con.commit()
    assert table_exists(con, "foo")
    assert not table_exists(con, "bar")
    con.close()
