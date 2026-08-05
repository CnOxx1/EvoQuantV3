#!/usr/bin/env python3
"""PIT band-readiness figure for the ICAIF paper.

Outputs:
  figures/fig_band_readiness.pdf
  figures/fig_band_readiness.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
# Prefer the evaluation PIT panel used in the paper empirics.
PANEL_CANDIDATES = [
    HERE.parent / "data" / "pit_multiband_panel.csv",
    HERE.parent / "tables" / "panel_simulation.csv",
]
OUT_PDF = HERE / "figures" / "fig_band_readiness.pdf"
OUT_PNG = HERE / "figures" / "fig_band_readiness.png"

BANDS = ["exchange", "macro", "alternative"]
STYLES = {
    "exchange": dict(color="#1f4e79", ls="-", lw=2.2, zorder=3),
    "macro": dict(color="#3f9160", ls="--", lw=1.7, zorder=2),
    "alternative": dict(color="#c87a2e", ls=":", lw=1.9, zorder=2),
}


def main() -> int:
    panel = next(p for p in PANEL_CANDIDATES if p.exists())
    df = pd.read_csv(panel, parse_dates=["date"])
    daily = df.groupby("date")

    fig, ax = plt.subplots(figsize=(3.45, 2.15))  # single-column friendly
    for b in BANDS:
        col = f"st_{b}"
        if col not in df.columns:
            continue
        share = daily[col].apply(lambda s: float((s == "ready").mean()))
        ax.plot(share.index, share.values, label=b, **STYLES[b])

    ax.set_ylabel("Share ready", fontsize=9)
    ax.set_ylim(-0.05, 1.08)
    ax.tick_params(axis="both", labelsize=8)
    ax.legend(
        ncol=3,
        fontsize=8,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        columnspacing=1.0,
        handlelength=2.2,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", lw=0.6, zorder=0)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PDF, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_PNG, bbox_inches="tight", facecolor="white", dpi=300)
    print(f"wrote {OUT_PDF} (from {panel.name})")
    print(f"wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
