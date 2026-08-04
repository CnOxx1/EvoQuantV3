#!/usr/bin/env python3
"""Reconcile Yahoo close-to-close returns against exchange daily bars.

Writes pdf/tables/table_return_reconciliation.csv and a JSON summary.
Does not alter the econometric panel; it is a data-quality audit.

Graceful statuses when history is missing:
  skipped_no_exchange_db / no_exchange_table / no_exchange_series /
  no_overlap / insufficient_overlap / ok / divergent
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import asset_to_symbol, paper_assets

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"
TAB.mkdir(parents=True, exist_ok=True)

MIN_OVERLAP = 5


def _load_daily_close_series(db_path: Path, table: str, symbol: str) -> tuple[pd.Series, dict]:
    meta = {
        "source_db": str(db_path),
        "source_table": table,
        "n_bars": 0,
        "status": "ok",
    }
    if not db_path.exists():
        meta["status"] = "skipped_no_exchange_db"
        return pd.Series(dtype=float), meta
    con = sqlite3.connect(str(db_path))
    try:
        exists = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            meta["status"] = "no_exchange_table"
            return pd.Series(dtype=float), meta
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if "close" not in cols or "open_time" not in cols:
            meta["status"] = "no_exchange_table"
            return pd.Series(dtype=float), meta
        raw = pd.read_sql(
            f"""
            SELECT open_time, close FROM {table}
            WHERE symbol=? AND timeframe='1d' AND close IS NOT NULL
            ORDER BY open_time
            """,
            con,
            params=(symbol,),
        )
    except Exception:
        meta["status"] = "no_exchange_series"
        return pd.Series(dtype=float), meta
    finally:
        con.close()

    if raw.empty:
        meta["status"] = "no_exchange_series"
        return pd.Series(dtype=float), meta
    raw["date"] = pd.to_datetime(raw["open_time"], format="mixed").dt.normalize()
    closes = raw.drop_duplicates("date", keep="last").set_index("date")["close"].astype(float)
    meta["n_bars"] = int(len(closes))
    meta["start"] = str(closes.index.min().date()) if len(closes) else None
    meta["end"] = str(closes.index.max().date()) if len(closes) else None
    return closes.pct_change().rename("ex_ret"), meta


def load_exchange_daily_returns(
    symbol: str,
    *,
    analytics_db: Path | None = None,
    exchange_db: Path | None = None,
) -> tuple[pd.Series, dict]:
    """Prefer analytics.merged_klines, else exchange_data.klines."""
    analytics_db = analytics_db or (ROOT / "database" / "analytics.db")
    exchange_db = exchange_db or (ROOT / "database" / "exchange_data.db")
    attempts: list[dict] = []

    for path, table in (
        (analytics_db, "merged_klines"),
        (exchange_db, "klines"),
    ):
        series, meta = _load_daily_close_series(path, table, symbol)
        attempts.append(meta)
        if not series.empty:
            meta = dict(meta)
            meta["attempts"] = attempts
            return series, meta

    # Pick the most informative empty status
    status = "no_exchange_series"
    for meta in attempts:
        if meta.get("status") == "no_exchange_series":
            status = "no_exchange_series"
            break
        if meta.get("status") == "no_exchange_table":
            status = "no_exchange_table"
        elif meta.get("status") == "skipped_no_exchange_db" and status == "no_exchange_series":
            status = "skipped_no_exchange_db"
    return pd.Series(dtype=float), {"status": status, "attempts": attempts, "n_bars": 0}


def reconcile_asset(
    asset: str,
    symbol: str,
    yahoo: pd.Series,
    *,
    analytics_db: Path | None = None,
    exchange_db: Path | None = None,
) -> dict:
    y = yahoo.copy()
    y.index = pd.to_datetime(y.index).normalize()
    ex, meta = load_exchange_daily_returns(
        symbol, analytics_db=analytics_db, exchange_db=exchange_db
    )
    base = {
        "asset": asset,
        "symbol": symbol,
        "n_yahoo": int(len(y.dropna())),
        "n_exchange": int(meta.get("n_bars") or 0),
        "n_overlap": 0,
        "corr": None,
        "mae": None,
        "median_abs_diff": None,
        "source_db": None,
        "source_table": None,
        "exchange_start": meta.get("start"),
        "exchange_end": meta.get("end"),
        "status": meta.get("status") or "no_exchange_series",
    }
    if ex.empty:
        return base

    both = pd.concat([y.rename("yahoo"), ex], axis=1, join="inner").dropna()
    base["source_db"] = meta.get("source_db")
    base["source_table"] = meta.get("source_table")
    base["n_overlap"] = int(len(both))
    if both.empty:
        base["status"] = "no_overlap"
        return base
    if len(both) < MIN_OVERLAP:
        base["status"] = "insufficient_overlap"
        return base

    corr = float(both["yahoo"].corr(both["ex_ret"]))
    if corr is None or (isinstance(corr, float) and (math.isnan(corr) or math.isinf(corr))):
        base["status"] = "insufficient_overlap"
        return base
    diff = (both["yahoo"] - both["ex_ret"]).abs()
    base["corr"] = round(corr, 4)
    base["mae"] = round(float(diff.mean()), 6)
    base["median_abs_diff"] = round(float(diff.median()), 6)
    base["status"] = "ok" if corr >= 0.95 else "divergent"
    return base


def main() -> int:
    yahoo_path = DATA / "crypto_daily_yahoo.csv"
    if not yahoo_path.exists():
        print("Missing", yahoo_path)
        return 1
    yahoo = pd.read_csv(yahoo_path, parse_dates=["date"])
    yahoo = yahoo[yahoo["asset"].isin(paper_assets())].dropna(subset=["ret"])
    analytics_db = ROOT / "database" / "analytics.db"
    exchange_db = ROOT / "database" / "exchange_data.db"

    rows = []
    for asset, symbol in asset_to_symbol().items():
        y = yahoo.loc[yahoo["asset"] == asset, ["date", "ret"]].copy()
        y["date"] = pd.to_datetime(y["date"]).dt.normalize()
        series = y.set_index("date")["ret"].astype(float)
        rows.append(
            reconcile_asset(
                asset,
                symbol,
                series,
                analytics_db=analytics_db,
                exchange_db=exchange_db,
            )
        )

    out = pd.DataFrame(rows)
    out.to_csv(TAB / "table_return_reconciliation.csv", index=False)
    missing_statuses = {
        "no_exchange_series",
        "no_overlap",
        "skipped_no_exchange_db",
        "no_exchange_table",
        "insufficient_overlap",
    }
    summary = {
        "n_assets": int(len(out)),
        "n_ok": int((out["status"] == "ok").sum()),
        "n_divergent": int((out["status"] == "divergent").sum()),
        "n_missing": int(out["status"].isin(missing_statuses).sum()),
        "mean_corr_ok": (
            None
            if out.loc[out["status"] == "ok", "corr"].empty
            else round(float(out.loc[out["status"] == "ok", "corr"].mean()), 4)
        ),
        "analytics_db_exists": analytics_db.exists(),
        "exchange_db_exists": exchange_db.exists(),
    }
    # JSON-safe: replace NaN
    records = []
    for rec in out.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean[k] = None
            else:
                clean[k] = v
        records.append(clean)
    (TAB / "table_return_reconciliation.json").write_text(
        json.dumps({"summary": summary, "rows": records}, indent=2),
        encoding="utf-8",
    )
    print(out.to_string(index=False))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
