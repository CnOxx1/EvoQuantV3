#!/usr/bin/env python3
"""Three-arm ladder figure + Wilson CIs for the ICAIF paper.

Reads live Compiled/Raw results (table_llm_consumer_deltas_live.csv) and the
100-day Ungated rerun (table_llm_understanding_ungated100.csv), computes
Wilson 95% intervals for abstain rates, and writes:

  - figures/fig_three_arm_ladder.png
  - tables/table_llm_three_arm_summary.csv  (with CI columns)
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
SHORT = {"gpt-5.4-mini": "gpt-5.4\nmini", "deepseek-v4-flash": "deepseek\nv4-flash",
         "glm-5.2": "glm-5.2", "gemini-3.5-flash-lite": "gemini-3.5\nflash-lite"}


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def main() -> int:
    deltas = pd.read_csv(TAB / "table_llm_consumer_deltas_live.csv").set_index("model")
    ung = pd.read_csv(TAB / "table_llm_understanding_ungated100.csv")
    ung = ung[ung.treatment == "ungated"].set_index("model")

    n_cr, n_u = 100, 100
    rows = []
    for m in MODELS:
        c = float(deltas.loc[m, "compiled_abstain_rate"])
        r = float(deltas.loc[m, "raw_abstain_rate"])
        u = float(ung.loc[m, "abstain_rate"])
        c_lo, c_hi = wilson(c, n_cr)
        u_lo, u_hi = wilson(u, n_u)
        r_lo, r_hi = wilson(r, n_cr)
        rows.append({
            "model": m,
            "abs_compiled": c, "ci_compiled": f"[{c_lo:.2f},{c_hi:.2f}]",
            "abs_ungated": u, "ci_ungated": f"[{u_lo:.2f},{u_hi:.2f}]",
            "abs_raw": r, "ci_raw": f"[{r_lo:.2f},{r_hi:.2f}]",
            "thin_abs_compiled": float(deltas.loc[m, "compiled_thin_world_abstain_rate"]),
            "thin_abs_ungated": float(ung.loc[m, "thin_world_abstain_rate"]),
            "dCE_compiled_minus_raw": float(deltas.loc[m, "dCE_compiled_minus_raw"]),
            "_err": (c - c_lo, c_hi - c, u - u_lo, u_hi - u, r - r_lo, r_hi - r),
        })

    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_err"} for r in rows])
    for d in (TAB, ROOT_TAB):
        df.to_csv(d / "table_llm_three_arm_summary.csv", index=False)
    print(df.to_string(index=False))

    # ---- figure -----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.4, 3.1), dpi=200)
    x = np.arange(len(MODELS))
    w = 0.26
    colors = {"Compiled": "#b8514e", "Ungated": "#c8952e", "Raw": "#888888"}

    for i, (arm, key) in enumerate(
        [("Compiled", "abs_compiled"), ("Ungated", "abs_ungated"), ("Raw", "abs_raw")]
    ):
        vals = [r[key] for r in rows]
        errs = np.clip(
            np.array([[r["_err"][2 * i], r["_err"][2 * i + 1]] for r in rows]).T, 0, None
        )
        bars = ax.bar(x + (i - 1) * w, vals, w, label=arm, color=colors[arm],
                      alpha=0.88, edgecolor="white", linewidth=0.6)
        ax.errorbar(x + (i - 1) * w, vals, yerr=errs, fmt="none",
                    ecolor="#333333", elinewidth=1.0, capsize=2.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, min(v + 0.05, 1.06), f"{v:.2f}",
                    ha="center", va="bottom", fontsize=7.4)

    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[m] for m in MODELS], fontsize=8.4)
    ax.set_ylabel("Abstain rate (OOS asset-days)", fontsize=9)
    ax.set_ylim(0, 1.18)
    ax.axhline(1.0, color="#cccccc", lw=0.7, ls=":")
    ax.legend(ncol=3, fontsize=8.4, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.14))
    ax.set_title("Live three-arm ladder: typed contract > disclosure-only > raw feed"
                 "  (Wilson 95% CIs, $n{=}100$ per arm)",
                 fontsize=9, pad=22)
    ax.spines[["top", "right"]].set_visible(False)

    out = FIG / "fig_three_arm_ladder.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
