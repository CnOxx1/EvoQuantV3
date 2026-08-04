#!/usr/bin/env python3
"""Reconcile Yahoo close-to-close returns against OKX/exchange daily bars.

Writes pdf/tables/table_return_reconciliation.csv and a JSON summary.
Does not alter the econometric panel; it is a data-quality appendix for the appendix.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import asset_to_symbol, paper_assets

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"
TAB.mkdir(parents=True, exist_ok=True)


def _exchange_daily_returns(db_path: Path, symbol: str) -> pd.Series:
    if not db_path.exists():
        return pd.Series(dtype=float)
    con = sqlite3.connect(str(db_path))
    # Prefer analytics merged_klines, else raw exchange klines.
    for table, db in (
        ("merged_klines", ROOT / "database" / "analytics.db"),
        ("klines", db_path),
    ):
        path = db if table == "merged_klines" else db_path
        if not path.exists():
            continue
        c = sqlite3.connect(str(path))
        try:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        except Exception:
            c.close()
            continue
        if "close" not in cols or "open_time" not in cols:
            c.close()
            continue
        q = f"""
            SELECT open_time, close FROM {table}
            WHERE symbol=? AND timeframe='1d' AND close IS NOT NULL
            ORDER BY open_time
        """
        try:
            raw = pd.read_sql(q, c, params=(symbol,))
        except Exception:
            c.close()
            continue
        c.close()
        if raw.empty:
            continue
        raw["date"] = pd.to_datetime(raw["open_time"], format="mixed").dt.normalize()
        s = raw.drop_duplicates("date", keep="last").set_index("date")["close"].astype(float)
        return s.pct_change().rename("ex_ret")
    con.close()
    return pd.Series(dtype=float)


def main() -> int:
    yahoo_path = DATA / "crypto_daily_yahoo.csv"
    if not yahoo_path.exists():
        print("Missing", yahoo_path)
        return 1
    yahoo = pd.read_csv(yahoo_path, parse_dates=["date"])
    yahoo = yahoo[yahoo["asset"].isin(paper_assets())].dropna(subset=["ret"])
    ex_db = ROOT / "database" / "exchange_data.db"
    rows = []
    for asset, symbol in asset_to_symbol().items():
        y = yahoo.loc[yahoo["asset"] == asset, ["date", "ret"]].copy()
        y["date"] = pd.to_datetime(y["date"]).dt.normalize()
        y = y.set_index("date")["ret"].astype(float)
        ex = _exchange_daily_returns(ex_db, symbol)
        if ex.empty:
            rows.append(
                {
                    "asset": asset,
                    "symbol": symbol,
                    "n_overlap": 0,
                    "corr": None,
                    "mae": None,
                    "median_abs_diff": None,
                    "status": "no_exchange_series",
                }
            )
            continue
        both = pd.concat([y.rename("yahoo"), ex], axis=1, join="inner").dropna()
        if both.empty:
            rows.append(
                {
                    "asset": asset,
                    "symbol": symbol,
                    "n_overlap": 0,
                    "corr": None,
                    "mae": None,
                    "median_abs_diff": None,
                    "status": "no_overlap",
                }
            )
            continue
        diff = (both["yahoo"] - both["ex_ret"]).abs()
        rows.append(
            {
                "asset": asset,
                "symbol": symbol,
                "n_overlap": int(len(both)),
                "corr": round(float(both["yahoo"].corr(both["ex_ret"])), 4),
                "mae": round(float(diff.mean()), 6),
                "median_abs_diff": round(float(diff.median()), 6),
                "status": "ok" if float(both["yahoo"].corr(both["ex_ret"])) >= 0.95 else "divergent",
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "table_return_reconciliation.csv", index=False)
    summary = {
        "n_assets": int(len(out)),
        "n_ok": int((out["status"] == "ok").sum()),
        "n_divergent": int((out["status"] == "divergent").sum()),
        "n_missing": int(out["status"].isin(["no_exchange_series", "no_overlap"]).sum()),
        "mean_corr_ok": (
            None
            if out.loc[out["status"] == "ok", "corr"].empty
            else round(float(out.loc[out["status"] == "ok", "corr"].mean()), 4)
        ),
    }
    (TAB / "table_return_reconciliation.json").write_text(
        json.dumps({"summary": summary, "rows": out.to_dict(orient="records")}, indent=2),
        encoding="utf-8",
    )
    print(out.to_string(index=False))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
