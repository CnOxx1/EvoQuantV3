#!/usr/bin/env python3
"""Offline q* sensitivity for scoped production valve and WMI-only counterfactual."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from logic_layer.decision_handoff.service import DecisionHandoffService
from pdf.sci.scoped_wmi_handoff import CUT, _ann_stats, recompute_scoped

ROOT = Path(__file__).resolve().parents[2]
TAB = ROOT / "pdf" / "tables"
SEE = ROOT / "pdf" / "icaif26_see" / "tables"
THRESHOLDS = (0.10, 0.15, 0.20, 0.25, 0.30)


def _handoff(oos: pd.DataFrame, thr: float, *, require_complete: bool) -> dict:
    handoff = DecisionHandoffService(require_open_valve=True)
    records = []
    for _, r in oos.iterrows():
        wmi = float(r["WMI_scoped"])
        complete = int(r.get("n_ready_scoped") or 0) >= 3
        should_abs = (wmi < thr) or (require_complete and not complete)
        decision = handoff.act(
            {
                "macro_tilt": r.get("macro_tilt", 0.0),
                "alt_tilt": r.get("alt_tilt", 0.0),
                "world_model_index": {"wmi": wmi, "should_ai_abstain": should_abs},
                "audit": {"evidence_ids": []},
            }
        )
        pos = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0, "abstain": 0.0}.get(
            decision["action"], 0.0
        )
        records.append(
            {
                "date": r["date"],
                "ret": float(r["ret"]) if pd.notna(r.get("ret")) else np.nan,
                "pos": pos,
                "valve_open": decision["valve_open"],
                "action": decision["action"],
            }
        )
    act = pd.DataFrame(records)
    act["pnl"] = act["pos"] * act["ret"]
    daily = act.groupby("date", sort=True)["pnl"].mean()
    stats = _ann_stats(daily)
    return {
        "threshold": thr,
        "rule": "complete∧WMI≥q*" if require_complete else "WMI≥q* only",
        "open_share": round(float(act["valve_open"].mean()), 4),
        "abstain_rate": round(float((act["action"] == "abstain").mean()), 4),
        **stats,
    }


def main() -> None:
    panel = pd.read_csv(TAB / "panel_simulation.csv")
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    oos = recompute_scoped(panel)
    oos = oos[oos["date"] >= CUT].copy()

    prod = pd.DataFrame([_handoff(oos, thr, require_complete=True) for thr in THRESHOLDS])
    wmi_only = pd.DataFrame(
        [_handoff(oos, thr, require_complete=False) for thr in THRESHOLDS]
    )
    full = pd.DataFrame(
        [
            {
                "threshold": thr,
                "open_share": round(float((oos["WMI"] >= thr).mean()), 4),
                "wmi_max": round(float(oos["WMI"].max()), 4),
                "band_scope": "full_schema",
            }
            for thr in THRESHOLDS
        ]
    )
    # gap-day WMI mass for interpretation
    gap = oos[oos["n_ready_scoped"] < 3]
    summary = {
        "cut": CUT,
        "gap_day_share": round(float((oos["n_ready_scoped"] < 3).mean()), 4),
        "gap_wmi_scoped_median": round(float(gap["WMI_scoped"].median()), 4) if len(gap) else None,
        "thick_wmi_scoped_median": round(
            float(oos.loc[oos["n_ready_scoped"] >= 3, "WMI_scoped"].median()), 4
        ),
        "interpretation": (
            "Production valve (complete∧WMI≥q*) is flat for q*∈[0.10,0.30] because "
            "thick days have scoped WMI≈1.0 and gap days fail completeness. "
            "WMI-only counterfactual moves when q* crosses the gap-day WMI mass (~0.14). "
            "Full-schema open share stays 0 for all q*≥0.10."
        ),
    }
    for d in (TAB, SEE):
        d.mkdir(parents=True, exist_ok=True)
        prod.to_csv(d / "table_qstar_sensitivity_scoped.csv", index=False)
        wmi_only.to_csv(d / "table_qstar_sensitivity_wmi_only.csv", index=False)
        full.to_csv(d / "table_qstar_sensitivity_full.csv", index=False)
        (d / "table_qstar_sensitivity_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
    print("PRODUCTION complete∧WMI")
    print(prod.to_string(index=False))
    print("WMI-ONLY")
    print(wmi_only.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
