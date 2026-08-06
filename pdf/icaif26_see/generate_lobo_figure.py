#!/usr/bin/env python3
"""LOBO content-vs-gating figure for ICAIF '26 See (no baked-in figure number)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TAB = HERE / "tables"
ROOT_TAB = HERE.parent / "tables"
FIG = HERE / "figures"

C_NAVY = "#1f4e79"
C_ORANGE = "#c87a2e"
C_GREEN = "#3f9160"
C_GRAY = "#888888"


def main() -> int:
    path = next(
        p
        for p in (TAB / "table_lobo_decomposition.csv", ROOT_TAB / "table_lobo_decomposition.csv")
        if p.exists()
    )
    df = pd.read_csv(path)
    bands = df["band"].tolist()
    x = np.arange(len(bands))
    w = 0.27
    fig, ax = plt.subplots(figsize=(3.45, 2.35))  # single-column friendly
    content_col = "dCE_content" if "dCE_content" in df.columns else "dCE_content_only"
    gating_col = (
        "dCE_gating_residual" if "dCE_gating_residual" in df.columns else "dCE_gating_only"
    )
    total = df["dCE_total"].fillna(0).to_numpy()
    content = df[content_col].fillna(0).to_numpy()
    gating = df[gating_col].fillna(0).to_numpy()
    ax.bar(x - w, total, w, label="Total ΔCE", color=C_NAVY)
    ax.bar(x, content, w, label="Content channel", color=C_ORANGE)
    ax.bar(x + w, gating, w, label="Gating residual", color=C_GREEN)
    ax.axhline(0, color=C_GRAY, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(bands, fontsize=7.5, rotation=15, ha="right")
    ax.set_ylabel(r"$\Delta$ OOS CE vs full world", fontsize=8.5)
    # No figure number in the axes title — LaTeX caption owns numbering.
    ax.set_title("LOBO: content vs gating channel", fontsize=8.5)
    ax.legend(frameon=False, fontsize=7.0, loc="lower left")
    ymin = float(min(total.min(), content.min(), gating.min()) - 0.08)
    ax.set_ylim(ymin, 0.04)
    for i, row in df.iterrows():
        p = row.get("p_total")
        if pd.notna(p):
            y = float(total[i]) - 0.02 if total[i] < 0 else 0.01
            ax.text(
                i - w,
                y,
                f"p={float(p):.3f}",
                ha="center",
                va="top" if total[i] < 0 else "bottom",
                fontsize=6.5,
                color=C_NAVY,
            )
    ax.tick_params(axis="y", labelsize=7.5)
    ax.spines[["top", "right"]].set_visible(False)

    FIG.mkdir(parents=True, exist_ok=True)
    out_pdf = FIG / "fig9_lobo_decomposition.pdf"
    out_png = FIG / "fig9_lobo_decomposition.png"
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    fig.savefig(out_png, bbox_inches="tight", facecolor="white", dpi=300)
    print(f"wrote {out_pdf} (from {path})")
    print(f"wrote {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
