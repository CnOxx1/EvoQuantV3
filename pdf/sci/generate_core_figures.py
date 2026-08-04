#!/usr/bin/env python3
"""Supplementary figures for the World-Model-First core manuscript."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
TAB = ROOT / "tables"
DATA = ROOT / "data"
FIG.mkdir(parents=True, exist_ok=True)

C_NAVY = "#1F4E79"
C_ORANGE = "#C55A11"
C_GREEN = "#548235"
C_BROWN = "#833C0C"
C_BLUE = "#5B9BD5"
C_GRAY = "#7F7F7F"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "figure.dpi": 140,
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def save(fig: plt.Figure, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / f"{stem}.png", bbox_inches="tight")
    fig.savefig(FIG / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("wrote", stem)


def fig9_lobo_decomposition() -> None:
    df = pd.read_csv(TAB / "table_lobo_decomposition.csv")
    bands = df["band"].tolist()
    x = np.arange(len(bands))
    w = 0.27
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    total = df["dCE_total"].fillna(0).to_numpy()
    content_col = "dCE_content" if "dCE_content" in df.columns else "dCE_content_only"
    gating_col = (
        "dCE_gating_residual"
        if "dCE_gating_residual" in df.columns
        else "dCE_gating_only"
    )
    content = df[content_col].fillna(0).to_numpy()
    gating = df[gating_col].fillna(0).to_numpy()
    ax.bar(x - w, total, w, label="Total ΔCE", color=C_NAVY)
    ax.bar(x, content, w, label="Content channel", color=C_ORANGE)
    ax.bar(x + w, gating, w, label="Gating residual", color=C_GREEN)
    ax.axhline(0, color=C_GRAY, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(bands)
    ax.set_ylabel("Δ OOS CE vs full world")
    ax.set_title("Fig. 9. LOBO: content vs gating channel decomposition")
    ax.legend(frameon=False)
    for i, row in df.iterrows():
        p = row.get("p_total")
        if pd.notna(p):
            y = float(total[i]) - 0.025
            ax.text(i - w, y, f"p={float(p):.3f}", ha="center", va="top", fontsize=7.5, color=C_NAVY)
    ax.set_ylim(min(total.min(), content.min(), gating.min()) - 0.08, 0.02)
    save(fig, "fig9_lobo_decomposition")


def fig10_longspan_by_year() -> None:
    df = pd.read_csv(TAB / "table_longspan_by_year.csv")
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    x = np.arange(len(df))
    w = 0.36
    ax.bar(x - w / 2, df["mech_ann_ret"], w, label="Mechanism (tilts=0 pre-archive)", color=C_NAVY)
    ax.bar(x + w / 2, df["long_ann_ret"], w, label="Always long", color=C_ORANGE)
    ax.axhline(0, color=C_GRAY, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(df["year"].astype(int))
    ax.set_ylabel("Calendar-year annualized return")
    ax.set_title("Fig. 10. Long-span external-validity anchor (BTC/ETH, 2017–2026)")
    ax.legend(frameon=False)
    save(fig, "fig10_longspan_by_year")


def fig11_band_readiness() -> None:
    panel = pd.read_csv(DATA / "pit_multiband_panel.csv", parse_dates=["date"])
    bands = [
        "exchange",
        "macro",
        "alternative",
        "news",
        "onchain",
        "options",
        "tokenomics",
        "event_calendar",
    ]
    series = {}
    for band in bands:
        col = f"st_{band}"
        if col not in panel.columns:
            continue
        ready = panel[col].astype(str).isin(["ready", "fresh", "ok", "limited"]).astype(float)
        series[band] = panel.assign(_ready=ready).groupby("date")["_ready"].mean()
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    for band, s in series.items():
        durable = band in {"exchange", "macro", "alternative"}
        ax.plot(s.index, s.values, label=band, lw=1.8 if durable else 1.0, alpha=1.0 if durable else 0.55)
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("Share of assets with band ready")
    ax.set_title("Fig. 11. Point-in-time band readiness over the archive")
    ax.legend(ncol=4, fontsize=8, frameon=False)
    save(fig, "fig11_band_readiness")


def fig12_wmi_acwmi_paths() -> None:
    sim = TAB / "panel_simulation.csv"
    panel = pd.read_csv(sim if sim.exists() else DATA / "pit_multiband_panel.csv", parse_dates=["date"])
    ac_col = "ACWMI" if "ACWMI" in panel.columns else "ACWMI_world"
    if "WMI" not in panel.columns or ac_col not in panel.columns:
        print("skip fig12: WMI/ACWMI not in panel")
        return
    daily = panel.groupby("date")[["WMI", ac_col]].mean()
    cut = pd.Timestamp("2026-01-16")
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    ax.plot(daily.index, daily["WMI"], label="WMI", color=C_BLUE, lw=1.3)
    ax.plot(daily.index, daily[ac_col], label="ACWMI", color=C_ORANGE, lw=1.3)
    ax.axvline(cut, color=C_GRAY, ls="--", lw=1)
    ymax = float(daily.max().max())
    ax.text(cut, ymax * 0.95, " IS | OOS ", fontsize=8, color=C_GRAY)
    ax.set_ylabel("Index level")
    ax.set_title("Fig. 12. World-model quality indices on the real PIT panel")
    ax.legend(frameon=False)
    save(fig, "fig12_wmi_acwmi_paths")


def fig13_cost_frontier() -> None:
    df = pd.read_csv(TAB / "table_cost_sensitivity.csv")
    if "funding" in df.columns:
        d = df[df["funding"].astype(str).str.startswith("no")].copy()
    else:
        d = df.copy()
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    for policy, color in [
        ("Thick ungated", C_NAVY),
        ("ACWMI (IS-frozen)", C_ORANGE),
        ("Momentum always", C_GREEN),
        ("Always long", C_GRAY),
    ]:
        g = d[d["policy"] == policy].sort_values("cost_bps")
        if g.empty:
            continue
        ax.plot(g["cost_bps"], g["CE"], "o-", label=policy, color=color, lw=1.4)
    ax.axhline(0, color=C_GRAY, lw=1)
    ax.set_xlabel("One-way transaction cost (bps)")
    ax.set_ylabel("OOS certainty equivalent (ann.)")
    ax.set_title("Fig. 13. Transaction-cost sensitivity of compiled-world policies")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "fig13_cost_frontier")


def fig14_architecture_schematic() -> None:
    fig, ax = plt.subplots(figsize=(8.4, 3.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")
    boxes = [
        (0.3, 1.4, 1.8, 1.4, "Raw bands\nX_j,t", C_BLUE),
        (2.5, 1.4, 2.0, 1.4, "Governance\nQ_t, R_t, A_t", C_NAVY),
        (4.9, 1.4, 2.0, 1.4, "Compiled world\nW_t / WMI", C_ORANGE),
        (7.3, 1.4, 2.2, 1.4, "AI judgment\n+ abstention", C_GREEN),
    ]
    for x, y, w, h, text, color in boxes:
        rect = plt.Rectangle((x, y), w, h, fill=False, ec=color, lw=2)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9, color=color)
    for x0, x1 in [(2.1, 2.5), (4.5, 4.9), (6.9, 7.3)]:
        ax.annotate(
            "",
            xy=(x1, 2.1),
            xytext=(x0, 2.1),
            arrowprops=dict(arrowstyle="->", color=C_GRAY, lw=1.5),
        )
    ax.text(5, 3.55, "World-Model-First: compile before predict", ha="center", fontsize=11, color=C_BROWN)
    ax.text(
        5,
        0.55,
        "latest_* · readiness · eight evidence bands · main/diagnostic separation",
        ha="center",
        fontsize=8,
        color=C_GRAY,
    )
    save(fig, "fig14_wm_pipeline")


def fig15_thin_thick_compare() -> None:
    df = pd.read_csv(TAB / "table_thin_thick.csv")
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8))
    labels = [
        w.replace(" (real PIT)", "")
        .replace("Thick gated AC", "Thick+AC")
        .replace("Thick real PIT (ex+macro+alt…)", "Thick PIT")
        .replace("Thin (exchange only, real PIT)", "Thin (ex only)")
        for w in df["world"]
    ]
    x = np.arange(len(df))
    axes[0].bar(x, df["mean_B"], color=C_BLUE, label="B", alpha=0.85)
    axes[0].plot(x, df["mean_H"], "o-", color=C_ORANGE, label="H")
    if "mean_ACWMI" in df.columns:
        axes[0].plot(x, df["mean_ACWMI"], "s-", color=C_GREEN, label="ACWMI")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    axes[0].set_title("World quality")
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].bar(x - 0.15, df["Sharpe"], 0.3, label="Sharpe", color=C_NAVY)
    axes[1].bar(x + 0.15, df["CE"], 0.3, label="CE", color=C_ORANGE)
    axes[1].axhline(0, color=C_GRAY, lw=1)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=15, ha="right", fontsize=8)
    axes[1].set_title("OOS economic value")
    axes[1].legend(frameon=False, fontsize=8)
    fig.suptitle("Fig. 15. Thin vs thick worlds under real multi-band PIT", y=1.02)
    save(fig, "fig15_thin_thick")


def main() -> None:
    _style()
    fig14_architecture_schematic()
    fig9_lobo_decomposition()
    fig10_longspan_by_year()
    fig11_band_readiness()
    fig12_wmi_acwmi_paths()
    fig13_cost_frontier()
    fig15_thin_thick_compare()
    print("Core supplementary figures done →", FIG)


if __name__ == "__main__":
    main()
