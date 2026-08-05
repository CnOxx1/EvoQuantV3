#!/usr/bin/env python3
"""Four-arm ladder figure + Wilson CIs for the ICAIF paper.

Arms: Compiled / Ungated / Raw (live tables) + Blind (table_llm_blind_live.csv).

Outputs:
  - figures/fig_four_arm_ladder.png
  - tables/table_llm_four_arm_summary.csv
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
    blind = pd.read_csv(TAB / "table_llm_blind_live.csv").set_index("model")

    n = 100
    rows = []
    for m in MODELS:
        vals = {
            "Blind": float(blind.loc[m, "abstain_rate"]),
            "Raw": float(deltas.loc[m, "raw_abstain_rate"]),
            "Ungated": float(ung.loc[m, "abstain_rate"]),
            "Compiled": float(deltas.loc[m, "compiled_abstain_rate"]),
        }
        row = {"model": m}
        for arm, v in vals.items():
            lo, hi = wilson(v, n)
            row[f"abs_{arm.lower()}"] = v
            row[f"ci_{arm.lower()}"] = f"[{lo:.2f},{hi:.2f}]"
            row[f"_err_{arm.lower()}"] = (v - lo, hi - v)
        row["dCE_compiled_minus_raw"] = float(deltas.loc[m, "dCE_compiled_minus_raw"])
        rows.append(row)

    df = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])
    for d in (TAB, ROOT_TAB):
        df.to_csv(d / "table_llm_four_arm_summary.csv", index=False)
    print(df.to_string(index=False))

    arms = ["Blind", "Raw", "Ungated", "Compiled"]
    colors = {"Blind": "#4a7fb5", "Raw": "#888888", "Ungated": "#c8952e", "Compiled": "#b8514e"}

    fig, ax = plt.subplots(figsize=(7.4, 3.1), dpi=200)
    x = np.arange(len(MODELS))
    w = 0.2
    for i, arm in enumerate(arms):
        key = f"abs_{arm.lower()}"
        vals = [r[key] for r in rows]
        errs = np.clip(np.array([r[f"_err_{arm.lower()}"] for r in rows]).T, 0, None)
        bars = ax.bar(x + (i - 1.5) * w, vals, w, label=arm, color=colors[arm],
                      alpha=0.88, edgecolor="white", linewidth=0.6)
        ax.errorbar(x + (i - 1.5) * w, vals, yerr=errs, fmt="none",
                    ecolor="#333333", elinewidth=0.9, capsize=2.2)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, min(v + 0.05, 1.06), f"{v:.2f}",
                    ha="center", va="bottom", fontsize=6.8)

    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[m] for m in MODELS], fontsize=8.4)
    ax.set_ylabel("Abstain rate (OOS asset-days)", fontsize=9)
    ax.set_ylim(0, 1.2)
    ax.axhline(1.0, color="#cccccc", lw=0.7, ls=":")
    ax.legend(ncol=4, fontsize=8.2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.15))
    ax.set_title(r"Live four-arm abstention rates (Wilson 95% CIs, $n{=}100$)",
                 fontsize=9.0, pad=18)
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
