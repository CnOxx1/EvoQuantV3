#!/usr/bin/env python3
"""Migrate a same-day-asof PIT panel to the previous-close decision clock.

When SQLite history is empty (common in fresh CI VMs), we cannot rebuild band
statuses from raw tables. This migrator implements the protocol algebraically:

  old row at calendar day s carries statuses evaluated at s 23:59.
  For payoff day t under decision_at_prev_close, use statuses from old row s=t-1.

Returns / content tilts are left as-is (content features already use lag-1).
Writes a new pit_multiband_panel.csv and updates pit_archive_summary.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import config_manifest, decision_asof_for_payoff_date

DATA = Path(__file__).resolve().parents[1] / "data"


def migrate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    status_cols = [c for c in df.columns if c.startswith("st_") or c.startswith("age_")]
    world_cols = [
        c
        for c in (
            "B_hier",
            "U",
            "H_cont",
            "WMI",
            "ACWMI_world",
            "n_ready",
            "n_limited",
            "n_missing",
            "macro_age",
            "outage",
            "market_outage",
            "shock_bands",
        )
        if c in df.columns
    ]
    shift_cols = status_cols + world_cols
    pieces = []
    for asset, g in df.groupby("asset", sort=False):
        g = g.sort_values("date").copy()
        shifted = g[shift_cols].shift(1)
        # First day per asset has no previous close → drop
        keep = shifted.notna().any(axis=1)
        g.loc[:, shift_cols] = shifted
        g = g.loc[keep].copy()
        g["decision_asof"] = [decision_asof_for_payoff_date(d).isoformat() for d in g["date"]]
        g["timing_protocol"] = "decision_at_prev_close"
        g["timing_migration"] = "shift_status_from_prev_calendar_day"
        pieces.append(g)
    out = pd.concat(pieces, ignore_index=True)
    return out


def main() -> int:
    src = DATA / "pit_multiband_panel.csv"
    if not src.exists():
        raise SystemExit(f"Missing {src}")
    df = pd.read_csv(src, parse_dates=["date"])
    out = migrate(df)
    out.to_csv(src, index=False)
    bands = [c[3:] for c in out.columns if c.startswith("st_")]
    summary = {
        "n_rows": int(len(out)),
        "n_days": int(out["date"].nunique()),
        "start": str(pd.Timestamp(out["date"].min()).date()),
        "end": str(pd.Timestamp(out["date"].max()).date()),
        "mean_ready": float(out["n_ready"].mean()) if "n_ready" in out.columns else None,
        "outage_rate": float(out["outage"].mean()) if "outage" in out.columns else None,
        "band_ready_rates": {
            b: float((out[f"st_{b}"] == "ready").mean()) for b in bands if f"st_{b}" in out.columns
        },
        "experiment_config": config_manifest(),
        "timing_protocol": "decision_at_prev_close",
        "timing_migration": "shift_status_from_prev_calendar_day",
        "note": (
            "Migrated from archived same-day-asof panel because local SQLite history "
            "was empty; statuses for day t are taken from archived day t-1 EOD."
        ),
    }
    (DATA / "pit_archive_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Wrote", src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
