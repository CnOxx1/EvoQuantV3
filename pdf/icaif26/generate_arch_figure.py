#!/usr/bin/env python3
"""Render the anonymized layered runtime architecture figure for the ICAIF paper.

Outputs (vector + raster):
  figures/fig_runtime_architecture.pdf
  figures/fig_runtime_architecture.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
OUT_PDF = HERE / "figures" / "fig_runtime_architecture.pdf"
OUT_PNG = HERE / "figures" / "fig_runtime_architecture.png"

BOX_H = 0.58
FS = 9.0
FS_SMALL = 8.2


def box(ax, x, y, w, h, text, fc, ec, fs=FS, weight="normal"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.03,rounding_size=0.06",
            linewidth=1.15,
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
        linespacing=1.15,
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
        bbox=dict(facecolor="white", edgecolor="none", pad=1.2),
    )


def arrow(ax, x0, y0, x1, y1, color="#555555", lw=1.25, ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            (x0, y0),
            (x1, y1),
            arrowstyle="-|>",
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
    # Slightly shorter: arm definitions only (outcomes live in Sec. Experiments).
    fig, ax = plt.subplots(figsize=(7.4, 5.15))
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0.15, 9.55)
    ax.axis("off")

    c_data = ("#eaf2fb", "#4a7fb5")
    c_store = ("#f2eefa", "#7b5ea7")
    c_logic = ("#fdf1e3", "#c87a2e")
    c_serv = ("#e9f6ee", "#3f9160")
    c_cons = ("#fdeaea", "#b8514e")

    # (1) Data
    y1 = 8.45
    layer_title(ax, 0.28, y1 + BOX_H + 0.14, "(1) Data layer — vintage-aware collectors", c_data[1])
    for name, x in [("exchange", 0.45), ("macro (available_at)", 4.2), ("alternative", 7.95)]:
        box(ax, x, y1, 3.35, BOX_H, name, c_data[0], c_data[1], fs=FS_SMALL)
    ax.text(
        11.45,
        y1 + BOX_H / 2,
        "eval. archive:\n3 bands",
        fontsize=7.2,
        color="#555555",
        ha="left",
        va="center",
        style="italic",
    )

    # (2) Store
    y2 = 7.05
    layer_title(ax, 0.28, y2 + BOX_H + 0.14, "(2) Store layer — embedded analytical stores", c_store[1])
    box(ax, 0.3, y2, 3.55, BOX_H, "raw multi-band history\n(timestamps / vintages)", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 4.15, y2, 3.55, BOX_H, "merged market panels", c_store[0], c_store[1], fs=FS_SMALL)
    box(ax, 8.0, y2, 3.55, BOX_H, "analytics: readiness,\nWMI / ACWMI, snapshots", c_store[0], c_store[1], fs=FS_SMALL)

    # (3) Logic
    y3 = 5.25
    layer_title(
        ax,
        0.28,
        y3 + 0.95 + 0.14,
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

    # (4) Service
    y4 = 3.45
    layer_title(ax, 0.28, y4 + 1.0 + 0.14, "(4) Service layer — world bundle contract (read API)", c_serv[1])
    box(
        ax,
        0.3,
        y4,
        11.25,
        1.0,
        "completeness · honesty $B,U,H$ · WMI / ACWMI · should_ai_abstain · thin_world\n"
        "content: macro_tilt, alt_tilt, regime · audit: evidence_ids",
        c_serv[0],
        c_serv[1],
        fs=FS_SMALL,
    )

    # (5) Consumers — definitions only (no outcome numbers; see Sec. Experiments)
    y5 = 1.15
    layer_title(
        ax,
        0.28,
        y5 + 1.35 + 0.12,
        "(5) Consumer layer — frozen prompts, temp. 0 (GPT / DeepSeek / GLM / Gemini)",
        c_cons[1],
    )
    arm_w = 2.7
    xs = [0.3, 3.2, 6.1, 9.0]
    box(
        ax,
        xs[0],
        y5,
        arm_w,
        1.35,
        "COMPILED\nfull bundle +\nhard should_ai_abstain",
        c_cons[0],
        c_cons[1],
        fs=FS_SMALL,
        weight="bold",
    )
    box(
        ax,
        xs[1],
        y5,
        arm_w,
        1.35,
        "UNGATED\nsame content;\nno hard flag",
        "#fdf6ec",
        "#c8952e",
        fs=FS_SMALL,
    )
    box(
        ax,
        xs[2],
        y5,
        arm_w,
        1.35,
        "RAW\nmom5 only;\nno world model",
        "#f2f2f2",
        "#666666",
        fs=FS_SMALL,
    )
    box(
        ax,
        xs[3],
        y5,
        arm_w,
        1.35,
        "BLIND\ndirect ask;\nno data feed",
        "#eef2f7",
        "#4a7fb5",
        fs=FS_SMALL,
    )
    ax.text(
        6.1,
        0.45,
        "Live abstention outcomes: Sec.~Experiments (Table / four-arm figure).",
        ha="center",
        va="center",
        fontsize=7.4,
        color="#555555",
        style="italic",
    )

    # Arrows between layers
    for x in (2.05, 5.9, 9.75):
        arrow(ax, x, y1 - 0.02, x, y2 + BOX_H + 0.05)
        arrow(ax, x, y2 - 0.02, x, y3 + 0.95 + 0.05)
        arrow(ax, x, y3 - 0.02, x, y4 + 1.0 + 0.05)
    # bundle → first three arms (Blind: no feed)
    for x in [xs[i] + arm_w / 2 for i in (0, 1, 2)]:
        arrow(ax, x, y4 - 0.02, x, y5 + 1.35 + 0.05)
    # dashed note arrow absent for Blind — label
    ax.text(
        xs[3] + arm_w / 2,
        y4 - 0.22,
        "(no feed)",
        ha="center",
        va="top",
        fontsize=6.8,
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
