#!/usr/bin/env python3
"""JF/RFS empirics on the real multi-band PIT archive.

Uses pdf/data/pit_multiband_panel.csv built from SQLite history tables
(exchange/macro/alternative have durable history; news/onchain/options mostly
right-censored to collection day). Mechanism engines run on real returns with
pre-t history only. Thresholds frozen on IS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib.util

_jf_path = Path(__file__).resolve().parent / "run_jf_experiments.py"
_spec = importlib.util.spec_from_file_location("run_jf_experiments", _jf_path)
_jf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_jf)
REGIME_GAMMA = _jf.REGIME_GAMMA
acwmi = _jf.acwmi
calibrate_thresholds = _jf.calibrate_thresholds
bootstrap_delta_pvalues = _jf.bootstrap_delta_pvalues
directional_signal = _jf.directional_signal
evaluate_policies = _jf.evaluate_policies
fig_cumreturns = _jf.fig_cumreturns
fig_is_oos_stability = _jf.fig_is_oos_stability
fig_lobo = _jf.fig_lobo
fig_oos_bars = _jf.fig_oos_bars
fig_pareto = _jf.fig_pareto
fig_paths = _jf.fig_paths
fig_thin_thick = _jf.fig_thin_thick
mechanism_component_definitions = _jf.mechanism_component_definitions
portfolio_stats = _jf.portfolio_stats
run_engines = _jf.run_engines
split_is_oos = _jf.split_is_oos
strategy_positions = _jf.strategy_positions
from logic_layer.asset_readiness.service import AssetReadinessService
from logic_layer.ai_market_context.service import AIMarketContextService

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"
FIG = Path(__file__).resolve().parents[1] / "figures"
OUT = Path(__file__).resolve().parent
TAB.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

BANDS = list(AssetReadinessService.BAND_WEIGHTS.keys())
HIST_BANDS = ["exchange", "macro", "alternative"]  # durable history in archive


def continuous_honesty(excl_rate: float, cont_rate: float) -> float:
    return float(np.exp(-2.0 * cont_rate) * max(0.0, 1.0 - 0.5 * (1.0 - excl_rate)))


def readiness_ratio(status: str) -> float:
    return float(AssetReadinessService._status_ratio(status))


def recompute_world(df: pd.DataFrame, drop_band: str | None = None, thin: bool = False) -> pd.DataFrame:
    out = df.copy()
    rows = []
    for _, r in out.iterrows():
        statuses = {b: r.get(f"st_{b}", "missing") for b in BANDS}
        if thin:
            statuses = {b: ("ready" if b == "exchange" and statuses.get("exchange") == "ready" else "missing") for b in BANDS}
            if statuses.get("exchange") != "ready":
                statuses["exchange"] = statuses.get("exchange", "missing")
        if drop_band:
            statuses[drop_band] = "missing"
        B_asset = sum(AssetReadinessService.BAND_WEIGHTS[b] * readiness_ratio(statuses[b]) for b in BANDS)
        req = [readiness_ratio(statuses[b]) for b in AssetReadinessService.REQUIRED_BANDS]
        B_band = float(np.mean(req)) if req else B_asset
        B_domain = float(np.mean([readiness_ratio(statuses[b]) for b in BANDS]))
        B_hier = 0.25 * B_domain + 0.35 * B_band + 0.40 * B_asset
        ready_n = sum(1 for s in statuses.values() if s == "ready")
        limited_n = sum(1 for s in statuses.values() if s == "limited")
        total = max(len(statuses), 1)
        U = (ready_n + 0.7 * limited_n) / total
        excl = ready_n / total
        cont = limited_n / total * 0.5
        H = continuous_honesty(excl, cont)
        flag = "ok" if B_hier >= 0.55 and cont < 0.15 else ("thin" if B_hier >= 0.35 else "blocked")
        wmi = AIMarketContextService._compute_world_model_index(
            coverage_score=float(B_hier),
            pipeline_latency_context={"summary": {"total_domains": total, "fresh": ready_n, "acceptable": limited_n}},
            data_quality_flag=flag,
            data_quality_flags=[],
        )["wmi"]
        rows.append((B_hier, U, H, wmi, ready_n, limited_n))
    out["B_hier"], out["U"], out["H_cont"], out["WMI"], out["n_ready"], out["n_limited"] = zip(*rows)
    return out


def attach_engines(pit: pd.DataFrame) -> pd.DataFrame:
    pit = pit.sort_values(["asset", "date"]).copy()
    rows = []
    for asset, g in pit.groupby("asset"):
        hist = []
        for _, r in g.iterrows():
            eng = run_engines(asset, np.array(hist, dtype=float))
            sig = directional_signal(eng)
            gamma = REGIME_GAMMA.get(eng["detected_regime"], REGIME_GAMMA["range"])
            ac = acwmi(r["B_hier"], r["U"], r["H_cont"], eng["S"], eng["C"], gamma)
            rec = r.to_dict()
            rec.update(
                {
                    "S": eng["S"],
                    "C": eng["C"],
                    "cascade_p": eng["cascade_p"],
                    "systemic": eng["systemic"],
                    "detected_regime": eng["detected_regime"],
                    "signal": sig,
                    "mom5": eng["mom5"],
                    "ACWMI": ac,
                }
            )
            rows.append(rec)
            hist.append(float(r["ret"]))
    df = pd.DataFrame(rows)
    # Relative scarcity shock: top quintile of thinness (1-B_hier) within sample
    thr = df["B_hier"].quantile(0.20)
    df["scarce"] = (df["B_hier"] <= thr).astype(int)
    # Prefer scarce days as identifying states when hard outages are rare in continuous backfills
    df["outage_id"] = ((df["outage"] == 1) | (df["scarce"] == 1)).astype(int)
    return df


def timeslice_grid() -> pd.DataFrame:
    from logic_layer.time_slice.service import TimeSliceService

    svc = TimeSliceService()
    dates = pd.date_range("2025-07-01", "2026-08-01", freq="MS")
    rows = []
    for d in dates:
        ts = d.strftime("%Y-%m-%dT00:00:00")
        try:
            sl = svc.get_slice_at(ts, symbols=["BTC/USDT", "ETH/USDT"])
            cov = sl.coverage_summary or {}
            statuses = {k: v.status for k, v in sl.domains.items()}
            rows.append({"timestamp": ts, **cov, **{f"dom_{k}": v for k, v in statuses.items()}})
        except Exception as e:
            rows.append({"timestamp": ts, "error": str(e)})
    svc.close()
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "table_timeslice_grid.csv", index=False)
    return out


def event_study_scarce(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.groupby("date")
        .agg(ret=("ret", "mean"), WMI=("WMI", "mean"), ACWMI=("ACWMI", "mean"), scarce=("scarce", "max"), B=("B_hier", "mean"))
        .sort_index()
    )
    events = daily.index[daily["scarce"] == 1]
    # de-cluster: keep events with gap>=3 days
    kept = []
    last = None
    for e in events:
        if last is None or (pd.Timestamp(e) - pd.Timestamp(last)).days >= 3:
            kept.append(e)
            last = e
    rows = []
    for k in range(-3, 4):
        vals = []
        for e in kept:
            idx = daily.index.get_indexer([e])[0]
            j = idx + k
            if 0 <= j < len(daily):
                vals.append(daily.iloc[j][["ret", "WMI", "ACWMI", "B"]].to_dict())
        if not vals:
            continue
        m = pd.DataFrame(vals).mean()
        rows.append(
            {
                "k": k,
                "ret": round(float(m["ret"]), 5),
                "WMI": round(float(m["WMI"]), 4),
                "ACWMI": round(float(m["ACWMI"]), 4),
                "B_hier": round(float(m["B"]), 4),
                "N": len(vals),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "table4_outage_event_study.csv", index=False)
    return out


def main() -> None:
    pit_path = DATA / "pit_multiband_panel.csv"
    if not pit_path.exists():
        raise SystemExit("Missing PIT panel; run build_pit_archive.py first")
    pit = pd.read_csv(pit_path, parse_dates=["date"])
    print("PIT", pit["date"].min().date(), "→", pit["date"].max().date(), "N", len(pit))

    print("time_slice monthly grid...")
    ts_grid = timeslice_grid()
    print(ts_grid[["timestamp", "domains_ready", "overall_freshness"]].head() if "domains_ready" in ts_grid else ts_grid.head())

    print("Attach engines (PIT returns)...")
    df = attach_engines(pit)
    df.to_csv(TAB / "panel_simulation.csv", index=False)

    is_df, oos, cut = split_is_oos(df, is_frac=0.5)
    print("IS/OOS cut", cut, "IS days", is_df["date"].nunique(), "OOS", oos["date"].nunique())
    params = calibrate_thresholds(is_df)
    (OUT / "frozen_thresholds.json").write_text(json.dumps(params, indent=2), encoding="utf-8")
    print("frozen", params)

    econ, curves = evaluate_policies(oos, params)
    econ.to_csv(TAB / "table_econ_oos.csv", index=False)
    print(econ)

    # Mechanism audit table (open the black box)
    mech_def = pd.DataFrame(mechanism_component_definitions())
    mech_def.to_csv(TAB / "table_mechanism_definition.csv", index=False)
    mech_sum = (
        df.groupby("detected_regime")
        .agg(
            n=("signal", "size"),
            mean_cascade_p=("cascade_p", "mean"),
            mean_S=("S", "mean"),
            mean_C=("C", "mean"),
            mean_signal=("signal", "mean"),
            share_long=("signal", lambda s: float((s > 0).mean())),
            share_short=("signal", lambda s: float((s < 0).mean())),
        )
        .reset_index()
    )
    mech_sum.to_csv(TAB / "table_mechanism_by_regime.csv", index=False)
    print(mech_def)
    print(mech_sum)

    # Block-bootstrap p-values on OOS daily curves (n_boot=999, block=5)
    print("Bootstrap OOS deltas...")
    boot_rows = []
    comparisons = [
        ("Thick ungated − Always long", "Thick ungated", "Always long"),
        ("ACWMI − Always long", "ACWMI (IS-frozen)", "Always long"),
        ("ACWMI − Momentum always", "ACWMI (IS-frozen)", "Momentum always"),
        ("Thick ungated − ACWMI", "Thick ungated", "ACWMI (IS-frozen)"),
        ("ACWMI − WMI threshold (0.2)", "ACWMI (IS-frozen)", "WMI threshold (0.2)"),
    ]
    for name, a, b in comparisons:
        if a not in curves or b not in curves:
            continue
        res = bootstrap_delta_pvalues(curves[a], curves[b], n_boot=999, block=5)
        boot_rows.append({"contrast": name, **res})
    boot_df = pd.DataFrame(boot_rows)
    boot_df.to_csv(TAB / "table_bootstrap_oos.csv", index=False)
    print(boot_df)

    # LOBO on historically durable bands
    _, oos0, _ = split_is_oos(df)
    base_pos = strategy_positions(oos0, "ac", params)
    base = portfolio_stats(oos0, base_pos)
    base_daily = base["daily"]
    lobo_rows = [{
        "band_dropped": "(none)",
        "Sharpe": round(base["Sharpe"], 3),
        "CE": round(base["CE"], 4),
        "abstain_rate": round(base["abstain_rate"], 3),
        "dCE": 0.0,
        "p_dCE": None,
    }]
    for band in HIST_BANDS:
        d2 = recompute_world(df, drop_band=band)
        # rebuild ACWMI with same S/C
        d2["ACWMI"] = [
            acwmi(b, u, h, s, c, REGIME_GAMMA.get(rg, REGIME_GAMMA["range"]))
            for b, u, h, s, c, rg in zip(d2["B_hier"], d2["U"], d2["H_cont"], d2["S"], d2["C"], d2["detected_regime"])
        ]
        _, oos_b, _ = split_is_oos(d2)
        st = portfolio_stats(oos_b, strategy_positions(oos_b, "ac", params))
        # p-value for CE loss vs baseline AC (A = dropped, B = baseline → dCE negative if harmful)
        bp = bootstrap_delta_pvalues(st["daily"], base_daily, n_boot=999, block=5)
        lobo_rows.append(
            {
                "band_dropped": band,
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
                "dCE": round(st["CE"] - base["CE"], 4),
                "p_dCE": bp.get("p_CE"),
            }
        )
    lobo = pd.DataFrame(lobo_rows)
    lobo.to_csv(TAB / "table_lobo.csv", index=False)
    print(lobo)

    # Thin vs thick using real statuses
    thin = recompute_world(df, thin=True)
    thin["ACWMI"] = [
        acwmi(b, u, h, s, c, REGIME_GAMMA.get(rg, REGIME_GAMMA["range"]))
        for b, u, h, s, c, rg in zip(thin["B_hier"], thin["U"], thin["H_cont"], thin["S"], thin["C"], thin["detected_regime"])
    ]
    _, oos_thin, _ = split_is_oos(thin)
    _, oos_thick, _ = split_is_oos(df)
    tt_rows = []
    daily_by_world = {}
    for name, dsub, policy in [
        ("Thin (exchange only, real PIT)", oos_thin, "ac"),
        ("Thick real PIT (ex+macro+alt…)", oos_thick, "thick_ungated"),
        ("Thick gated AC (real PIT)", oos_thick, "ac"),
    ]:
        st = portfolio_stats(dsub, strategy_positions(dsub, policy, params))
        daily_by_world[name] = st["daily"]
        tt_rows.append(
            {
                "world": name,
                "mean_B": round(float(dsub["B_hier"].mean()), 3),
                "mean_H": round(float(dsub["H_cont"].mean()), 3),
                "mean_ACWMI": round(float(dsub["ACWMI"].mean()), 3),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
            }
        )
    # bootstrap: thick ungated vs thin AC
    thick_vs_thin = bootstrap_delta_pvalues(
        daily_by_world["Thick real PIT (ex+macro+alt…)"],
        daily_by_world["Thin (exchange only, real PIT)"],
        n_boot=999,
        block=5,
    )
    tt = pd.DataFrame(tt_rows)
    tt.to_csv(TAB / "table_thin_thick.csv", index=False)
    (TAB / "table_thin_thick_bootstrap.json").write_text(
        json.dumps({"thick_minus_thin": thick_vs_thin}, indent=2), encoding="utf-8"
    )
    print(tt)
    print("thick−thin bootstrap", thick_vs_thin)

    ev = event_study_scarce(df)
    print(ev)

    # archive inventory for paper
    summary = json.loads((DATA / "pit_archive_summary.json").read_text())
    inv = {
        "design": "real multi-band PIT from SQLite history + Yahoo returns",
        "pit": summary,
        "is_oos_cut": str(pd.Timestamp(cut).date()),
        "frozen_thresholds": params,
        "hist_bands": HIST_BANDS,
        "timeslice_months": int(len(ts_grid)),
    }
    (TAB / "table1_project_inventory.json").write_text(json.dumps(inv, indent=2, default=str), encoding="utf-8")

    print("Figures...")
    # map scarce event study into fig5 helper expecting outage cols
    ev2 = ev.rename(columns={})
    fig_cumreturns(curves)
    fig_oos_bars(econ)
    fig_paths(df)
    fig_lobo(lobo)
    # event figure
    fig, ax1 = plt.subplots(figsize=(7.4, 3.8))
    ax1.plot(ev["k"], ev["WMI"], "o-", label="WMI", color="#5B9BD5")
    ax1.plot(ev["k"], ev["ACWMI"], "s-", label="ACWMI", color="#C55A11")
    ax1.set_xlabel("Event time around scarce-world states (bottom B_hier quintile)")
    ax1.set_ylabel("World-model index")
    ax2 = ax1.twinx()
    ax2.plot(ev["k"], ev["ret"], "^--", label="equal-weight ret", color="#548235")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="best")
    ax1.axvline(0, color="gray", ls="--")
    ax1.set_title("Fig. 5. Event study: real PIT scarce-world states")
    fig.tight_layout()
    fig.savefig(FIG / "fig5_quality_scatter.png", bbox_inches="tight")
    fig.savefig(FIG / "fig5_quality_scatter.pdf", bbox_inches="tight")
    plt.close(fig)

    fig_thin_thick(tt)
    fig_pareto(oos)
    fig_is_oos_stability(params, is_df, oos)

    lines = [
        "# Real PIT multi-band experiment results",
        "",
        f"- PIT archive: **{summary['start']} → {summary['end']}**, {summary['n_rows']} rows",
        f"- Band ready rates: `{summary['band_ready_rates']}`",
        f"- IS/OOS cut: **{inv['is_oos_cut']}**",
        f"- Frozen: `{params}`",
        f"- Bootstrap: circular block, n_boot=999, block=5 trading days",
        "",
        "## OOS economic value",
        "",
        econ.to_markdown(index=False),
        "",
        "## OOS block-bootstrap contrasts",
        "",
        boot_df.to_markdown(index=False),
        "",
        "## LOBO (durable bands)",
        "",
        lobo.to_markdown(index=False),
        "",
        "## Thin vs thick (real PIT statuses)",
        "",
        tt.to_markdown(index=False),
        "",
        f"- Thick − Thin bootstrap: `{thick_vs_thin}`",
        "",
        "## Mechanism (opened)",
        "",
        mech_def.to_markdown(index=False),
        "",
        mech_sum.to_markdown(index=False),
        "",
        "## Notes",
        "- Exchange/macro/alternative have durable DB history; news/onchain/options/tokenomics are mostly collection-day right-censored.",
        "- Natural hard outages are rare in continuous OKX backfill; scarce-world states use bottom B_hier quintile for event study.",
        "- Mechanism signal is the deterministic R1–R3 rule in `directional_signal` (no latent model).",
        "- time_slice grid exported to table_timeslice_grid.csv (analytics snapshots still sparse historically).",
    ]
    (OUT / "EXPERIMENT_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "experiment_summary.json").write_text(
        json.dumps(
            {
                "inventory": inv,
                "econ_oos": econ.to_dict(orient="records"),
                "bootstrap_oos": boot_df.to_dict(orient="records"),
                "lobo": lobo.to_dict(orient="records"),
                "thin_thick": tt.to_dict(orient="records"),
                "thin_thick_bootstrap": thick_vs_thin,
                "mechanism_definition": mech_def.to_dict(orient="records"),
                "mechanism_by_regime": mech_sum.to_dict(orient="records"),
                "event_study": ev.to_dict(orient="records"),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print("Done.")


if __name__ == "__main__":
    main()
