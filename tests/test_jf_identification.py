"""JF/RFS-grade identification invariants for PIT empirics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pdf.sci.experiment_config import (
    config_content_hash,
    decision_asof_for_payoff_date,
    load_experiment_config,
)
from pdf.sci.run_jf_experiments import consistency_from_signs, directional_signal
from pdf.sci.run_pit_jf_experiments import (
    assign_scarce_expanding,
    delete_band_content,
    scramble_band_content,
)


ROOT = Path(__file__).resolve().parents[1]


def test_experiment_config_hash_stable():
    cfg = load_experiment_config()
    assert cfg["version"]
    assert cfg["_content_hash"] == config_content_hash()
    assert "BTC" in cfg["assets"]
    assert "BNB/USDT" in cfg["bootstrap_symbols"]
    assert cfg["timing"]["protocol"] == "decision_at_prev_close"
    assert cfg["pre_specified_contrast"]["control"] == "Momentum always"


def test_decision_asof_is_previous_close():
    asof = decision_asof_for_payoff_date("2026-02-10")
    assert asof.strftime("%Y-%m-%d %H:%M:%S") == "2026-02-09 23:59:00"


def test_scarce_label_is_expanding_not_full_sample():
    dates = pd.date_range("2025-07-01", periods=100, freq="D")
    rows = []
    for i, d in enumerate(dates):
        # First half thick, second half thin — full-sample q=0.2 would mark early days scarce incorrectly
        b = 0.5 if i < 70 else 0.1
        rows.append({"date": d, "asset": "BTC", "B_hier": b, "outage": 0, "ret": 0.0})
        rows.append({"date": d, "asset": "ETH", "B_hier": b, "outage": 0, "ret": 0.0})
    df = pd.DataFrame(rows)
    out = assign_scarce_expanding(df)
    # Burn-in days should not be scarce
    early = out[out["date"] < dates[60]]
    assert int(early["scarce"].sum()) == 0
    late = out[out["date"] >= dates[80]]
    assert int(late["scarce"].sum()) > 0


def _toy_engine_row(**kwargs):
    base = {
        "date": pd.Timestamp("2026-03-01"),
        "asset": "BTC",
        "ret": 0.01,
        "B_hier": 0.4,
        "U": 0.7,
        "H_cont": 0.8,
        "S": 0.5,
        "C": 0.6,
        "C_base": 0.55,
        "cascade_p": 0.2,
        "mom5": 1.0,
        "detected_regime": "range",
        "macro_tilt": 1.0,
        "alt_tilt": 1.0,
        "st_macro": "ready",
        "st_alternative": "ready",
        "signs_json": json.dumps([1.0, 1.0, -1.0, -1.0]),
        "signal": 1.0,
        "ACWMI": 0.4,
        "WMI": 0.3,
        "outage": 0,
    }
    base.update(kwargs)
    return base


def test_lobo_content_deletion_changes_band_driven_signal():
    # R2b long requires both tilts; content deletion removes that branch.
    df = pd.DataFrame([_toy_engine_row(mom5=0.0, detected_regime="range", macro_tilt=1.0, alt_tilt=1.0, signal=1.0)])
    assert (
        directional_signal(
            {"detected_regime": "range", "cascade_p": 0.2, "mom5": 0.0, "macro_tilt": 1.0, "alt_tilt": 1.0}
        )
        == 1.0
    )
    out = delete_band_content(df, ["macro", "alternative"])
    assert float(out.iloc[0]["signal"]) == 0.0
    assert "ACWMI" in out.columns


def test_scramble_placebo_destroys_tilt_timing():
    rows = [
        _toy_engine_row(
            date=pd.Timestamp("2026-03-01") + pd.Timedelta(days=i),
            macro_tilt=1.0 if i < 6 else -1.0,
            alt_tilt=1.0 if i < 6 else -1.0,
            mom5=float((-1) ** i),
        )
        for i in range(12)
    ]
    df = pd.DataFrame(rows)
    scr = scramble_band_content(df, seed=3)
    # Marginal counts preserved up to readiness masking; sequence timing should differ.
    assert list(scr["macro_tilt"]) != list(df["macro_tilt"])


def test_no_future_timestamp_in_decision_asof_column_if_panel_present():
    panel = ROOT / "pdf" / "data" / "pit_multiband_panel.csv"
    if not panel.exists():
        pytest.skip("PIT panel not built in this environment")
    df = pd.read_csv(panel, parse_dates=["date"])
    if "decision_asof" not in df.columns:
        pytest.skip("Panel predates timing protocol; rebuild with build_pit_archive.py")
    asof = pd.to_datetime(df["decision_asof"])
    payoff = pd.to_datetime(df["date"]).dt.normalize()
    assert (asof < payoff + pd.Timedelta(hours=1)).all()
    # Strict: decision clock on previous calendar day
    assert (asof.dt.normalize() < payoff).all()


def test_consistency_helper_bounds():
    assert 0.0 <= consistency_from_signs([1, 1, 1]) <= 1.0
    assert consistency_from_signs([1, -1]) == pytest.approx(0.0)
