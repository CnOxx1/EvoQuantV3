#!/usr/bin/env python3
"""Clean PIT band-readiness figure for the ICAIF paper (replaces legacy fig11).

Output: figures/fig_band_readiness.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "tables" / "panel_simulation.csv"
OUT = HERE / "figures" / "fig_band_readiness.png"

BANDS = ["exchange", "macro", "alternative"]
COLORS = {
    "exchange": "#4a7fb5",
    "macro": "#3f9160",
    "alternative": "#c87a2e",
}


def main() -> int:
    df = pd.read_csv(PANEL, parse_dates=["date"])
    daily = df.groupby("date")

    fig, ax = plt.subplots(figsize=(7.0, 2.5), dpi=200)
    for b in BANDS:
        col = f"st_{b}"
        if col not in df.columns:
            continue
        share = daily[col].apply(lambda s: float((s == "ready").mean()))
        ax.plot(share.index, share.values, label=b, color=COLORS[b], ls="-", lw=1.6)

    ax.set_ylabel("Share ready", fontsize=8.5)
    ax.set_ylim(-0.04, 1.09)
    ax.tick_params(labelsize=7.5)
    ax.legend(
        ncol=3,
        fontsize=7.5,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        columnspacing=1.2,
        handlelength=1.6,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("PIT readiness for the three-band evaluation archive", fontsize=8.2)

    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
