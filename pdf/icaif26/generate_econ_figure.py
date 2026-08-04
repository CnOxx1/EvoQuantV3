#!/usr/bin/env python3
"""OOS economics figure: cumulative wealth + per-asset dCE bars.

Output: figures/fig_oos_economics.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from pdf.sci.run_jf_experiments import portfolio_stats, strategy_positions  # noqa: E402

PANEL = HERE.parent / "tables" / "panel_simulation.csv"
OUT = HERE / "figures" / "fig_oos_economics.png"

POLICIES = [
    ("World-model rule", "thick_ungated", "#2f6f4f", 1.9),
    ("Momentum", "mom_always", "#4a7fb5", 1.4),
    ("Buy-and-hold", "always_long", "#b8514e", 1.4),
]


def main() -> int:
    p = pd.read_csv(PANEL, parse_dates=["date"])
    dates = sorted(p["date"].unique())
    cut = dates[200]
    oos = p[p["date"] >= cut].copy()

    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(7.0, 2.5), dpi=200, gridspec_kw={"width_ratios": [1.35, 1.0]}
    )

    for label, key, color, lw in POLICIES:
        st = portfolio_stats(oos, strategy_positions(oos, key, {}))
        wealth = (1 + st["daily"]).cumprod()
        ax1.plot(wealth.index, wealth.values, label=label, color=color, lw=lw)
    ax1.axhline(1.0, color="#999999", lw=0.7, ls=":")
    ax1.set_ylabel("Cumulative wealth", fontsize=8.5)
    ax1.set_title("OOS equity curves (10 assets, equal weight)", fontsize=8.2)
    ax1.legend(fontsize=7.0, frameon=False, loc="lower left")
    ax1.tick_params(labelsize=7)
    ax1.spines[["top", "right"]].set_visible(False)

    rows = []
    for a in sorted(oos["asset"].unique()):
        sub = oos[oos["asset"] == a]
        mech = portfolio_stats(sub, strategy_positions(sub, "thick_ungated", {}))
        mom = portfolio_stats(sub, strategy_positions(sub, "mom_always", {}))
        rows.append((a, mech["CE"] - mom["CE"]))
    rows.sort(key=lambda x: x[1])
    names = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    ax2.barh(names, vals, color="#2f6f4f", alpha=0.85)
    ax2.axvline(0, color="#444444", lw=0.8)
    ax2.set_title(r"Per-asset $\Delta$CE (WM $-$ momentum)", fontsize=8.2)
    ax2.tick_params(labelsize=7)
    ax2.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
