#!/usr/bin/env python3
"""Render the anonymized layered runtime architecture figure (ICAIF '26 See).

Five-arm consumer layer: Compiled / HPO / Ungated / Raw / Blind.
Outputs vector + raster under figures/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
OUT_PDF = HERE / "figures" / "fig_runtime_architecture.pdf"
OUT_PNG = HERE / "figures" / "fig_runtime_architecture.png"

BOX_H = 0.56
FS = 8.8
FS_SMALL = 7.6


def box(ax, x, y, w, h, text, fc, ec, fs=FS, weight="normal"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.03,rounding_size=0.05",
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
        color="black",
        weight=weight,
        zorder=4,
        linespacing=1.12,
    )


def layer_band(ax, y, h, color):
    """Subtle full-width band behind a layer for visual stability."""
    ax.add_patch(
        Rectangle(
            (0.12, y - 0.12),
            11.95,
            h + 0.48,
            facecolor=color,
            edgecolor="none",
            alpha=0.22,
            zorder=0,
        )
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
        bbox=dict(facecolor="white", edgecolor="none", pad=1.0, alpha=0.92),
    )


def arrow(ax, x0, y0, x1, y1, color="#555555", lw=1.2, ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=lw,
            color=color,
            linestyle=ls,
            shrinkA=1,
            shrinkB=1,
            zorder=2,
        )
    )


def main() -> int:
    fig, ax = plt.subplots(figsize=(7.6, 5.35))
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0.08, 9.65)
    ax.axis("off")

    c_data = ("#eaf2fb", "#4a7fb5")
    c_store = ("#f2eefa", "#7b5ea7")
    c_logic = ("#fdf1e3", "#c87a2e")
    c_serv = ("#e9f6ee", "#3f9160")
    c_cons = ("#fdeaea", "#b8514e")

    # (1) Data
    y1 = 8.55
    layer_band(ax, y1, BOX_H, "#eaf2fb")
    layer_title(ax, 0.28, y1 + BOX_H + 0.12, "(1) Data layer — vintage-aware collectors", c_data[1])
    for name, x in [("exchange", 0.45), ("macro (available_at)", 4.2), ("alternative", 7.95)]:
        box(ax, x, y1, 3.35, BOX_H, name, c_data[0], c_data[1], fs=FS_SMALL)
    ax.text(
        11.45,
        y1 + BOX_H / 2,
        "eval. archive:\n3 bands",
        fontsize=6.8,
        color="#555555",
        ha="left",
        va="center",
        style="italic",
    )

    # (2) Store
    y2 = 7.15
    layer_band(ax, y2, BOX_H, "#f2eefa")
    layer_title(ax, 0.28, y2 + BOX_H + 0.12, "(2) Store layer — embedded analytical stores", c_store[1])
    box(ax, 0.3, y2, 3.55, BOX_H, "raw multi-band history\n(timestamps / vintages)", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 4.15, y2, 3.55, BOX_H, "merged market panels", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 8.0, y2, 3.55, BOX_H, "analytics: readiness,\nWMI / ACWMI, snapshots", c_store[0], c_store[1], fs=FS_SMALL)

    # (3) Logic
    y3 = 5.30
    layer_band(ax, y3, 0.95, "#fdf1e3")
    layer_title(
        ax,
        0.28,
        y3 + 0.95 + 0.12,
        r"(3) Logic layer — compilation  $\Pi_t = B_t \circ M_t \circ A_t$",
        c_logic[1],
    )
    box(
        ax,
        0.3,
        y3,
        3.55,
        0.95,
        "BandPIT clock\ndecision_asof = $(t{-}1)$ 23:59\n(no same-day look-ahead)",
        c_logic[0],
        c_logic[1],
        fs=FS_SMALL,
    )
    box(
        ax,
        4.15,
        y3,
        3.55,
        0.95,
        "honesty / missingness gates\n$B,U,H$ → WMI $=BUH$\nACWMI (regime-cond.)",
        c_logic[0],
        c_logic[1],
        fs=FS_SMALL,
    )
    box(
        ax,
        8.0,
        y3,
        3.55,
        0.95,
        "availability shocks $O_t$\n(quasi-exogenous\nthickness lever)",
        c_logic[0],
        c_logic[1],
        fs=FS_SMALL,
    )

    # (4) Service — dual-scope contract fields
    y4 = 3.48
    layer_band(ax, y4, 1.05, "#e9f6ee")
    layer_title(ax, 0.28, y4 + 1.05 + 0.12, "(4) Service layer — world bundle contract (read API)", c_serv[1])
    box(
        ax,
        0.3,
        y4,
        11.25,
        1.05,
        "completeness · honesty $B,U,H$ · WMI / ACWMI (dual scope) · should_ai_abstain · thin_world\n"
        "content: macro_tilt, alt_tilt, regime · audit: evidence_ids",
        c_serv[0],
        c_serv[1],
        fs=FS_SMALL,
    )

    # (5) Consumers — five arms
    y5 = 1.05
    arm_h = 1.45
    layer_band(ax, y5, arm_h, "#fdeaea")
    layer_title(
        ax,
        0.28,
        y5 + arm_h + 0.10,
        "(5) Consumer layer — frozen prompts, temp. 0 (GPT / DeepSeek / GLM / Gemini)",
        c_cons[1],
    )
    arm_w = 2.12
    gap = 0.18
    x0 = 0.30
    xs = [x0 + i * (arm_w + gap) for i in range(5)]
    arms = [
        ("COMPILED\nfull bundle +\nhard should_ai_abstain", c_cons[0], c_cons[1], True),
        ("HPO\nsame numeric fields;\nhard prompt, no boolean", "#fce8e8", "#9a3d3a", True),
        ("UNGATED\nsame content;\nno hard flag", "#fdf6ec", "#c8952e", True),
        ("RAW\nmom5 only;\nno world model", "#f2f2f2", "#666666", True),
        ("BLIND\ndirect ask;\nno data feed", "#eef2f7", "#4a7fb5", False),
    ]
    for x, (text, fc, ec, _fed) in zip(xs, arms):
        box(ax, x, y5, arm_w, arm_h, text, fc, ec, fs=7.0, weight="bold" if text.startswith("COMPILED") else "normal")

    ax.text(
        6.1,
        0.38,
        "Live abstention outcomes: Sec. Experiments (Table / five-arm ladder).",
        ha="center",
        va="center",
        fontsize=7.2,
        color="#555555",
        style="italic",
    )

    # Arrows between layers (three vertical trunks)
    for x in (2.05, 5.9, 9.75):
        arrow(ax, x, y1 - 0.02, x, y2 + BOX_H + 0.04)
        arrow(ax, x, y2 - 0.02, x, y3 + 0.95 + 0.04)
        arrow(ax, x, y3 - 0.02, x, y4 + 1.05 + 0.04)

    # Bundle → fed arms (Compiled, HPO, Ungated, Raw); Blind has no feed
    for i in range(4):
        cx = xs[i] + arm_w / 2
        arrow(ax, cx, y4 - 0.02, cx, y5 + arm_h + 0.04)
    ax.text(
        xs[4] + arm_w / 2,
        y4 - 0.20,
        "(no feed)",
        ha="center",
        va="top",
        fontsize=6.6,
        color="#4a7fb5",
        style="italic",
    )

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PDF, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_PNG, bbox_inches="tight", facecolor="white", dpi=300)
    print(f"wrote {OUT_PDF}")
    print(f"wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
