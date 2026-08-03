#!/usr/bin/env python3
"""Long-span external-validity backtest of the R1–R3 mechanism (BTC/ETH, 2017+).

Addresses the single-regime critique: the 200-day OOS window is dominated by
crisis/short states, so mechanism skill could be a one-regime artifact. Here the
same deterministic rule (no band content, tilts = 0; returns-only inputs) runs
on multi-year Yahoo daily data across the 2017 bubble, 2018 bear, 2020 crash,
2020-21 bull, 2022 bear, and the recent cycle.

Outputs:
  pdf/data/crypto_longspan_yahoo.csv        cached returns
  pdf/tables/table_longspan_by_year.csv     per-year mechanism vs baselines
  pdf/tables/table_longspan_summary.csv     full-span stats + bootstrap p
  pdf/tables/table_cascade_calibration.csv  cascade_p deciles vs realized tails
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib.util

_jf_path = Path(__file__).resolve().parent / "run_jf_experiments.py"
_spec = importlib.util.spec_from_file_location("run_jf_experiments", _jf_path)
_jf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_jf)

run_engines = _jf.run_engines
directional_signal = _jf.directional_signal
bootstrap_delta_pvalues = _jf.bootstrap_delta_pvalues
portfolio_stats = _jf.portfolio_stats

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"
ASSETS = {"BTC": "BTC-USD", "ETH": "ETH-USD"}
START = "2017-01-01"


def fetch_yahoo(symbol: str, start: str) -> pd.DataFrame:
    p1 = int(pd.Timestamp(start).timestamp())
    p2 = int(time.time())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={p1}&period2={p2}&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    close = res["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s").normalize(), "close": close})
    df = df.dropna().drop_duplicates(subset=["date"]).sort_values("date")
    return df


def load_returns() -> pd.DataFrame:
    cache = DATA / "crypto_longspan_yahoo.csv"
    if cache.exists():
        return pd.read_csv(cache, parse_dates=["date"])
    frames = []
    for asset, symbol in ASSETS.items():
        px = fetch_yahoo(symbol, START)
        px["ret"] = px["close"].pct_change()
        px["asset"] = asset
        frames.append(px.dropna(subset=["ret"])[["date", "asset", "ret"]])
    out = pd.concat(frames, ignore_index=True).sort_values(["date", "asset"])
    out.to_csv(cache, index=False)
    return out


def build_panel(returns: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for asset, g in returns.groupby("asset"):
        g = g.sort_values("date")
        hist: list[float] = []
        for _, r in g.iterrows():
            eng = run_engines(asset, np.array(hist, dtype=float))
            sig = directional_signal(eng)  # tilts default to 0 (no band archive pre-2025)
            rows.append(
                {
                    "date": r["date"],
                    "asset": asset,
                    "ret": float(r["ret"]),
                    "signal": sig,
                    "mom5": eng["mom5"],
                    "cascade_p": eng["cascade_p"],
                    "detected_regime": eng["detected_regime"],
                }
            )
            hist.append(float(r["ret"]))
    df = pd.DataFrame(rows)
    warm = df.groupby("asset").cumcount()
    return df.loc[warm >= 30].reset_index(drop=True)


def policy_daily(df: pd.DataFrame, mode: str) -> pd.Series:
    if mode == "mechanism":
        pos = df["signal"].astype(float)
    elif mode == "always_long":
        pos = pd.Series(1.0, index=df.index)
    elif mode == "momentum":
        pos = df["mom5"].replace(0.0, 1.0).astype(float)
    else:
        raise ValueError(mode)
    tmp = df[["date", "ret"]].copy()
    tmp["pnl"] = pos.values * tmp["ret"].values
    return tmp.groupby("date")["pnl"].mean().sort_index()


def ann_stats(daily: pd.Series) -> dict:
    mu, sd = float(daily.mean()), float(daily.std(ddof=1) + 1e-12)
    wealth = (1 + daily).cumprod()
    gamma = 2.0
    ce = float((np.mean(np.maximum(1 + daily, 1e-8) ** (1 - gamma))) ** (1 / (1 - gamma)) - 1) * 365
    return {
        "ann_return": round(mu * 365, 4),
        "Sharpe": round(mu / sd * np.sqrt(365), 3),
        "CE": round(ce, 4),
        "max_DD": round(float((wealth / wealth.cummax() - 1).min()), 4),
        "n_days": int(len(daily)),
    }


def main() -> None:
    returns = load_returns()
    print("returns", returns["date"].min().date(), "→", returns["date"].max().date(), len(returns))
    panel_cache = DATA / "longspan_mechanism_panel.csv"
    if panel_cache.exists():
        panel = pd.read_csv(panel_cache, parse_dates=["date"])
    else:
        panel = build_panel(returns)
        panel.to_csv(panel_cache, index=False)
    print("panel", len(panel), "crisis share", round(float((panel["detected_regime"] == "crisis").mean()), 3))

    curves = {m: policy_daily(panel, m) for m in ("mechanism", "always_long", "momentum")}

    # Full-span summary with block bootstrap vs both baselines
    summary_rows = []
    for m, cur in curves.items():
        summary_rows.append({"policy": m, **ann_stats(cur)})
    bp_long = bootstrap_delta_pvalues(curves["mechanism"], curves["always_long"], n_boot=999, block=5)
    bp_mom = bootstrap_delta_pvalues(curves["mechanism"], curves["momentum"], n_boot=999, block=5)
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(TAB / "table_longspan_summary.csv", index=False)
    (TAB / "table_longspan_bootstrap.json").write_text(
        json.dumps({"mechanism_minus_always_long": bp_long, "mechanism_minus_momentum": bp_mom}, indent=2),
        encoding="utf-8",
    )
    print(summary)
    print("mech − always-long:", {k: bp_long[k] for k in ("n_days", "dCE", "p_CE", "ci_dCE_05", "ci_dCE_95")})
    print("mech − momentum:", {k: bp_mom[k] for k in ("n_days", "dCE", "p_CE", "ci_dCE_05", "ci_dCE_95")})

    # Per-year performance (regime balance disclosure)
    panel["year"] = panel["date"].dt.year
    year_rows = []
    for y, g in panel.groupby("year"):
        cur_m = policy_daily(g, "mechanism")
        cur_l = policy_daily(g, "always_long")
        year_rows.append(
            {
                "year": int(y),
                "n_days": int(g["date"].nunique()),
                "crisis_share": round(float((g["detected_regime"] == "crisis").mean()), 3),
                "mech_ann_ret": ann_stats(cur_m)["ann_return"],
                "mech_Sharpe": ann_stats(cur_m)["Sharpe"],
                "long_ann_ret": ann_stats(cur_l)["ann_return"],
                "long_Sharpe": ann_stats(cur_l)["Sharpe"],
            }
        )
    by_year = pd.DataFrame(year_rows)
    by_year.to_csv(TAB / "table_longspan_by_year.csv", index=False)
    print(by_year.to_string())

    # Cascade probability calibration: deciles vs realized next-day left tail
    panel = panel.sort_values(["asset", "date"])
    panel["ret_next"] = panel.groupby("asset")["ret"].shift(-1)
    dec = panel.dropna(subset=["ret_next"]).copy()
    dec["casc_decile"] = pd.qcut(dec["cascade_p"], 10, labels=False, duplicates="drop")
    cal = (
        dec.groupby("casc_decile")
        .agg(
            n=("ret_next", "size"),
            mean_cascade_p=("cascade_p", "mean"),
            mean_ret_next=("ret_next", "mean"),
            p_tail2=("ret_next", lambda s: float((s < -0.02).mean())),
            p_tail5=("ret_next", lambda s: float((s < -0.05).mean())),
        )
        .reset_index()
    )
    cal["mean_cascade_p"] = cal["mean_cascade_p"].round(3)
    cal["mean_ret_next"] = cal["mean_ret_next"].round(5)
    cal["p_tail2"] = cal["p_tail2"].round(3)
    cal["p_tail5"] = cal["p_tail5"].round(3)
    cal.to_csv(TAB / "table_cascade_calibration.csv", index=False)
    print(cal.to_string())
    print("Done.")


if __name__ == "__main__":
    main()
