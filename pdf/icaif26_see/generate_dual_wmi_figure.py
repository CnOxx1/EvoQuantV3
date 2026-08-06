#!/usr/bin/env python3
"""Dual-scope WMI paths (full-schema stress vs scoped production)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
TAB = HERE / "tables"
FIG = HERE / "figures"
OUT_PDF = FIG / "fig_wmi_dual_scope.pdf"
OUT_PNG = FIG / "fig_wmi_dual_scope.png"
QSTAR = 0.2
OOS_START = "2026-01-16"  # chronological IS/OOS cut in the paper


def main() -> int:
    df = pd.read_csv(TAB / "panel_scoped_wmi.csv", parse_dates=["date"])
    daily = (
        df.groupby("date", as_index=True)
        .agg(WMI=("WMI", "mean"), WMI_scoped=("WMI_scoped", "mean"), n_ready=("n_ready_scoped", "mean"))
        .sort_index()
    )

    fig, ax = plt.subplots(figsize=(3.45, 2.15))
    # Shade archive-complete days (mean n_ready ≈ 3)
    complete = daily["n_ready"] >= 2.99
    if complete.any():
        # contiguous shade via fill_between where complete
        ax.fill_between(
            daily.index,
            0,
            1,
            where=complete.values,
            color="#f7e6d4",
            alpha=0.55,
            zorder=0,
        )

    ax.plot(
        daily.index,
        daily["WMI"].values,
        color="#4a7fb5",
        lw=1.7,
        label="Full-schema stress WMI",
        zorder=3,
    )
    ax.plot(
        daily.index,
        daily["WMI_scoped"].values,
        color="#c87a2e",
        lw=1.7,
        label="Scoped production WMI",
        zorder=3,
    )
    ax.axhline(QSTAR, color="#222222", lw=1.0, ls="--", label=rf"Threshold $q^\star={QSTAR}$", zorder=2)
    oos = pd.Timestamp(OOS_START)
    if daily.index.min() <= oos <= daily.index.max():
        ax.axvline(oos, color="#999999", lw=0.9, ls=":", zorder=1)
        ax.text(oos, 1.02, "OOS", ha="center", va="bottom", fontsize=7.5, color="#666666")

    ax.set_ylabel("WMI (cross-asset mean)", fontsize=8.5)
    ax.set_ylim(-0.02, 1.08)
    ax.tick_params(labelsize=7.5)
    ax.legend(frameon=False, fontsize=7.0, loc="center right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#ececec", lw=0.6, zorder=0)

    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PDF, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT_PNG, bbox_inches="tight", facecolor="white", dpi=300)
    print(f"wrote {OUT_PDF}")
    print(f"wrote {OUT_PNG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
