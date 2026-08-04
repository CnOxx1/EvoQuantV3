#!/usr/bin/env python3
"""Render the anonymized layered runtime architecture figure for the ICAIF paper.

Output: pdf/icaif26/figures/fig_runtime_architecture.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "figures" / "fig_runtime_architecture.png"

LAYER_W = 11.6
BOX_H = 0.62
FS = 9.2
FS_SMALL = 8.0


def box(ax, x, y, w, h, text, fc, ec, fs=FS, weight="normal", text_color="black"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.035,rounding_size=0.07",
            linewidth=1.1,
            facecolor=fc,
            edgecolor=ec,
            zorder=3,
        )
    )
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color=text_color,
        weight=weight,
        zorder=4,
    )


def layer_title(ax, x, y, text, color):
    ax.text(
        x,
        y,
        text,
        fontsize=FS,
        weight="bold",
        color=color,
        zorder=5,
        bbox=dict(facecolor="white", edgecolor="none", pad=1.5),
    )


def arrow(ax, x0, y0, x1, y1, color="#555555", lw=1.3, style="-|>", ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle=style,
            mutation_scale=11,
            linewidth=lw,
            color=color,
            linestyle=ls,
            shrinkA=1,
            shrinkB=1,
            zorder=2,
        )
    )


def main() -> int:
    fig, ax = plt.subplots(figsize=(7.6, 5.9), dpi=200)
    ax.set_xlim(0, 12.4)
    ax.set_ylim(0, 10.4)
    ax.axis("off")

    c_data = ("#eaf2fb", "#4a7fb5")
    c_store = ("#f2eefa", "#7b5ea7")
    c_logic = ("#fdf1e3", "#c87a2e")
    c_serv = ("#e9f6ee", "#3f9160")
    c_cons = ("#fdeaea", "#b8514e")
    c_out = ("#f5f5f5", "#666666")

    # ---- Layer 1: data collectors -------------------------------------------------
    y1 = 9.15
    layer_title(ax, 0.28, y1 + BOX_H + 0.16, "Data layer — vintage-aware collectors", c_data[1])
    bands = [
        ("exchange", 0.3), ("macro\n(available_at)", 2.32), ("alternative", 4.34),
        ("news", 6.36), ("on-chain", 8.03), ("options", 9.7),
    ]
    for name, x in bands:
        w = 1.92 if x < 6 else 1.57
        dim = x >= 6
        box(ax, x, y1, w, BOX_H, name, "#f6f6f6" if dim else c_data[0],
            "#aaaaaa" if dim else c_data[1], fs=FS_SMALL,
            text_color="#888888" if dim else "black")
    ax.text(11.4, y1 + BOX_H / 2, "right-censored\n→ disclosed missing",
            fontsize=7.0, color="#888888", ha="left", va="center", style="italic")

    # ---- Layer 2: stores -----------------------------------------------------------
    y2 = 7.75
    layer_title(ax, 0.28, y2 + BOX_H + 0.16, "Store layer — embedded analytical stores", c_store[1])
    box(ax, 0.3, y2, 3.6, BOX_H, "raw multi-band history\n(obs. timestamps, vintages)", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 4.2, y2, 3.6, BOX_H, "merged market panels", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 8.1, y2, 3.6, BOX_H, "analytics: readiness,\nWMI/ACWMI, snapshots", c_store[0], c_store[1], fs=FS_SMALL)

    # ---- Layer 3: logic / compilation ---------------------------------------------
    y3 = 6.0
    layer_title(ax, 0.28, y3 + 0.95 + 0.16, "Logic layer — compilation  $\\Pi_t = B_t \\circ M_t \\circ A_t$", c_logic[1])
    box(ax, 0.3, y3, 3.6, 0.95,
        "BandPIT clock\ndecision_asof = $(t{-}1)$ 23:59\n(no same-day look-ahead)",
        c_logic[0], c_logic[1], fs=FS_SMALL)
    box(ax, 4.2, y3, 3.6, 0.95,
        "honesty / missingness gates\n$B,U,H$ → WMI $=BUH$\nACWMI (regime-cond.)",
        c_logic[0], c_logic[1], fs=FS_SMALL)
    box(ax, 8.1, y3, 3.6, 0.95,
        "availability shocks $O_t$\n(quasi-exogenous\nworld-thickness lever)",
        c_logic[0], c_logic[1], fs=FS_SMALL)

    # ---- Layer 4: service / bundle -------------------------------------------------
    y4 = 4.15
    layer_title(ax, 0.28, y4 + 1.06 + 0.16, "Service layer — world bundle contract (read API)", c_serv[1])
    box(ax, 0.3, y4, 11.4, 1.06,
        "completeness $n_{ready/limited/missing}$   ·   honesty $B,U,H$   ·   quality WMI / ACWMI\n"
        "should_ai_abstain · thin_world   ·   content: macro_tilt, alt_tilt, regime, cascade   ·   audit: evidence_ids (EAR)",
        c_serv[0], c_serv[1], fs=FS_SMALL)

    # ---- Layer 5: consumers (three arms) -------------------------------------------
    y5 = 2.1
    layer_title(ax, 0.28, y5 + 1.16 + 0.16,
        "Consumer layer — frozen prompts, temp. 0, OpenAI-compatible adapter (GPT / DeepSeek / GLM / Gemini)",
        c_cons[1])
    box(ax, 0.3, y5, 3.6, 1.16,
        "COMPILED\nfull bundle + hard\nshould_ai_abstain\n(typed contract)",
        c_cons[0], c_cons[1], fs=FS_SMALL, weight="bold")
    box(ax, 4.2, y5, 3.6, 1.16,
        "UNGATED (ablation)\nsame content + numeric\nWMI, no hard flag\n(soft judgment)",
        "#fdf6ec", "#c8952e", fs=FS_SMALL)
    box(ax, 8.1, y5, 3.6, 1.16,
        "RAW\nmom5 only\nno world model\n(common integration)",
        "#f2f2f2", "#888888", fs=FS_SMALL)

    # ---- Output row ------------------------------------------------------------------
    y6 = 0.35
    box(ax, 0.3, y6, 3.6, 0.86, "abstain 1.00\nthin-world refusal\nenforced", c_out[0], c_cons[1], fs=FS_SMALL, weight="bold")
    box(ax, 4.2, y6, 3.6, 0.86, "abstain 0.68 mean\n(0.43–0.86)\nvendor-dependent", c_out[0], "#c8952e", fs=FS_SMALL)
    box(ax, 8.1, y6, 3.6, 0.86, "abstain 0.04–0.75\ntrades into\nsparse support", c_out[0], "#888888", fs=FS_SMALL)

    # ---- Arrows ----------------------------------------------------------------------
    for x in (2.1, 6.0, 9.9):
        arrow(ax, x, y1 - 0.03, x, y2 + BOX_H + 0.06)
        arrow(ax, x, y2 - 0.03, x, y3 + 0.95 + 0.06)
        arrow(ax, x, y3 - 0.03, x, y4 + 1.06 + 0.06)
        arrow(ax, x, y5 - 0.03, x, y6 + 0.86 + 0.06)
    # bundle -> three arms
    for x in (2.1, 6.0, 9.9):
        arrow(ax, x, y4 - 0.03, x, y5 + 1.16 + 0.06)

    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
