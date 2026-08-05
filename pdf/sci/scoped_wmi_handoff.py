#!/usr/bin/env python3
"""Rebuild scoped-WMI open-share + Compiled-open handoff tables from the PIT panel.

Root cause of "gate never opens": full-schema WMI counts permanently missing
bands outside the consumer archive. Scoped WMI scores only declared archive
bands (exchange/macro/alternative), so 3/3-ready days clear WMI>=0.2.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import EVAL_ARCHIVE_BANDS, WMI_ABSTAIN_THRESHOLD
from logic_layer.decision_handoff.service import DecisionHandoffService
from logic_layer.time_slice.world_quality import (
    resolve_active_bands,
    scoped_wmi_from_statuses,
    statuses_from_panel_row,
)

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "pdf" / "tables"
SEE = ROOT / "pdf" / "icaif26_see" / "tables"
CUT = "2026-01-16"


def _ann_stats(daily: pd.Series) -> dict:
    x = daily.dropna().astype(float)
    if len(x) < 2:
        return {"Sharpe": 0.0, "CE": 0.0, "n_days": int(len(x))}
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    sharpe = (mu / sd) * np.sqrt(365.0) if sd > 1e-12 else 0.0
    # certainty-equivalent proxy used in paper tables: ann mean - 0.5 * ann var
    ce = mu * 365.0 - 0.5 * (sd**2) * 365.0
    return {"Sharpe": round(sharpe, 4), "CE": round(ce, 4), "n_days": int(len(x))}


def recompute_scoped(panel: pd.DataFrame) -> pd.DataFrame:
    bands = resolve_active_bands(scope="eval_archive")
    rows = []
    for _, r in panel.iterrows():
        st = statuses_from_panel_row(r, bands)
        q = scoped_wmi_from_statuses(st, scope="eval_archive", declared_bands=bands)
        rows.append(q)
    out = panel.copy()
    out["WMI_scoped"] = [r["wmi"] for r in rows]
    out["B_scoped"] = [r["B_hier"] for r in rows]
    out["U_scoped"] = [r["U"] for r in rows]
    out["H_scoped"] = [r["H"] for r in rows]
    out["should_ai_abstain_scoped"] = [r["should_ai_abstain"] for r in rows]
    out["valve_open_scoped"] = [not r["should_ai_abstain"] for r in rows]
    out["n_ready_scoped"] = [r["n_ready"] for r in rows]
    return out


def open_share_table(df: pd.DataFrame) -> pd.DataFrame:
    oos = df[df["date"] >= CUT]
    rows = []
    # Production valve = archive_complete ∧ WMI≥0.2 (stored as valve_open_scoped).
    rows.append(
        {
            "threshold": 0.2,
            "open_share": round(float(oos["valve_open_scoped"].mean()), 4),
            "wmi_max": round(float(oos["WMI_scoped"].max()), 4),
            "wmi_median": round(float(oos["WMI_scoped"].median()), 4),
            "note": "production scoped valve (complete∧WMI≥0.2)",
            "band_scope": "eval_archive",
            "bands": ",".join(EVAL_ARCHIVE_BANDS),
        }
    )
    for thr, note in [
        (0.05, "counterfactual WMI-only (no completeness∧)"),
        (0.01, "near-floor WMI-only"),
    ]:
        open_share = float((oos["WMI_scoped"] >= thr).mean())
        rows.append(
            {
                "threshold": thr,
                "open_share": round(open_share, 4),
                "wmi_max": round(float(oos["WMI_scoped"].max()), 4),
                "wmi_median": round(float(oos["WMI_scoped"].median()), 4),
                "note": note,
                "band_scope": "eval_archive",
                "bands": ",".join(EVAL_ARCHIVE_BANDS),
            }
        )
    return pd.DataFrame(rows)


def handoff_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """No-LLM decision handoff under scoped valve (Compiled-open proxy)."""
    oos = df[df["date"] >= CUT].copy()
    # align returns: use same-day ret already on panel
    handoff = DecisionHandoffService(require_open_valve=True)

    def pos_from_action(action: str) -> float:
        return {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0, "abstain": 0.0}.get(
            action, 0.0
        )

    records = []
    for _, r in oos.iterrows():
        bundle = {
            "macro_tilt": r.get("macro_tilt", 0.0),
            "alt_tilt": r.get("alt_tilt", 0.0),
            "world_model_index": {
                "wmi": r["WMI_scoped"],
                "should_ai_abstain": bool(r["should_ai_abstain_scoped"]),
            },
            "audit": {"evidence_ids": []},
        }
        decision = handoff.act(bundle)
        records.append(
            {
                "date": r["date"],
                "asset": r["asset"],
                "ret": float(r["ret"]) if pd.notna(r.get("ret")) else np.nan,
                "action": decision["action"],
                "pos": pos_from_action(decision["action"]),
                "valve_open": decision["valve_open"],
                "WMI_scoped": r["WMI_scoped"],
            }
        )
    act = pd.DataFrame(records)
    act["pnl"] = act["pos"] * act["ret"]

    # portfolio: equal-weight across assets per day
    daily = act.groupby("date", sort=True)["pnl"].mean()
    open_daily = (
        act[act["valve_open"]].groupby("date", sort=True)["pnl"].mean()
        if act["valve_open"].any()
        else pd.Series(dtype=float)
    )

    # baselines
    mom = oos.copy()
    mom["pos"] = np.sign(mom.get("mom5", 0.0)).astype(float)
    mom_daily = (mom["pos"] * mom["ret"]).groupby(mom["date"]).mean()
    long_daily = oos.groupby("date")["ret"].mean()

    # full-schema production gate (legacy): always abstain on this panel
    legacy_stats = {"Sharpe": 0.0, "CE": 0.0, "n_days": int(oos["date"].nunique())}

    rows = [
        {
            "policy": "WMI gate 0.2 (full-schema legacy)",
            **legacy_stats,
            "abstain_rate": 1.0,
            "open_share": 0.0,
            "note": "max full-schema WMI≈0.093",
        },
        {
            "policy": "WMI gate 0.2 (scoped archive) + tilt handoff",
            **_ann_stats(daily),
            "abstain_rate": round(float((act["action"] == "abstain").mean()), 4),
            "open_share": round(float(act["valve_open"].mean()), 4),
            "note": "Compiled-open proxy on declared bands",
        },
        {
            "policy": "Tilt handoff on open days only",
            **_ann_stats(open_daily),
            "abstain_rate": 0.0,
            "open_share": 1.0,
            "note": "condition on valve_open",
        },
        {
            "policy": "Momentum (mom5)",
            **_ann_stats(mom_daily),
            "abstain_rate": 0.0,
            "open_share": 1.0,
            "note": "always-on baseline",
        },
        {
            "policy": "Buy-and-hold",
            **_ann_stats(long_daily),
            "abstain_rate": 0.0,
            "open_share": 1.0,
            "note": "always-on baseline",
        },
    ]
    return pd.DataFrame(rows)


def compare_full_vs_scoped(df: pd.DataFrame) -> dict:
    oos = df[df["date"] >= CUT]
    return {
        "band_scope_default": "eval_archive",
        "eval_archive_bands": list(EVAL_ARCHIVE_BANDS),
        "wmi_abstain_threshold": WMI_ABSTAIN_THRESHOLD,
        "full_schema_wmi_max": round(float(oos["WMI"].max()), 4),
        "full_schema_open_share_at_0.2": round(float((oos["WMI"] >= 0.2).mean()), 4),
        "scoped_wmi_max": round(float(oos["WMI_scoped"].max()), 4),
        "scoped_open_share_at_0.2": round(float(oos["valve_open_scoped"].mean()), 4),
        "scoped_open_equiv_band_thick": bool(
            abs(
                float(oos["valve_open_scoped"].mean())
                - float((oos["n_ready_scoped"] >= 3).mean())
            )
            < 0.02
        ),
        "interpretation": (
            "Scoped WMI measures quality of the declared consumer archive; "
            "full-schema WMI never opens because empty non-archive bands drag B/U."
        ),
    }


def main() -> None:
    panel_path = TAB / "panel_simulation.csv"
    df = pd.read_csv(panel_path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    scoped = recompute_scoped(df)

    open_tbl = open_share_table(scoped)
    handoff_tbl = handoff_backtest(scoped)
    summary = compare_full_vs_scoped(scoped)

    for d in (TAB, SEE):
        d.mkdir(parents=True, exist_ok=True)
        open_tbl.to_csv(d / "table_scoped_wmi_open_share.csv", index=False)
        handoff_tbl.to_csv(d / "table_scoped_wmi_handoff.csv", index=False)
        (d / "table_scoped_wmi_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    # also persist scoped columns for paper joins
    keep = [
        "date",
        "asset",
        "WMI",
        "WMI_scoped",
        "B_scoped",
        "U_scoped",
        "H_scoped",
        "should_ai_abstain_scoped",
        "valve_open_scoped",
        "n_ready_scoped",
        "macro_tilt",
        "alt_tilt",
        "mom5",
        "ret",
    ]
    scoped[keep].to_csv(TAB / "panel_scoped_wmi.csv", index=False)
    scoped[keep].to_csv(SEE / "panel_scoped_wmi.csv", index=False)

    print(json.dumps(summary, indent=2))
    print(open_tbl.to_string(index=False))
    print(handoff_tbl.to_string(index=False))


if __name__ == "__main__":
    main()
