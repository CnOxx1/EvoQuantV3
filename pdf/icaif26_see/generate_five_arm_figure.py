#!/usr/bin/env python3
"""Five-arm thin-abstention ladder + Wilson CIs for the ICAIF '26 See paper.

Arms: Blind / Raw / Ungated / HPO / Compiled (stress protocol, n=100).
Keeps filename fig_four_arm_ladder.* for stable \\includegraphics paths.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TAB = HERE / "tables"
ROOT_TAB = HERE.parent / "tables"
FIG = HERE / "figures"

MODELS = ["gpt-5.4-mini", "deepseek-v4-flash", "glm-5.2", "gemini-3.5-flash-lite"]
SHORT = {
    "gpt-5.4-mini": "gpt-5.4\nmini",
    "deepseek-v4-flash": "deepseek\nv4-flash",
    "glm-5.2": "glm-5.2",
    "gemini-3.5-flash-lite": "gemini-3.5\nflash-lite",
}
ARMS = ["Blind", "Raw", "Ungated", "HPO", "Compiled"]
COLORS = {
    "Blind": "#4a7fb5",
    "Raw": "#888888",
    "Ungated": "#c8952e",
    "HPO": "#9a3d3a",
    "Compiled": "#b8514e",
}


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0 or not math.isfinite(p):
        return (float("nan"), float("nan"))
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def main() -> int:
    five = pd.read_csv(TAB / "table_llm_five_arm_thin_abstain.csv")
    five = five[five["model"].isin(MODELS)].set_index("model")

    n = 100
    rows = []
    for m in MODELS:
        row: dict = {"model": m}
        for arm in ARMS:
            v = float(five.loc[m, arm])
            lo, hi = wilson(v, n)
            key = arm.lower()
            row[f"abs_{key}"] = v
            row[f"ci_{key}"] = f"[{lo:.2f},{hi:.2f}]"
            row[f"_err_{key}"] = (v - lo, hi - v)
        rows.append(row)

    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    for d in (TAB, ROOT_TAB):
        d.mkdir(parents=True, exist_ok=True)
        df.to_csv(d / "table_llm_five_arm_summary.csv", index=False)
        # Keep legacy summary name for any downstream readers.
        df.to_csv(d / "table_llm_four_arm_summary.csv", index=False)
    print(df.to_string(index=False))

    fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=200)
    x = np.arange(len(MODELS))
    w = 0.155
    offsets = (np.arange(len(ARMS)) - (len(ARMS) - 1) / 2.0) * w
    for i, arm in enumerate(ARMS):
        key = arm.lower()
        vals = [r[f"abs_{key}"] for r in rows]
        errs = np.clip(np.array([r[f"_err_{key}"] for r in rows]).T, 0, None)
        bars = ax.bar(
            x + offsets[i],
            vals,
            w,
            label=arm,
            color=COLORS[arm],
            alpha=0.90,
            edgecolor="white",
            linewidth=0.55,
        )
        ax.errorbar(
            x + offsets[i],
            vals,
            yerr=errs,
            fmt="none",
            ecolor="#333333",
            elinewidth=0.85,
            capsize=2.0,
        )
        for b, v in zip(bars, vals):
            ax.text(
                b.get_x() + b.get_width() / 2,
                min(v + 0.045, 1.08),
                f"{v:.2f}",
                ha="center",
                va="bottom",
                fontsize=6.2,
            )

    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[m] for m in MODELS], fontsize=8.2)
    ax.set_ylabel("Abstain rate (OOS asset-days)", fontsize=9)
    ax.set_ylim(0, 1.22)
    ax.axhline(1.0, color="#cccccc", lw=0.7, ls=":")
    ax.legend(
        ncol=5,
        fontsize=7.6,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.16),
        columnspacing=0.9,
        handlelength=1.4,
    )
    ax.set_title(
        r"Live five-arm thin abstention (Wilson 95% CIs, $n{=}100$; full-schema stress)",
        fontsize=8.8,
        pad=20,
    )
    ax.spines[["top", "right"]].set_visible(False)

    FIG.mkdir(parents=True, exist_ok=True)
    out_png = FIG / "fig_four_arm_ladder.png"
    out_pdf = FIG / "fig_four_arm_ladder.pdf"
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    fig.savefig(out_png, bbox_inches="tight", facecolor="white", dpi=300)
    print(f"wrote {out_pdf}")
    print(f"wrote {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
