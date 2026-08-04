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
consistency_from_signs = _jf.consistency_from_signs
directional_signal = _jf.directional_signal
evaluate_policies = _jf.evaluate_policies
white_reality_check = _jf.white_reality_check
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
from pdf.sci.experiment_config import (
    config_manifest,
    content_bands,
    hist_bands,
    load_experiment_config,
)

DATA = Path(__file__).resolve().parents[1] / "data"
TAB = Path(__file__).resolve().parents[1] / "tables"
FIG = Path(__file__).resolve().parents[1] / "figures"
OUT = Path(__file__).resolve().parent
TAB.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

_CFG = load_experiment_config()
BANDS = list(AssetReadinessService.BAND_WEIGHTS.keys())
HIST_BANDS = hist_bands()  # durable history in archive
CONTENT_BANDS = content_bands()
DB_DIR = ROOT / "database"


def continuous_honesty(excl_rate: float, cont_rate: float) -> float:
    return float(np.exp(-2.0 * cont_rate) * max(0.0, 1.0 - 0.5 * (1.0 - excl_rate)))


def load_band_content_features() -> pd.DataFrame:
    """PIT-safe daily band-content tilts from vintaged history tables.

    macro_tilt: +1 if both VIX and DXY 5d as-of changes are negative (risk-on),
    -1 if both positive (risk-off), else 0. Uses available_at (fallback
    observation_time) <= t so vintages are respected.
    alt_tilt: sign of stablecoin_net_supply_change_7d at the latest observation
    strictly before t (liquidity inflow proxy).

    Cached to pdf/data/band_content_features.csv so experiments reproduce
    without the SQLite archive.
    """
    import sqlite3

    cache = DATA / "band_content_features.csv"
    db = DB_DIR / "market_data.db"

    def _from_cache() -> pd.DataFrame:
        if not cache.exists():
            raise SystemExit("Neither usable market_data.db history nor band_content_features.csv available")
        out = pd.read_csv(cache, parse_dates=["date"])
        # Drop placeholder rows with no usable tilt inputs
        if "vix_chg5" in out.columns:
            usable = out.dropna(subset=["vix_chg5", "dxy_chg5"], how="all")
            if len(usable):
                out = usable
        if len(out) == 0 or (out[["macro_tilt", "alt_tilt"]].abs().sum().sum() == 0 and "vix_chg5" not in out.columns):
            raise SystemExit("band_content_features.csv is empty/unusable")
        return out

    if not db.exists():
        return _from_cache()

    con = sqlite3.connect(str(db))

    def asof_daily(table: str, factor: str, value_col: str = "value") -> pd.Series:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if not cols:
            return pd.Series(dtype=float)
        avail_expr = "available_at" if "available_at" in cols else "observation_time"
        q = f"""
            SELECT observation_time, {avail_expr} AS available_at, {value_col} AS v
            FROM {table} WHERE factor_id = ? AND {value_col} IS NOT NULL
            ORDER BY observation_time
        """
        try:
            raw = pd.read_sql(q, con, params=(factor,))
        except Exception:
            return pd.Series(dtype=float)
        if raw.empty:
            return pd.Series(dtype=float)
        avail = pd.to_datetime(raw["available_at"].fillna(raw["observation_time"]), format="mixed")
        s = pd.Series(raw["v"].astype(float).to_numpy(), index=avail).sort_index()
        s = s[~s.index.duplicated(keep="last")]
        # last value known strictly before each calendar midnight
        days = pd.date_range("2025-06-01", s.index.max().normalize(), freq="D")
        return s.reindex(s.index.union(days).drop_duplicates()).ffill().reindex(days)

    vix = asof_daily("macro_timeseries", "vix")
    dxy = asof_daily("macro_timeseries", "dxy")
    ssc = asof_daily("alternative_timeseries", "stablecoin_net_supply_change_7d")
    con.close()

    # Empty schema / empty history must not overwrite the checked-in cache.
    if vix.empty and dxy.empty and ssc.empty:
        print("band content: SQLite history empty — using cached band_content_features.csv")
        return _from_cache()

    df = pd.DataFrame({"vix": vix, "dxy": dxy, "ssc7": ssc})
    # tilts computed on information available before t: shift by one day
    vix_chg = df["vix"].diff(5).shift(1)
    dxy_chg = df["dxy"].diff(5).shift(1)
    ssc_prev = df["ssc7"].shift(1)
    macro_tilt = np.where(
        (vix_chg < 0) & (dxy_chg < 0), 1.0, np.where((vix_chg > 0) & (dxy_chg > 0), -1.0, 0.0)
    )
    alt_tilt = np.sign(ssc_prev.fillna(0.0))
    out = pd.DataFrame(
        {
            "date": df.index,
            "vix_chg5": vix_chg.to_numpy(),
            "dxy_chg5": dxy_chg.to_numpy(),
            "ssc7_prev": ssc_prev.to_numpy(),
            "macro_tilt": macro_tilt,
            "alt_tilt": alt_tilt.to_numpy(),
        }
    ).dropna(subset=["macro_tilt", "alt_tilt"])
    if len(out) == 0 or out[["vix_chg5", "dxy_chg5"]].notna().sum().sum() == 0:
        print("band content: DB rebuild unusable — falling back to cache")
        return _from_cache()
    out.to_csv(cache, index=False)
    return out


