"""Unit tests for JF paper inference helpers: bootstrap p-values and mechanism R1–R3."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pdf.sci.run_jf_experiments import (
    bootstrap_delta_pvalues,
    directional_signal,
    mechanism_component_definitions,
)


def test_mechanism_component_definitions_cover_named_inputs():
    defs = mechanism_component_definitions()
    names = {d["component"] for d in defs}
    assert {"cascade_p", "mom5", "signal", "C (consistency)", "S (signal integrity)"} <= names
    for row in defs:
        assert row["formula"]
        assert row["role"]


def test_directional_signal_r1_r2_r3():
    # R1: crisis → short
    assert directional_signal({"detected_regime": "crisis", "cascade_p": 0.1, "mom5": 1.0}) == -1.0
    # R1: cascade threshold → short even in non-crisis
    assert directional_signal({"detected_regime": "range", "cascade_p": 0.60, "mom5": 1.0}) == -1.0
    # R2: trend + positive mom + low cascade → long
    assert directional_signal({"detected_regime": "trend", "cascade_p": 0.2, "mom5": 1.0}) == 1.0
    # R3: fallback to sign(mom5)
    assert directional_signal({"detected_regime": "range", "cascade_p": 0.2, "mom5": -1.0}) == -1.0
    assert directional_signal({"detected_regime": "range", "cascade_p": 0.2, "mom5": 0.0}) == 0.0


def test_bootstrap_rejects_strong_delta_and_not_identical():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2025-01-01", periods=200, freq="D")
    strong = pd.Series(rng.normal(0.02, 0.01, 200), index=idx)
    weak = pd.Series(rng.normal(0.00, 0.01, 200), index=idx)
    res = bootstrap_delta_pvalues(strong, weak, n_boot=399, block=5, seed=7)
    assert res["p_CE"] is not None
    assert res["p_CE"] < 0.05
    assert res["ci95_excludes_0_CE"] is True

    same = bootstrap_delta_pvalues(strong, strong, n_boot=399, block=5, seed=8)
    assert same["dCE"] == 0.0
    assert same["p_CE"] > 0.5
    assert same["ci95_excludes_0_CE"] is False
