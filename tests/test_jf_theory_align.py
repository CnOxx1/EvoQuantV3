"""Tests for theory-aligned LOBO telescope, CE gamma, and jackknife helpers."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pdf.sci.run_jf_experiments import portfolio_stats
from pdf.sci.run_pit_jf_experiments import (
    ce_gamma_sensitivity,
    compilation_wedge_bridge,
    leave_one_asset_jackknife,
)


def _toy_oos(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        for j, asset in enumerate(("BTC", "ETH", "SOL")):
            rows.append(
                {
                    "date": d,
                    "asset": asset,
                    "ret": 0.002 * ((-1) ** (i + j)),
                    "signal": 1.0 if i % 3 else 0.0,
                    "mom5": 1.0 if i % 2 == 0 else -1.0,
                    "cascade_p": 0.2,
                    "detected_regime": "range",
                    "macro_tilt": 1.0,
                    "alt_tilt": 1.0,
                    "B_hier": 0.5,
                    "U": 0.7,
                    "H_cont": 0.8,
                    "S": 0.6,
                    "C": 0.6,
                    "WMI": 0.4,
                    "ACWMI": 0.45,
                    "outage": 0,
                    "st_macro": "ready",
                    "st_alternative": "ready",
                    "st_exchange": "ready",
                    "signs_json": json.dumps([1.0, -1.0]),
                    "C_base": 0.55,
                    "detect_conf": 0.5,
                }
            )
    return pd.DataFrame(rows)


def test_portfolio_stats_risk_aversion_changes_ce():
    df = _toy_oos(30)
    pos = pd.Series(np.ones(len(df)), index=df.index)
    ce2 = portfolio_stats(df, pos, risk_aversion=2.0)["CE"]
    ce6 = portfolio_stats(df, pos, risk_aversion=6.0)["CE"]
    # Higher risk aversion cannot raise CE for a risky portfolio
    assert ce6 <= ce2 + 1e-9


def test_ce_gamma_sensitivity_grid():
    oos = _toy_oos(50)
    params = {"casc_thr": 0.6, "ac_thr": 0.25, "c_thr": 0.25, "casc_only_thr": 0.6}
    out = ce_gamma_sensitivity(oos, params)
    assert set(out["risk_aversion"]) == {1.0, 2.0, 4.0, 6.0}
    assert set(out["cost_bps"]) == {0.0, 10.0, 25.0}
    assert len(out) == 12


def test_leave_one_asset_jackknife_covers_each_asset():
    oos = _toy_oos(40)
    params = {"casc_thr": 0.6, "ac_thr": 0.25, "c_thr": 0.25, "casc_only_thr": 0.6}
    out = leave_one_asset_jackknife(oos, params)
    dropped = set(out["asset_dropped"])
    assert "(none)" in dropped
    assert {"BTC", "ETH", "SOL"} <= dropped


def test_compilation_wedge_bridge_has_sign_hit_and_bootstrap():
    df = _toy_oos(80)
    # Need history variation for engines-like features
    df["mom5"] = np.where(df.index % 2 == 0, 1.0, -1.0)
    cut = pd.Timestamp("2026-02-01")
    res = compilation_wedge_bridge(df, cut)
    assert res["status"] == "ok"
    assert "sign_hit" in res["compiled"]
    assert "bootstrap_dCE" in res
    assert "dCE_ann_compiled_minus_thin" in res