def load_funding_daily() -> pd.DataFrame:
    """Daily perp funding per asset from exchange archive (sum of 8h prints).

    Cached to pdf/data/funding_daily.csv. Missing dates → no adjustment.
    """
    import sqlite3

    cache = DATA / "funding_daily.csv"
    db = DB_DIR / "exchange_data.db"
    if not db.exists():
        if cache.exists():
            return pd.read_csv(cache, parse_dates=["date"])
        return pd.DataFrame(columns=["date", "asset", "funding_rate_daily"])
    con = sqlite3.connect(str(db))
    raw = pd.read_sql(
        "SELECT symbol, funding_rate, timestamp FROM funding_rates WHERE funding_rate IS NOT NULL",
        con,
    )
    con.close()
    if raw.empty:
        return pd.DataFrame(columns=["date", "asset", "funding_rate_daily"])
    raw["date"] = pd.to_datetime(raw["timestamp"], format="mixed").dt.normalize()
    raw["asset"] = raw["symbol"].str.split("/").str[0]
    out = (
        raw.groupby(["date", "asset"])["funding_rate"].sum().reset_index()
        .rename(columns={"funding_rate": "funding_rate_daily"})
    )
    out.to_csv(cache, index=False)
    return out


def readiness_ratio(status: str) -> float:
    return float(AssetReadinessService._status_ratio(status))


def recompute_world(
    df: pd.DataFrame,
    drop_band: str | None = None,
    thin: bool = False,
    weights: tuple[float, float, float] = (0.25, 0.35, 0.40),
) -> pd.DataFrame:
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
        B_hier = weights[0] * B_domain + weights[1] * B_band + weights[2] * B_asset
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


def attach_engines(pit: pd.DataFrame, content: pd.DataFrame | None = None) -> pd.DataFrame:
    pit = pit.sort_values(["asset", "date"]).copy()
    tilt_by_date: dict = {}
    content_by_date: dict = {}
    if content is not None and len(content):
        c = content.set_index(pd.to_datetime(content["date"]).dt.normalize())
        tilt_by_date = {
            d: (float(r["macro_tilt"]), float(r["alt_tilt"])) for d, r in c.iterrows()
        }
        content_by_date = {
            d: (
                float(r.get("vix_chg5") or 0.0) if pd.notna(r.get("vix_chg5")) else 0.0,
                float(r.get("dxy_chg5") or 0.0) if pd.notna(r.get("dxy_chg5")) else 0.0,
            )
            for d, r in c.iterrows()
        }
    rows = []
    for asset, g in pit.groupby("asset"):
        hist = []
        for _, r in g.iterrows():
            eng = run_engines(asset, np.array(hist, dtype=float))
            d = pd.Timestamp(r["date"]).normalize()
            m_tilt, a_tilt = tilt_by_date.get(d, (0.0, 0.0))
            vix_chg, dxy_chg = content_by_date.get(d, (0.0, 0.0))
            # Content is usable only when the band is PIT-ready at t: this makes
            # leave-one-band-out a true deletion of content, not only of gating.
            if str(r.get("st_macro", "missing")) != "ready":
                m_tilt = 0.0
                vix_chg, dxy_chg = 0.0, 0.0
            if str(r.get("st_alternative", "missing")) != "ready":
                a_tilt = 0.0
            eng["macro_tilt"] = m_tilt
            eng["alt_tilt"] = a_tilt
            base_signs = list(eng.get("signs", []))
            C_base = eng["C"]
            ext_signs = base_signs + [t for t in (m_tilt, a_tilt) if t != 0]
            C_ext = consistency_from_signs(ext_signs) if len(ext_signs) >= 2 else C_base
            eng["C"] = C_ext
            sig = directional_signal(eng)
            gamma = REGIME_GAMMA.get(eng["detected_regime"], REGIME_GAMMA["range"])
            ac = acwmi(r["B_hier"], r["U"], r["H_cont"], eng["S"], C_ext, gamma)
            rec = r.to_dict()
            rec.update(
                {
                    "S": eng["S"],
                    "C": C_ext,
                    "C_base": C_base,
                    "cascade_p": eng["cascade_p"],
                    "systemic": eng["systemic"],
                    "detected_regime": eng["detected_regime"],
                    "detect_conf": eng.get("detect_conf", 0.0),
                    "signal": sig,
                    "mom5": eng["mom5"],
                    "macro_tilt": m_tilt,
                    "alt_tilt": a_tilt,
                    "vix_chg5": vix_chg,
                    "dxy_chg5": dxy_chg,
                    "signs_json": json.dumps(base_signs),
                    "ACWMI": ac,
                }
            )
            rows.append(rec)
            hist.append(float(r["ret"]))
    df = pd.DataFrame(rows)
    df = assign_scarce_expanding(df)
    # Prefer scarce days as identifying states when hard outages are rare in continuous backfills
    df["outage_id"] = ((df["outage"] == 1) | (df["scarce"] == 1)).astype(int)
    return df


def assign_scarce_expanding(df: pd.DataFrame) -> pd.DataFrame:
    """Label scarce-world days with an expanding (causal) B_hier quantile.

    Avoids full-sample look-ahead that would contaminate event-study labels.
    """
    out = df.copy()
    scarce_cfg = _CFG["scarce_world"]
    q = float(scarce_cfg["quantile"])
    min_hist = int(scarce_cfg["min_history_days"])
    daily = (
        out.groupby("date", sort=True)["B_hier"]
        .mean()
        .rename("B_mkt")
        .to_frame()
        .sort_index()
    )
    thr = []
    vals = daily["B_mkt"].to_numpy()
    for i in range(len(daily)):
        if i < min_hist:
            thr.append(np.nan)
        else:
            thr.append(float(np.nanquantile(vals[:i], q)))
    daily["scarce_thr"] = thr
    daily["scarce"] = ((daily["B_mkt"] <= daily["scarce_thr"]) & daily["scarce_thr"].notna()).astype(int)
    out = out.merge(daily[["scarce", "scarce_thr"]], left_on="date", right_index=True, how="left")
    out["scarce"] = out["scarce"].fillna(0).astype(int)
    return out


