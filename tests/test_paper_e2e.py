"""E2E-ish: seed panel rows → persist paper objects → load via helper/API contract."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pdf.sci.persist_paper_objects import (
    load_paper_world_model,
    panel_to_snapshot_rows,
    persist_paper_world_model,
)


def _mini_panel(n: int = 8) -> pd.DataFrame:
    rows = []
    for i in range(n):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        for asset in ("BTC", "ETH"):
            rows.append(
                {
                    "date": d,
                    "asset": asset,
                    "symbol": f"{asset}/USDT",
                    "B_hier": 0.55,
                    "U": 0.7,
                    "H_cont": 0.8,
                    "S": 0.75,
                    "C": 0.65,
                    "C_base": 0.6,
                    "WMI": 0.4,
                    "ACWMI": 0.45,
                    "macro_tilt": 1.0 if i % 2 == 0 else 0.0,
                    "alt_tilt": 1.0,
                    "signal": 1.0,
                    "detected_regime": "range",
                    "mom5": 1.0,
                    "cascade_p": 0.2,
                    "scarce": 0,
                    "outage": 0,
                    "vix_chg5": -0.5,
                    "dxy_chg5": -0.4,
                }
            )
    return pd.DataFrame(rows)


def test_panel_to_snapshot_rows_provenance():
    rows = panel_to_snapshot_rows(_mini_panel(2))
    assert len(rows) == 4
    assert rows[0]["acwmi_input_source"] == "paper_engines"
    assert "paper_pit_engines" in rows[0]["content_source_json"]


def test_persist_and_load_roundtrip(tmp_path: Path):
    db = tmp_path / "analytics.db"
    df = _mini_panel(5)
    n = persist_paper_world_model(df, db_path=db, replace=True)
    assert n == 10
    loaded = load_paper_world_model(db_path=db, asset="BTC", limit=20)
    assert len(loaded) == 5
    assert loaded[0]["acwmi_input_source"] == "paper_engines"
    assert loaded[0]["content_provenance"]["source"] == "paper_pit_engines"
    one = load_paper_world_model(db_path=db, date="2026-01-01", asset="ETH")
    assert len(one) == 1
    assert one[0]["ACWMI"] == pytest.approx(0.45)


def test_joint_alt_tilt_construction_and_inject():
    from pdf.sci.run_longspan_content_audit import (
        build_alt_tilts,
        build_joint_content_tilts,
        inject_content,
    )

    days = pd.date_range("2020-01-01", periods=40, freq="D")
    # Rising then falling supply → positive then negative 7d changes after lag
    circ = pd.Series(range(40), dtype=float) * 1e9 + 1e11
    stable = pd.DataFrame(
        {"date": days, "stablecoin_circ_usd": circ, "ssc7": circ.diff(7)}
    )
    alt = build_alt_tilts(stable)
    assert set(alt["alt_tilt"].unique()).issubset({-1.0, 0.0, 1.0})
    assert (alt["alt_tilt"] > 0).any()

    macro = pd.DataFrame(
        {
            "date": days,
            "vix": list(range(40, 0, -1)),  # falling → risk-on with falling dxy
            "dxy": list(range(120, 80, -1)),
        }
    )
    joint = build_joint_content_tilts(macro, stable)
    assert "macro_tilt" in joint.columns and "alt_tilt" in joint.columns
    assert ((joint["macro_tilt"] > 0) & (joint["alt_tilt"] > 0)).any()

    panel = pd.DataFrame(
        {
            "date": days[10:20],
            "asset": "BTC",
            "ret": 0.01,
            "signal": 0.0,
            "mom5": 1.0,
            "cascade_p": 0.1,
            "detected_regime": "range",
        }
    )
    with_c = inject_content(panel, joint)
    # Range + both tilts > 0 + mom5 >= 0 → R2b long
    assert (with_c["signal"] == 1.0).any()


def test_availability_shock_api_object_contract():
    """O_t helper remains the first-class availability surface."""
    from data_layer.data_quality.availability import tag_availability_shock_metadata

    meta = json.loads(tag_availability_shock_metadata(band="alternative", planted=True))
    assert meta["event_kind"] == "availability_shock"
    assert meta["outage_flag"] is True


def test_attach_paper_engines_onto_readiness_row(tmp_path: Path):
    from logic_layer.ai_market_context.service import AIMarketContextService

    db = tmp_path / "analytics.db"
    persist_paper_world_model(_mini_panel(3), db_path=db, replace=True)
    row = AIMarketContextService._attach_paper_engines(
        {
            "asset": "BTC",
            "readiness_score": 0.2,
            "ready_band_count": 1,
            "limited_band_count": 0,
            "missing_band_count": 7,
        },
        "BTC",
        db_path=db,
    )
    assert row["S"] == pytest.approx(0.75)
    assert row["C"] == pytest.approx(0.65)
    assert row["signal_integrity"] == pytest.approx(0.75)
    assert row["paper_world_model_snapshot"]["source"] == "paper_world_model_snapshots"
    s, c, src = AIMarketContextService._acwmi_proxies(
        asset_readiness_row=row, data_quality_flags=["ignored"]
    )
    assert src == "paper_engines"
    assert s == pytest.approx(0.75)
    assert c == pytest.approx(0.65)
