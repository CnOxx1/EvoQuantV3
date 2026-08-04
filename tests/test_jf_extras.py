"""Tests for orthogonal LOBO, planted shocks, and compilation-wedge bridge."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from pdf.sci.run_pit_jf_experiments import (
    _macro_tilt_from_chgs,
    compilation_wedge_bridge,
    delete_macro_component,
    plant_availability_shocks,
)


def _rows(n: int = 30) -> pd.DataFrame:
    rows = []
    for i in range(n):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        for asset in ("BTC", "ETH"):
            vix = -0.5 if i % 3 == 0 else 0.5
            dxy = -0.4 if i % 3 == 0 else 0.4
            rows.append(
                {
                    "date": d,
                    "asset": asset,
                    "ret": 0.001 * ((-1) ** i),
                    "B_hier": 0.4,
                    "U": 0.7,
                    "H_cont": 0.8,
                    "S": 0.5,
                    "C": 0.6,
                    "C_base": 0.55,
                    "WMI": 0.3,
                    "ACWMI": 0.35,
                    "cascade_p": 0.2,
                    "mom5": 1.0 if i % 2 == 0 else -1.0,
                    "detected_regime": "range",
                    "macro_tilt": _macro_tilt_from_chgs(vix, dxy),
                    "alt_tilt": 1.0,
                    "vix_chg5": vix,
                    "dxy_chg5": dxy,
                    "st_macro": "ready",
                    "st_alternative": "ready",
                    "st_exchange": "ready",
                    "signs_json": json.dumps([1.0, -1.0]),
                    "signal": 1.0,
                    "outage": 0,
                    "market_outage": 0,
                }
            )
    return pd.DataFrame(rows)


def test_macro_tilt_conjunction():
    assert _macro_tilt_from_chgs(-1.0, -1.0) == 1.0
    assert _macro_tilt_from_chgs(1.0, 1.0) == -1.0
    assert _macro_tilt_from_chgs(-1.0, 1.0) == 0.0


def test_delete_vix_breaks_conjunction_tilt():
    df = _rows(6)
    # Days with both negative chgs have macro_tilt +1
    assert (df.loc[df["vix_chg5"] < 0, "macro_tilt"] == 1.0).all()
    out = delete_macro_component(df, "vix")
    # Zeroing VIX change forces tilt to 0 (conjunction fails)
    assert float(out["macro_tilt"].abs().max()) == 0.0


def test_planted_shocks_mark_dates_and_zero_content():
    df = _rows(40)
    out = plant_availability_shocks(df, rate=0.1, bands=["macro"], seed=1)
    assert "planted_shock" in out.columns
    assert int(out["planted_shock"].sum()) > 0
    shocked = out[out["planted_shock"] == 1]
    assert (shocked["st_macro"] == "missing").all()
    assert (shocked["macro_tilt"] == 0.0).all()


def test_compilation_wedge_bridge_runs():
    df = _rows(80)
    cut = pd.Timestamp("2026-02-10")
    res = compilation_wedge_bridge(df, cut)
    assert res["status"] == "ok"
    assert "dR2_compiled_minus_thin" in res
    assert res["compiled"]["n_oos"] > 0


def test_stationary_bootstrap_indices_and_method():
    from pdf.sci.run_jf_experiments import (
        bootstrap_delta_pvalues,
        stationary_bootstrap_indices,
    )

    rng = np.random.default_rng(0)
    idx = stationary_bootstrap_indices(50, 5.0, 7, rng)
    assert idx.shape == (7, 50)
    assert idx.min() >= 0 and idx.max() < 50

    dates = pd.date_range("2026-01-01", periods=120, freq="D")
    strong = pd.Series(np.random.default_rng(1).normal(0.02, 0.01, 120), index=dates)
    weak = pd.Series(np.random.default_rng(2).normal(0.0, 0.01, 120), index=dates)
    res = bootstrap_delta_pvalues(strong, weak, n_boot=199, block=5, method="stationary")
    assert res["method"] == "stationary"
    assert res["p_CE"] is not None and res["p_CE"] < 0.05


def test_longspan_content_tilt_construction():
    from pdf.sci.run_longspan_content_audit import build_content_tilts

    days = pd.date_range("2020-01-01", periods=30, freq="D")
    macro = pd.DataFrame(
        {
            "date": days,
            "vix": np.linspace(30, 20, 30),   # falling VIX
            "dxy": np.linspace(100, 95, 30),  # falling DXY → risk-on
        }
    )
    tilts = build_content_tilts(macro)
    assert (tilts["macro_tilt"] == 1.0).all()
    # lag-1: first usable day requires 6 prior observations
    assert tilts["date"].min() >= days[6]