def scramble_band_content(df: pd.DataFrame, seed: int = 17) -> pd.DataFrame:
    """Date-scramble macro/alt tilts (preserve marginals, destroy timing).

    Placebo for the content channel: if OOS value survives scrambling, the
    apparent band MIG is not coming from correctly timed compiled content.
    """
    out = df.copy()
    dates = np.array(sorted(out["date"].unique()))
    rng = np.random.default_rng(seed)
    perm = dates.copy()
    rng.shuffle(perm)
    mapping = dict(zip(dates, perm))
    tilt_src = (
        out.groupby("date", sort=True)[["macro_tilt", "alt_tilt"]]
        .mean()
        .to_dict(orient="index")
    )
    new_m, new_a, new_C, new_sig, new_ac = [], [], [], [], []
    for _, r in out.iterrows():
        src = tilt_src[mapping[r["date"]]]
        m_tilt = float(src["macro_tilt"])
        a_tilt = float(src["alt_tilt"])
        # Respect PIT readiness after scramble (content unusable if band not ready)
        if str(r.get("st_macro", "missing")) != "ready":
            m_tilt = 0.0
        if str(r.get("st_alternative", "missing")) != "ready":
            a_tilt = 0.0
        base_signs = json.loads(r["signs_json"]) if isinstance(r.get("signs_json"), str) else []
        ext = base_signs + [t for t in (m_tilt, a_tilt) if t != 0]
        C = consistency_from_signs(ext) if len(ext) >= 2 else float(r["C_base"])
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": m_tilt,
            "alt_tilt": a_tilt,
        }
        sig = directional_signal(eng)
        gamma = REGIME_GAMMA.get(r["detected_regime"], REGIME_GAMMA["range"])
        ac = acwmi(r["B_hier"], r["U"], r["H_cont"], r["S"], C, gamma)
        new_m.append(m_tilt)
        new_a.append(a_tilt)
        new_C.append(C)
        new_sig.append(sig)
        new_ac.append(ac)
    out["macro_tilt"], out["alt_tilt"] = new_m, new_a
    out["C"], out["signal"], out["ACWMI"] = new_C, new_sig, new_ac
    return out


def _macro_tilt_from_chgs(vix_chg: float, dxy_chg: float) -> float:
    if vix_chg < 0 and dxy_chg < 0:
        return 1.0
    if vix_chg > 0 and dxy_chg > 0:
        return -1.0
    return 0.0


def delete_macro_component(df: pd.DataFrame, component: str) -> pd.DataFrame:
    """Zero one leg of macro_tilt (vix or dxy) and recompute signal/C/ACWMI.

    Identifies whether LOBO macro value is VIX-driven, DXY-driven, or requires conjunction.
    """
    if component not in {"vix", "dxy"}:
        raise ValueError(component)
    out = df.copy()
    new_m, new_C, new_sig, new_ac = [], [], [], []
    for _, r in out.iterrows():
        vix = 0.0 if component == "vix" else float(r.get("vix_chg5") or 0.0)
        dxy = 0.0 if component == "dxy" else float(r.get("dxy_chg5") or 0.0)
        if str(r.get("st_macro", "missing")) != "ready":
            m_tilt = 0.0
        else:
            m_tilt = _macro_tilt_from_chgs(vix, dxy)
        a_tilt = float(r["alt_tilt"])
        base_signs = json.loads(r["signs_json"]) if isinstance(r.get("signs_json"), str) else []
        ext = base_signs + [t for t in (m_tilt, a_tilt) if t != 0]
        C = consistency_from_signs(ext) if len(ext) >= 2 else float(r["C_base"])
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": m_tilt,
            "alt_tilt": a_tilt,
        }
        sig = directional_signal(eng)
        gamma = REGIME_GAMMA.get(r["detected_regime"], REGIME_GAMMA["range"])
        ac = acwmi(r["B_hier"], r["U"], r["H_cont"], r["S"], C, gamma)
        new_m.append(m_tilt)
        new_C.append(C)
        new_sig.append(sig)
        new_ac.append(ac)
    out["macro_tilt"] = new_m
    out["C"], out["signal"], out["ACWMI"] = new_C, new_sig, new_ac
    return out


