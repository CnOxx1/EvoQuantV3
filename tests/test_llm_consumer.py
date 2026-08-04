"""Tests for the pre-registered LLM consumer validation harness."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pdf.sci.llm_consumer.eval import build_compiled_bundle, build_raw_bundle, evaluate_model
from pdf.sci.llm_consumer.providers.mock import get_provider


def test_action_schema_exists_and_lists_abstain():
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "pdf/sci/llm_consumer/schemas/action.json").read_text()
    )
    assert "abstain" in schema["properties"]["action"]["enum"]


def test_compiled_aware_provider_abstains_when_world_thin():
    p = get_provider("mock-compiled-aware")
    bundle = {
        "mom5": 1.0,
        "macro_tilt": 1.0,
        "alt_tilt": 1.0,
        "cascade_p": 0.1,
        "detected_regime": "range",
        "abstain_threshold": 0.25,
        "world_model_index": {"wmi": 0.1, "acwmi": 0.1, "should_ai_abstain": True},
    }
    dec = p.decide(treatment="compiled", prompt="x", bundle=bundle)
    assert dec.action == "abstain"
    assert dec.position() == 0.0


def test_raw_bundle_has_no_world_model_index():
    row = pd.Series(
        {
            "date": "2026-03-01",
            "asset": "BTC",
            "mom5": 1.0,
            "ret": 0.01,
            "WMI": 0.5,
            "ACWMI": 0.5,
        }
    )
    raw = build_raw_bundle(row)
    compiled = build_compiled_bundle(row)
    assert "world_model_index" not in raw
    assert "world_model_index" in compiled


def test_within_model_delta_runs_on_tiny_panel():
    rows = []
    for i in range(40):
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "asset": "BTC",
                "ret": 0.001 * ((-1) ** i),
                "mom5": 1.0 if i % 2 == 0 else -1.0,
                "macro_tilt": 1.0,
                "alt_tilt": 1.0,
                "cascade_p": 0.2,
                "detected_regime": "range",
                "B_hier": 0.4,
                "WMI": 0.5,
                "ACWMI": 0.5,
                "st_exchange": "ready",
                "st_macro": "ready",
                "st_alternative": "ready",
            }
        )
    df = pd.DataFrame(rows)
    res = evaluate_model(df, "mock-compiled-aware")
    assert "dCE_compiled_minus_raw" in res["delta"]
    assert {r["treatment"] for r in res["rows"]} == {"compiled", "raw"}