def plant_availability_shocks(
    df: pd.DataFrame,
    *,
    rate: float = 0.05,
    bands: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Plant random band-missing shocks (pre-registered rate) for O_t designs.

    Shocks are applied to calendar dates (same mask for all assets on that day).
    Content tilts for shocked bands are zeroed and world metrics recomputed.
    """
    bands = bands or ["macro", "alternative"]
    out = df.copy()
    dates = np.array(sorted(out["date"].unique()))
    rng = np.random.default_rng(seed)
    n_shock = max(1, int(round(len(dates) * rate)))
    shocked = set(rng.choice(dates, size=min(n_shock, len(dates)), replace=False))
    for band in bands:
        col = f"st_{band}"
        if col in out.columns:
            out.loc[out["date"].isin(shocked), col] = "missing"
    # Recompute world metrics under planted missingness, then wipe shocked content.
    out = recompute_world(out)
    if "macro" in bands:
        out.loc[out["date"].isin(shocked), "macro_tilt"] = 0.0
        out.loc[out["date"].isin(shocked), "vix_chg5"] = 0.0
        out.loc[out["date"].isin(shocked), "dxy_chg5"] = 0.0
    if "alternative" in bands:
        out.loc[out["date"].isin(shocked), "alt_tilt"] = 0.0
    # Rebuild signals/ACWMI from (possibly zeroed) tilts
    new_C, new_sig, new_ac = [], [], []
    for _, r in out.iterrows():
        m_tilt = float(r["macro_tilt"])
        a_tilt = float(r["alt_tilt"])
        base_signs = json.loads(r["signs_json"]) if isinstance(r.get("signs_json"), str) else []
        ext = base_signs + [t for t in (m_tilt, a_tilt) if t != 0]
        C = consistency_from_signs(ext) if len(ext) >= 2 else float(r["C_base"])
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": m_tilt,
            "alt_tilt": a_tilt,
        }
        sig = directional_signal(eng)
        gamma = REGIME_GAMMA.get(r["detected_regime"], REGIME_GAMMA["range"])
        ac = acwmi(r["B_hier"], r["U"], r["H_cont"], r["S"], C, gamma)
        new_C.append(C)
        new_sig.append(sig)
        new_ac.append(ac)
    out["C"], out["signal"], out["ACWMI"] = new_C, new_sig, new_ac
    out["planted_shock"] = out["date"].isin(shocked).astype(int)
    out.attrs["planted_shock_dates"] = [str(pd.Timestamp(d).date()) for d in sorted(shocked)]
    out.attrs["planted_shock_rate"] = rate
    return out


def compilation_wedge_bridge(df: pd.DataFrame, cut) -> dict:
    """OOS predictive bridge: compiled features vs thin (momentum-only).

    Estimates a simple linear projection of next-day asset returns on
    pre-specified compiled features vs mom5 alone (IS-fit, OOS-eval).
    This is a transparent stand-in for the compilation wedge / MIG idea:
    does F^AI span incremental return variation beyond the thin set?
    """
    panel = df.sort_values(["asset", "date"]).copy()
    panel["y"] = panel.groupby("asset")["ret"].shift(-1)
    feats_compiled = ["mom5", "macro_tilt", "alt_tilt", "cascade_p", "B_hier", "WMI"]
    feats_thin = ["mom5"]
    is_mask = panel["date"] < cut
    oos_mask = panel["date"] >= cut
    train = panel.loc[is_mask].dropna(subset=["y"] + feats_compiled)
    test = panel.loc[oos_mask].dropna(subset=["y"] + feats_compiled)
    if len(train) < 50 or len(test) < 50:
        return {"status": "insufficient_rows", "n_train": int(len(train)), "n_test": int(len(test))}

    def _fit_predict(cols: list[str]):
        x_tr = train[cols].to_numpy(dtype=float)
        y_tr = train["y"].to_numpy(dtype=float)
        x_te = test[cols].to_numpy(dtype=float)
        y_te = test["y"].to_numpy(dtype=float)
        # add intercept
        x_tr = np.column_stack([np.ones(len(x_tr)), x_tr])
        x_te = np.column_stack([np.ones(len(x_te)), x_te])
        beta, *_ = np.linalg.lstsq(x_tr, y_tr, rcond=None)
        pred = x_te @ beta
        ss_res = float(np.sum((y_te - pred) ** 2))
        ss_tot = float(np.sum((y_te - y_te.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        # Directional CE proxy: trade sign(pred), equal-weight daily
        tmp = test[["date", "asset", "y"]].copy()
        tmp["pos"] = np.sign(pred)
        daily = tmp.groupby("date").apply(lambda g: float((g["pos"] * g["y"]).mean()), include_groups=False)
        mu = float(daily.mean())
        sig = float(daily.std(ddof=1)) if len(daily) > 2 else np.nan
        sharpe = mu / sig * np.sqrt(365) if sig and sig > 0 else 0.0
        # CRRA CE γ=2 on daily (annualize roughly by *365 for level comparability)
        wealth = 1.0 + daily.to_numpy()
        wealth = np.clip(wealth, 1e-8, None)
        ce_daily = float(np.mean(wealth ** (-1)) ** (-1) - 1.0)  # γ=2 ⇒ 1-γ=-1
        return {
            "r2_oos": round(r2, 6),
            "ann_mean": round(mu * 365, 4),
            "Sharpe": round(sharpe, 3),
            "CE_daily": round(ce_daily, 6),
            "n_oos": int(len(test)),
        }

    thick = _fit_predict(feats_compiled)
    thin = _fit_predict(feats_thin)
    return {
        "status": "ok",
        "compiled": thick,
        "thin": thin,
        "dR2_compiled_minus_thin": round(thick["r2_oos"] - thin["r2_oos"], 6),
        "dSharpe_compiled_minus_thin": round(thick["Sharpe"] - thin["Sharpe"], 3),
        "features_compiled": feats_compiled,
        "features_thin": feats_thin,
        "note": "IS-fit OLS, OOS evaluate; transparent bridge for compilation wedge, not a trading claim",
    }


def event_study_availability(df: pd.DataFrame) -> pd.DataFrame:
    """Event study around hard availability shocks (outage==1), not scarce proxies."""
    agg = {
        "ret": ("ret", "mean"),
        "WMI": ("WMI", "mean"),
        "ACWMI": ("ACWMI", "mean"),
        "outage": ("outage", "max"),
        "B": ("B_hier", "mean"),
    }
    if "market_outage" in df.columns:
        agg["market_outage"] = ("market_outage", "max")
    daily = df.groupby("date").agg(**agg).sort_index()
    if "market_outage" not in daily.columns:
        daily["market_outage"] = 0
    events = daily.index[(daily["outage"] == 1) | (daily["market_outage"] == 1)]
    gap = int(_CFG["scarce_world"]["event_gap_days"])
    kept = []
    last = None
    for e in events:
        if last is None or (pd.Timestamp(e) - pd.Timestamp(last)).days >= gap:
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
                "n_events": len(kept),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "table_ot_availability_event_study.csv", index=False)
    return out


def delete_band_content(df: pd.DataFrame, bands: list[str]) -> pd.DataFrame:
    """Zero the content tilts of `bands` and recompute C, signal, and ACWMI.

    This is the *content* channel of information-set deletion (I \\ E_k);
    band-status deletion via recompute_world is the *gating* channel.
    Exchange content (returns) cannot be deleted without destroying the payoff
    data itself, so content deletion applies to macro/alternative only.
    """
    out = df.copy()
    zero_macro = "macro" in bands
    zero_alt = "alternative" in bands
    new_C, new_sig, new_ac = [], [], []
    for _, r in out.iterrows():
        m_tilt = 0.0 if zero_macro else float(r["macro_tilt"])
        a_tilt = 0.0 if zero_alt else float(r["alt_tilt"])
        base_signs = json.loads(r["signs_json"]) if isinstance(r.get("signs_json"), str) else []
        ext = base_signs + [t for t in (m_tilt, a_tilt) if t != 0]
        C = consistency_from_signs(ext) if len(ext) >= 2 else float(r["C_base"])
        eng = {
            "detected_regime": r["detected_regime"],
            "cascade_p": float(r["cascade_p"]),
            "mom5": float(r["mom5"]),
            "macro_tilt": m_tilt,
            "alt_tilt": a_tilt,
        }
        sig = directional_signal(eng)
        gamma = REGIME_GAMMA.get(r["detected_regime"], REGIME_GAMMA["range"])
        ac = acwmi(r["B_hier"], r["U"], r["H_cont"], r["S"], C, gamma)
        new_C.append(C)
        new_sig.append(sig)
        new_ac.append(ac)
    out["C"], out["signal"], out["ACWMI"] = new_C, new_sig, new_ac
    return out


def rebuild_acwmi(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ACWMI"] = [
        acwmi(b, u, h, s, c, REGIME_GAMMA.get(rg, REGIME_GAMMA["range"]))
        for b, u, h, s, c, rg in zip(out["B_hier"], out["U"], out["H_cont"], out["S"], out["C"], out["detected_regime"])
    ]
    return out


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

    print("Load band-content features (vintaged macro / alternative)...")
    content = load_band_content_features()
    print("content days", len(content), "macro_tilt mean", round(float(content["macro_tilt"].mean()), 3),
          "alt_tilt mean", round(float(content["alt_tilt"].mean()), 3))
    funding = load_funding_daily()
    print("funding rows", len(funding))

    print("Attach engines (PIT returns + band content)...")
    df = attach_engines(pit, content=content)
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
            mean_macro_tilt=("macro_tilt", "mean"),
            mean_alt_tilt=("alt_tilt", "mean"),
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

    # LOBO on historically durable bands, decomposed into content vs gating channels.
    # Content channel: zero the band's tilt in signals/C (information deletion in the
    # action rule). Gating channel: band status → missing (B/U/H/WMI/ACWMI fall, so
    # abstention pattern changes). "both" is the full information-set deletion I\E_k.
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
    decomp_rows = []
    for band in HIST_BANDS:
        variants = {}
        # gating-only: status deleted, content kept
        d_g = rebuild_acwmi(recompute_world(df, drop_band=band))
        variants["gating"] = d_g
        # content-only (macro/alternative only; exchange content is the return data itself)
        if band in CONTENT_BANDS:
            d_c = delete_band_content(df, [band])
            variants["content"] = d_c
            d_b = delete_band_content(recompute_world(df, drop_band=band), [band])
            variants["both"] = d_b
        else:
            variants["both"] = d_g
        stats = {}
        for label, dv in variants.items():
            _, oos_v, _ = split_is_oos(dv)
            st = portfolio_stats(oos_v, strategy_positions(oos_v, "ac", params))
            bp = bootstrap_delta_pvalues(st["daily"], base_daily, n_boot=999, block=5)
            stats[label] = (st, bp)
        st_full, bp_full = stats["both"]
        lobo_rows.append(
            {
                "band_dropped": band,
                "Sharpe": round(st_full["Sharpe"], 3),
                "CE": round(st_full["CE"], 4),
                "abstain_rate": round(st_full["abstain_rate"], 3),
                "dCE": round(st_full["CE"] - base["CE"], 4),
                "p_dCE": bp_full.get("p_CE"),
            }
        )
        decomp_rows.append(
            {
                "band": band,
                "dCE_total": round(st_full["CE"] - base["CE"], 4),
                "p_total": bp_full.get("p_CE"),
                "dCE_content_only": round(stats["content"][0]["CE"] - base["CE"], 4) if "content" in stats else None,
                "p_content": stats["content"][1].get("p_CE") if "content" in stats else None,
                "dCE_gating_only": round(stats["gating"][0]["CE"] - base["CE"], 4),
                "p_gating": stats["gating"][1].get("p_CE"),
            }
        )

    # Joint content+gating deletion of macro AND alternative (orthogonality check)
    d_joint_g = recompute_world(df, drop_band="macro")
    d_joint_g = recompute_world(d_joint_g, drop_band="alternative")
    d_joint = delete_band_content(d_joint_g, ["macro", "alternative"])
    d_joint = rebuild_acwmi(d_joint)
    _, oos_j, _ = split_is_oos(d_joint)
    st_j = portfolio_stats(oos_j, strategy_positions(oos_j, "ac", params))
    bp_j = bootstrap_delta_pvalues(st_j["daily"], base_daily, n_boot=_CFG["inference"]["n_boot"], block=_CFG["inference"]["block"])
    lobo_rows.append(
        {
            "band_dropped": "macro+alternative",
            "Sharpe": round(st_j["Sharpe"], 3),
            "CE": round(st_j["CE"], 4),
            "abstain_rate": round(st_j["abstain_rate"], 3),
            "dCE": round(st_j["CE"] - base["CE"], 4),
            "p_dCE": bp_j.get("p_CE"),
        }
    )
    d_joint_content = delete_band_content(df, ["macro", "alternative"])
    _, oos_jc, _ = split_is_oos(d_joint_content)
    st_jc = portfolio_stats(oos_jc, strategy_positions(oos_jc, "ac", params))
    bp_jc = bootstrap_delta_pvalues(st_jc["daily"], base_daily, n_boot=_CFG["inference"]["n_boot"], block=_CFG["inference"]["block"])
    decomp_rows.append(
        {
            "band": "macro+alternative",
            "dCE_total": round(st_j["CE"] - base["CE"], 4),
            "p_total": bp_j.get("p_CE"),
            "dCE_content_only": round(st_jc["CE"] - base["CE"], 4),
            "p_content": bp_jc.get("p_CE"),
            "dCE_gating_only": None,
            "p_gating": None,
        }
    )

    lobo = pd.DataFrame(lobo_rows)
    lobo.to_csv(TAB / "table_lobo.csv", index=False)
    print(lobo)
    lobo_decomp = pd.DataFrame(decomp_rows)
    lobo_decomp.to_csv(TAB / "table_lobo_decomposition.csv", index=False)
    print(lobo_decomp)

    # Scrambled-content placebo: destroy tilt timing, keep marginals
    print("Scrambled content placebo...")
    d_scr = scramble_band_content(df, seed=17)
    _, oos_scr, _ = split_is_oos(d_scr)
    st_scr = portfolio_stats(oos_scr, strategy_positions(oos_scr, "thick_ungated", params))
    st_base_ungated = portfolio_stats(oos0, strategy_positions(oos0, "thick_ungated", params))
    bp_scr = bootstrap_delta_pvalues(
        st_scr["daily"],
        st_base_ungated["daily"],
        n_boot=_CFG["inference"]["n_boot"],
        block=_CFG["inference"]["block"],
    )
    placebo = {
        "design": "date-scramble macro_tilt/alt_tilt (seed=17)",
        "base_CE": round(st_base_ungated["CE"], 4),
        "scrambled_CE": round(st_scr["CE"], 4),
        "dCE_scrambled_minus_base": round(st_scr["CE"] - st_base_ungated["CE"], 4),
        "p_CE": bp_scr.get("p_CE"),
        "interpretation": (
            "Placebo should not beat the timed-content rule; "
            "negative dCE supports correctly timed compiled content."
        ),
    }
    (TAB / "table_content_scramble_placebo.json").write_text(
        json.dumps(placebo, indent=2), encoding="utf-8"
    )
    print(placebo)

    # Orthogonal macro components: VIX-only vs DXY-only content deletion
    print("Macro component LOBO (VIX / DXY)...")
    comp_rows = []
    for comp in ("vix", "dxy"):
        d_comp = delete_macro_component(df, comp)
        _, oos_c, _ = split_is_oos(d_comp)
        st_c = portfolio_stats(oos_c, strategy_positions(oos_c, "thick_ungated", params))
        bp_c = bootstrap_delta_pvalues(
            st_c["daily"],
            st_base_ungated["daily"],
            n_boot=_CFG["inference"]["n_boot"],
            block=_CFG["inference"]["block"],
        )
        comp_rows.append(
            {
                "component_zeroed": comp,
                "CE": round(st_c["CE"], 4),
                "dCE_vs_base": round(st_c["CE"] - st_base_ungated["CE"], 4),
                "p_CE": bp_c.get("p_CE"),
                "Sharpe": round(st_c["Sharpe"], 3),
            }
        )
    comp_lobo = pd.DataFrame(comp_rows)
    comp_lobo.to_csv(TAB / "table_macro_component_lobo.csv", index=False)
    print(comp_lobo)

    # Stationary-bootstrap (Politis–Romano) confirmation of headline contrasts
    print("Stationary bootstrap confirmation...")
    stat_rows = {}
    for name, a, b in [
        ("mechanism_minus_momentum", "Thick ungated", "Momentum always"),
        ("mechanism_minus_always_long", "Thick ungated", "Always long"),
    ]:
        if a in curves and b in curves:
            stat_rows[name] = {
                m: bootstrap_delta_pvalues(
                    curves[a], curves[b],
                    n_boot=_CFG["inference"]["n_boot"],
                    block=_CFG["inference"]["block"],
                    method=m,
                )
                for m in ("circular", "stationary")
            }
    (TAB / "table_stationary_bootstrap.json").write_text(
        json.dumps(stat_rows, indent=2), encoding="utf-8"
    )
    for k, v in stat_rows.items():
        print(k, {m: (r["dCE"], r["p_CE"]) for m, r in v.items()})

    # Cost-aware pre-specified contrast (mechanism − momentum at 10 bps)
    print("Cost-aware pre-specified contrast...")
    pos_mech = strategy_positions(oos, "thick_ungated", params)
    pos_mom = strategy_positions(oos, "mom_always", params)
    cost_headline = []
    for cost in (0.0, 10.0, 25.0):
        st_m = portfolio_stats(oos, pos_mech, cost_bps=cost)
        st_o = portfolio_stats(oos, pos_mom, cost_bps=cost)
        bp = bootstrap_delta_pvalues(
            st_m["daily"],
            st_o["daily"],
            n_boot=_CFG["inference"]["n_boot"],
            block=_CFG["inference"]["block"],
        )
        cost_headline.append(
            {
                "contrast": "Mechanism − Momentum",
                "cost_bps": cost,
                "mech_CE": round(st_m["CE"], 4),
                "mom_CE": round(st_o["CE"], 4),
                "dCE": round(st_m["CE"] - st_o["CE"], 4),
                "p_CE": bp.get("p_CE"),
                "ci95_excludes_0": bp.get("ci95_excludes_0_CE"),
                "mech_Sharpe": round(st_m["Sharpe"], 3),
                "mom_Sharpe": round(st_o["Sharpe"], 3),
            }
        )
    cost_pre = pd.DataFrame(cost_headline)
    cost_pre.to_csv(TAB / "table_prespec_cost_contrast.csv", index=False)
    print(cost_pre)

    # Compilation wedge / predictive bridge
    print("Compilation wedge bridge...")
    wedge = compilation_wedge_bridge(df, cut)
    (TAB / "table_compilation_wedge_bridge.json").write_text(
        json.dumps(wedge, indent=2), encoding="utf-8"
    )
    print(wedge)

    # Planted O_t availability shocks (5% dates, macro+alternative)
    print("Planted O_t shocks...")
    d_plant = plant_availability_shocks(df, rate=0.05, bands=["macro", "alternative"], seed=42)
    _, oos_p, _ = split_is_oos(d_plant)
    st_p = portfolio_stats(oos_p, strategy_positions(oos_p, "thick_ungated", params))
    bp_p = bootstrap_delta_pvalues(
        st_p["daily"],
        st_base_ungated["daily"],
        n_boot=_CFG["inference"]["n_boot"],
        block=_CFG["inference"]["block"],
    )
    planted = {
        "rate": 0.05,
        "bands": ["macro", "alternative"],
        "seed": 42,
        "n_shock_dates": len(d_plant.attrs.get("planted_shock_dates", [])),
        "shock_dates": d_plant.attrs.get("planted_shock_dates", []),
        "base_CE": round(st_base_ungated["CE"], 4),
        "planted_CE": round(st_p["CE"], 4),
        "dCE_planted_minus_base": round(st_p["CE"] - st_base_ungated["CE"], 4),
        "p_CE": bp_p.get("p_CE"),
        "interpretation": "Negative dCE indicates planted missingness destroys value (O_t channel).",
    }
    (TAB / "table_planted_ot_shocks.json").write_text(json.dumps(planted, indent=2), encoding="utf-8")
    print(planted)

    # Thin vs thick using real statuses. Thin world deletes BOTH the gating
    # channel (band statuses → missing) and the content channel (tilts zeroed):
    # an exchange-only observer has no macro/alternative information at all.
    thin = delete_band_content(recompute_world(df, thin=True), ["macro", "alternative"])
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

    # Block-length sensitivity for the two headline contrasts
    print("Block-length sensitivity...")
    block_rows = []
    for blk in (5, 10, 21):
        r1 = bootstrap_delta_pvalues(
            daily_by_world["Thick real PIT (ex+macro+alt…)"],
            daily_by_world["Thin (exchange only, real PIT)"],
            n_boot=999,
            block=blk,
        )
        r2 = bootstrap_delta_pvalues(curves["ACWMI (IS-frozen)"], curves["Always long"], n_boot=999, block=blk)
        block_rows.append(
            {
                "block": blk,
                "thick_minus_thin_p_CE": r1["p_CE"],
                "thick_minus_thin_ci": f"[{r1['ci_dCE_05']},{r1['ci_dCE_95']}]",
                "acwmi_minus_long_p_CE": r2["p_CE"],
                "acwmi_minus_long_ci": f"[{r2['ci_dCE_05']},{r2['ci_dCE_95']}]",
            }
        )
    block_sens = pd.DataFrame(block_rows)
    block_sens.to_csv(TAB / "table_block_sensitivity.csv", index=False)
    print(block_sens)

    # White (2000) reality check across selective/mechanism policies vs always-long
    print("White reality check...")
    rc = white_reality_check(
        {k: v for k, v in curves.items() if k in {
            "Always long", "Momentum always", "Thick ungated", "ACWMI (IS-frozen)", "WMI threshold (0.2)"
        }},
        benchmark="Always long",
        n_boot=999,
        block=5,
    )
    (TAB / "table_reality_check.json").write_text(json.dumps(rc, indent=2), encoding="utf-8")
    print(rc)

    # Transaction costs and funding adjustment
    print("Cost / funding sensitivity...")
    cost_rows = []
    for pol_name, pol_key in [
        ("Thick ungated", "thick_ungated"),
        ("ACWMI (IS-frozen)", "ac"),
        ("Momentum always", "mom_always"),
        ("Always long", "always_long"),
    ]:
        pos = strategy_positions(oos, pol_key, params)
        for cost in (0.0, 10.0, 25.0, 50.0):
            st = portfolio_stats(oos, pos, cost_bps=cost)
            cost_rows.append(
                {
                    "policy": pol_name,
                    "cost_bps": cost,
                    "funding": "no",
                    "Sharpe": round(st["Sharpe"], 3),
                    "CE": round(st["CE"], 4),
                }
            )
        st_f = portfolio_stats(oos, pos, cost_bps=10.0, funding_daily=funding if len(funding) else None)
        cost_rows.append(
            {
                "policy": pol_name,
                "cost_bps": 10.0,
                "funding": "yes (where archived)",
                "Sharpe": round(st_f["Sharpe"], 3),
                "CE": round(st_f["CE"], 4),
            }
        )
    cost_sens = pd.DataFrame(cost_rows)
    cost_sens.to_csv(TAB / "table_cost_sensitivity.csv", index=False)
    print(cost_sens)

    # Regime-stratified OOS performance (external-validity disclosure)
    print("Regime stratification...")
    strat_rows = []
    for pol_name, pol_key in [("Thick ungated", "thick_ungated"), ("ACWMI (IS-frozen)", "ac")]:
        pos = strategy_positions(oos, pol_key, params)
        tmp = oos[["date", "asset", "ret", "detected_regime"]].copy()
        tmp["pnl"] = pos.values * tmp["ret"].values
        for rg, g in tmp.groupby("detected_regime"):
            strat_rows.append(
                {
                    "policy": pol_name,
                    "regime": rg,
                    "n_asset_days": int(len(g)),
                    "share": round(float(len(g) / len(tmp)), 3),
                    "ann_mean_pnl": round(float(g["pnl"].mean() * 365), 4),
                    "hit_rate": round(float(((np.sign(g["pnl"]) > 0) & (pos.loc[g.index] != 0)).mean()), 3),
                }
            )
    regime_strat = pd.DataFrame(strat_rows)
    regime_strat.to_csv(TAB / "table_regime_stratified.csv", index=False)
    print(regime_strat)

    # ECP / EAR measurement (theory objects instantiated, not just defined)
    ecp_rate = float(((df["detect_conf"] > 0.7) & (df["WMI"] < 0.2)).mean())
    ecp_casc = float(((df["cascade_p"] > 0.7) & (df["WMI"] < 0.2)).mean())
    active = df[df["signal"] != 0]
    ear = 1.0  # every action is bound to named calculator evidence by construction (R1–R3)
    explain = {
        "EAR": ear,
        "UCR": round(1.0 - ear, 4),
        "ECP_rate_detect_conf": round(ecp_rate, 4),
        "ECP_rate_cascade_conf": round(ecp_casc, 4),
        "n_active_asset_days": int(len(active)),
    }
    (TAB / "table_explanation_metrics.json").write_text(json.dumps(explain, indent=2), encoding="utf-8")
    print("explanation metrics", explain)

    # B_hier weight sensitivity (magic-constant robustness)
    print("Weight sensitivity...")
    wt_rows = []
    for wts in [(0.25, 0.35, 0.40), (0.15, 0.35, 0.50), (0.35, 0.35, 0.30), (1 / 3, 1 / 3, 1 / 3)]:
        dw = rebuild_acwmi(recompute_world(df, weights=wts))
        _, oos_w, _ = split_is_oos(dw)
        st = portfolio_stats(oos_w, strategy_positions(oos_w, "ac", params))
        wt_rows.append(
            {
                "weights_dom_band_asset": str(tuple(round(w, 3) for w in wts)),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
            }
        )
    wt_sens = pd.DataFrame(wt_rows)
    wt_sens.to_csv(TAB / "table_weight_sensitivity.csv", index=False)
    print(wt_sens)

    ev = event_study_scarce(df)
    print(ev)
    ev_ot = event_study_availability(df)
    print("O_t availability event study rows", len(ev_ot))

    # archive inventory for paper
    summary = json.loads((DATA / "pit_archive_summary.json").read_text())
    inv = {
        "design": "real multi-band PIT from SQLite history + Yahoo returns",
        "pit": summary,
        "is_oos_cut": str(pd.Timestamp(cut).date()),
        "frozen_thresholds": params,
        "hist_bands": HIST_BANDS,
        "timeslice_months": int(len(ts_grid)),
        "experiment_config": config_manifest(),
        "pre_specified_contrast": _CFG["pre_specified_contrast"],
        "scarce_world_method": _CFG["scarce_world"]["method"],
        "content_scramble_placebo": placebo,
        "macro_component_lobo": comp_lobo.to_dict(orient="records"),
        "prespec_cost_contrast": cost_pre.to_dict(orient="records"),
        "compilation_wedge_bridge": wedge,
        "planted_ot_shocks": planted,
        "stationary_bootstrap": stat_rows,
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
        "## LOBO (durable bands, content+gating deletion)",
        "",
        lobo.to_markdown(index=False),
        "",
        "## LOBO decomposition (content vs gating channel)",
        "",
        lobo_decomp.to_markdown(index=False),
        "",
        "## Thin vs thick (real PIT statuses; thin deletes content AND gating)",
        "",
        tt.to_markdown(index=False),
        "",
        f"- Thick − Thin bootstrap: `{thick_vs_thin}`",
        "",
        "## Block-length sensitivity",
        "",
        block_sens.to_markdown(index=False),
        "",
        "## White (2000) reality check vs Always long",
        "",
        f"`{rc}`",
        "",
        "## Transaction costs and funding",
        "",
        cost_sens.to_markdown(index=False),
        "",
        "## Regime-stratified OOS performance",
        "",
        regime_strat.to_markdown(index=False),
        "",
        "## Explanation / calibration metrics",
        "",
        f"`{explain}`",
        "",
        "## B_hier weight sensitivity (AC policy, frozen thresholds)",
        "",
        wt_sens.to_markdown(index=False),
        "",
        "## Mechanism (opened; band content in signals)",
        "",
        mech_def.to_markdown(index=False),
        "",
        mech_sum.to_markdown(index=False),
        "",
        "## Notes",
        "- Exchange/macro/alternative have durable DB history; news/onchain/options/tokenomics are mostly collection-day right-censored.",
        "- Band content (macro_tilt from vintaged VIX/DXY; alt_tilt from stablecoin 7d net supply) enters R2/R2b/R3 and C directly;",
        "  tilts are forced to 0 whenever the band is not PIT-ready, so LOBO deletes content, not only gating.",
        "- Natural hard outages are rare in continuous OKX backfill; scarce-world states use expanding B_hier quantile (no full-sample look-ahead).",
        "- Hard O_t availability event study exported to table_ot_availability_event_study.csv.",
        "- Joint macro+alternative LOBO and date-scrambled content placebo are reported.",
        "- Macro component LOBO (VIX vs DXY), cost-aware pre-specified contrast, compilation-wedge bridge, planted O_t shocks exported.",
        "- Mechanism signal is the deterministic R1–R3 rule in `directional_signal` (no latent model).",
        "- Timing protocol: decision_at_prev_close (features at t-1 23:59; payoff = day-t close-to-close).",
        f"- Experiment config: `{config_manifest()}`.",
        "- Selective prediction / ACWMI gating is secondary on this sparse archive (often equals ungated).",
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
                "lobo_decomposition": lobo_decomp.to_dict(orient="records"),
                "thin_thick": tt.to_dict(orient="records"),
                "thin_thick_bootstrap": thick_vs_thin,
                "block_sensitivity": block_sens.to_dict(orient="records"),
                "reality_check": rc,
                "cost_sensitivity": cost_sens.to_dict(orient="records"),
                "regime_stratified": regime_strat.to_dict(orient="records"),
                "explanation_metrics": explain,
                "weight_sensitivity": wt_sens.to_dict(orient="records"),
                "mechanism_definition": mech_def.to_dict(orient="records"),
                "mechanism_by_regime": mech_sum.to_dict(orient="records"),
                "event_study": ev.to_dict(orient="records"),
                "ot_availability_event_study": ev_ot.to_dict(orient="records"),
                "content_scramble_placebo": placebo,
                "macro_component_lobo": comp_lobo.to_dict(orient="records"),
                "prespec_cost_contrast": cost_pre.to_dict(orient="records"),
                "compilation_wedge_bridge": wedge,
                "planted_ot_shocks": planted,
                "stationary_bootstrap": stat_rows,
                "experiment_config": config_manifest(),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print("Done.")


if __name__ == "__main__":
    main()
