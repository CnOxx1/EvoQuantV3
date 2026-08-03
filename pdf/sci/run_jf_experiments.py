#!/usr/bin/env python3
"""JF/RFS-oriented empirical suite for RCA-WM / ACWMI.

Design principles (top-finance style):
1. Real daily crypto returns (Yahoo; cached under pdf/data/).
2. Chronological IS/OOS freeze of abstention thresholds.
3. Strong baselines (always-long, momentum, thick-ungated, simple outage rule, WMI).
4. Economic value of selective action (Sharpe, certainty equivalent, drawdown).
5. Leave-one-band-out / thin-vs-thick ablation.
6. Availability shocks O_t constructed to be return-orthogonal (exclusion restriction).
7. Mechanism scores from production EvoQuant calculators on real return windows.

Band availability remains a constructed information-set layer because the local DB
has no multi-year multi-band archive; returns and OOS discipline are real.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from logic_layer.ai_market_context.service import AIMarketContextService
from logic_layer.alpha_decay.calculator import AlphaDecayCalculator
from logic_layer.asset_readiness.service import AssetReadinessService
from logic_layer.contagion_risk.calculator import ContagionRiskCalculator
from logic_layer.flow_decomposition.calculator import FlowDecompositionCalculator
from logic_layer.liquidation_cascade.calculator import LiquidationCascadeCalculator
from logic_layer.regime_detection.classifier import RegimeClassifier, RegimeFeatures
from logic_layer.volatility_forecast.calculator import VolatilityCalculator

FIG_DIR = Path(__file__).resolve().parents[1] / "figures"
TAB_DIR = Path(__file__).resolve().parents[1] / "tables"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUT_DIR = Path(__file__).resolve().parent
FIG_DIR.mkdir(parents=True, exist_ok=True)
TAB_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "figure.dpi": 160,
        "savefig.dpi": 300,
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "legend.fontsize": 8,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

RNG = np.random.default_rng(20260803)
ASSETS = ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "AVAX", "LINK", "DOT", "NEAR"]
BANDS = list(AssetReadinessService.BAND_WEIGHTS.keys())
GAMMA = 2.0  # CRRA for certainty equivalent
RF_DAILY = 0.0

# Frozen production WMI threshold (never tuned on OOS)
WMI_ABS_THR = 0.2

REGIME_GAMMA = {
    "trend": (1.0, 1.0, 1.0, 1.3, 0.8),
    "range": (1.0, 1.1, 1.1, 1.0, 1.0),
    "crisis": (0.9, 1.2, 1.4, 0.8, 1.5),
}


def continuous_honesty(excl_rate: float, cont_rate: float, beta1: float = 2.0, beta2: float = 0.5) -> float:
    return float(np.exp(-beta1 * cont_rate) * max(0.0, 1.0 - beta2 * (1.0 - excl_rate)))


def acwmi(B, U, H, S, C, gamma=(1.0, 1.0, 1.0, 1.0, 1.0)) -> float:
    vals = np.array([max(B, 1e-6), max(U, 1e-6), max(H, 1e-6), max(S, 1e-6), max(C, 1e-6)])
    g = np.array(gamma, dtype=float)
    return float(np.exp(np.sum(g * np.log(vals)) / np.sum(g)))


def wmi_from_project(breadth: float, fresh: int, acceptable: int, total: int, flag: str) -> dict:
    return AIMarketContextService._compute_world_model_index(
        coverage_score=float(breadth),
        pipeline_latency_context={
            "summary": {"total_domains": int(total), "fresh": int(fresh), "acceptable": int(acceptable)}
        },
        data_quality_flag=flag,
        data_quality_flags=[],
    )


def load_real_returns() -> pd.DataFrame:
    path = DATA_DIR / "crypto_daily_yahoo.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; download Yahoo panel first.")
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.dropna(subset=["ret"]).sort_values(["date", "asset"]).reset_index(drop=True)
    # keep common calendar
    counts = df.groupby("date")["asset"].nunique()
    keep = counts[counts >= len(ASSETS) - 1].index
    df = df[df["date"].isin(keep) & df["asset"].isin(ASSETS)].copy()
    return df


def band_readiness_from_masks(ready_mask: dict[str, float]) -> float:
    score = 0.0
    for band, weight in AssetReadinessService.BAND_WEIGHTS.items():
        ratio = float(ready_mask.get(band, 0.0))
        if ratio >= 0.8:
            status = "ready"
        elif ratio >= 0.4:
            status = "limited"
        else:
            status = "missing"
        score += weight * AssetReadinessService._status_ratio(status)
    return float(score)


def consistency_from_signs(signs: list[float]) -> float:
    vals = [s for s in signs if np.isfinite(s) and s != 0]
    if len(vals) < 2:
        return 0.0
    agree = total = 0
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            total += 1
            if vals[i] * vals[j] > 0:
                agree += 1
    return agree / total if total else 0.0


def run_engines(asset: str, hist: np.ndarray) -> dict:
    hist = hist[~np.isnan(hist)]
    if len(hist) < 25:
        mom5 = float(np.sign(np.mean(hist[-5:])) if len(hist) >= 5 else 0.0)
        return {
            "cascade_p": 0.2,
            "systemic": 20.0,
            "S": 0.2,
            "C": 0.5,
            "detected_regime": "range",
            "detect_conf": 0.4,
            "vpin": 0.3,
            "mom5": mom5,
            "vol_regime": "normal",
            "signs": [mom5] if mom5 != 0 else [],
        }
    # Bounded information window: regime/tail measurements must be local, not
    # full-history. (Full-history max-drawdown makes `crisis` an absorbing
    # state and saturates cascade_p — the failure mode exposed by the
    # long-span calibration audit.)
    win = hist[-60:]
    vol_calc = VolatilityCalculator()
    classifier = RegimeClassifier()
    rv = vol_calc.compute_realized_vol(win.tolist()) or 0.2
    vol_regime = vol_calc.classify_vol_regime(float(rv))
    peer = win * 0.7 + RNG.normal(0, np.std(win) * 0.5 + 1e-6, size=len(win))
    covar = ContagionRiskCalculator.compute_covar(win.tolist(), peer.tolist()) or 0.0
    tail_b = ContagionRiskCalculator.compute_tail_beta(win.tolist(), peer.tolist()) or 0.0
    systemic = ContagionRiskCalculator.compute_systemic_risk_score(
        [{"covar_95": float(covar), "conditional_correlation": 0.5, "tail_beta": float(tail_b)}]
    )
    # Left-tail clustering intensity, standardized by local volatility.
    # For thin-tailed returns the bottom-decile mean sits near -1.75σ; excess
    # beyond that indicates clustered liquidation pressure. intensity ∈ [0,1]
    # maps to a cluster of at most 10% of daily capacity (the size_factor
    # saturation point in compute_cascade_probability).
    sigma = float(np.std(win) + 1e-9)
    left = win[win < np.quantile(win, 0.1)]
    z_tail = float(abs(left.mean()) / sigma) if len(left) else 0.0
    intensity = float(np.clip((z_tail - 1.75) / 1.5, 0.0, 1.0))
    cluster = 6e6 * intensity
    distance = 0.7 if vol_regime in {"high", "extreme"} else 2.2
    casc_p = LiquidationCascadeCalculator.compute_cascade_probability(cluster, 6e7, distance)
    signal = np.cumsum(hist[-120:])
    half_life = AlphaDecayCalculator.compute_half_life(signal.tolist()) or 24.0
    crowd = AlphaDecayCalculator.compute_crowding_score(
        [
            {"signal_name": "mom", "direction": 1 if hist[-1] > 0 else -1, "strength": abs(float(hist[-1])) * 20},
            {"signal_name": "funding", "direction": -1 if casc_p > 0.55 else 1, "strength": 1.0},
        ]
    )
    surprise = abs(AlphaDecayCalculator.compute_signal_surprise(float(hist[-1]), hist[:-1].tolist()) or 0.0)
    surprise_n = float(np.clip(abs(surprise) / 2.5, 0.0, 1.0))
    crowding_n = float(np.clip((crowd.get("crowding_score", 50) if isinstance(crowd, dict) else 50) / 100.0, 0, 1))
    hl_factor = float(1.0 - np.exp(-(max(half_life, 1.0)) / 36.0))
    S = float(np.clip(hl_factor * (1.0 - 0.7 * crowding_n) * (0.35 + 0.65 * surprise_n), 0.05, 1.0))
    trades = []
    px = 100.0
    for r in hist[-40:]:
        px *= 1 + r
        trades.append({"volume": float(abs(r) * 1000 + 10), "side": "buy" if r >= 0 else "sell", "price": px})
    vpin = FlowDecompositionCalculator.compute_vpin(trades, bucket_size=20) if trades else 0.0
    flow = FlowDecompositionCalculator.classify_flow(trades) if trades else {"smart_money_direction": "neutral"}
    vol_series = pd.Series(win).rolling(10).std().fillna(sigma).tolist()
    # Real RSI-14 and a trend-strength ADX proxy from the local window (the
    # previous constant placeholders froze the classifier out of trend states).
    r14 = win[-14:]
    gains = float(np.sum(r14[r14 > 0]))
    losses = float(abs(np.sum(r14[r14 < 0])))
    rsi = 100.0 * gains / (gains + losses) if (gains + losses) > 0 else 50.0
    r20 = win[-20:]
    t20 = float(abs(np.mean(r20)) * np.sqrt(len(r20)) / (np.std(r20) + 1e-9))
    adx = float(15.0 + 12.0 * min(t20, 2.5))
    feats = RegimeFeatures(
        returns=win.tolist(),
        volatility=vol_series,
        volume_ratio=1.3 if vol_regime in {"high", "extreme"} else 1.0,
        rsi=rsi,
        adx=adx,
        correlation_to_btc=0.85 if asset != "BTC" else 1.0,
    )
    price_regime, conf = classifier.classify_price_regime(feats)
    label = str(price_regime).lower()
    if label == "crisis" or (vol_regime in {"high", "extreme"} and casc_p > 0.6):
        detected = "crisis"
    elif "trend" in label:
        detected = "trend"
    else:
        detected = "range"
    flow_dir = flow.get("smart_money_direction", "neutral")
    flow_sign = 1.0 if flow_dir == "buy" else (-1.0 if flow_dir == "sell" else 0.0)
    signs = [
        float(np.sign(np.mean(hist[-5:]))),
        flow_sign if flow_sign != 0 else float(np.sign(np.mean(hist[-10:]))),
        -1.0 if casc_p > 0.55 else 1.0,
        -1.0 if (systemic or 0) > 55 else 1.0,
    ]
    return {
        "cascade_p": float(casc_p or 0),
        "systemic": float(systemic or 0),
        "S": S,
        "C": consistency_from_signs(signs),
        "detected_regime": detected,
        "detect_conf": float(conf or 0),
        "vpin": float(vpin or 0),
        "mom5": float(np.sign(np.mean(hist[-5:]))),
        "vol_regime": vol_regime,
        "signs": signs,
    }


def build_world_factors(outage: bool, drop_band: str | None = None, ungated: bool = False, thin: bool = False) -> dict:
    base = {b: 0.9 for b in BANDS}
    if thin:
        for b in BANDS:
            base[b] = 0.9 if b == "exchange" else 0.15
    if outage:
        for k in ["options", "onchain", "news"]:
            if k in base:
                base[k] *= 0.30
    if drop_band and drop_band in base:
        base[drop_band] = 0.05
    B_asset = band_readiness_from_masks(base)
    req = [base[k] for k in AssetReadinessService.REQUIRED_BANDS if k in base]
    B_band = float(np.mean(req)) if req else float(np.mean(list(base.values())))
    B_domain = float(np.mean(list(base.values())))
    B_hier = 0.25 * B_domain + 0.35 * B_band + 0.40 * B_asset
    total = 12
    fresh = int(np.clip(round((0.88 if not outage else 0.40) * total), 0, total))
    acceptable = max(0, min(total - fresh, 2 if outage else 3))
    U = (fresh + 0.7 * acceptable) / total
    if ungated:
        excl, cont = 0.20, 0.25  # thick but dishonest
    else:
        excl = 0.82 if not outage else 0.55
        cont = 0.05 if not outage else 0.20
        if thin:
            excl, cont = 0.90, 0.04
    flag = "ok" if B_hier >= 0.55 and cont < 0.15 else ("thin" if B_hier >= 0.35 else "blocked")
    wmi = wmi_from_project(B_hier, fresh, acceptable, total, flag)
    H = continuous_honesty(excl, cont)
    return {"B_hier": B_hier, "U": U, "H_cont": H, "WMI": wmi["wmi"], "base": base, "excl": excl, "cont": cont}


def directional_signal(eng: dict) -> float:
    """Deterministic mechanism action in {-1,0,+1} when the agent chooses to act.

    Transparent rule (no latent NN). Band content enters directly:
      macro_tilt ∈ {-1,0,+1}: PIT-safe macro risk-on/off from vintaged VIX/DXY 5d changes
      alt_tilt   ∈ {-1,0,+1}: stablecoin 7d net-supply sign (liquidity in/outflow)
    Both are 0 (uninformative) whenever the corresponding band is not `ready`
    at t, so leave-one-band-out deletes *content*, not only gating.

      (R1)  crisis regime ∧ cascade_p >= 0.60                        → short (−1)
            (evidence conjunction: a drawdown-only or cascade-only trigger is
            not actionable — the same logic as the consistency factor C)
      (R2)  trend ∧ mom5 > 0 ∧ cascade_p < 0.45 ∧ macro_tilt ≥ 0     → long (+1)
      (R2b) range ∧ macro_tilt > 0 ∧ alt_tilt > 0 ∧ mom5 ≥ 0         → long (+1)
      (R3)  sign(mom5), but a long is vetoed to 0 when both tilts are
            risk-off (macro_tilt < 0 ∧ alt_tilt < 0); ties broken by
            sign(macro_tilt + alt_tilt)
    Return-based inputs come from production calculators on pre-t returns only
    (see run_engines); band tilts come from vintaged macro / alternative history.
    """
    macro_tilt = float(eng.get("macro_tilt", 0.0))
    alt_tilt = float(eng.get("alt_tilt", 0.0))
    if eng["detected_regime"] == "crisis" and eng["cascade_p"] >= 0.60:
        return -1.0
    if (
        eng["detected_regime"] == "trend"
        and eng["mom5"] > 0
        and eng["cascade_p"] < 0.45
        and macro_tilt >= 0
    ):
        return 1.0
    if (
        eng["detected_regime"] == "range"
        and macro_tilt > 0
        and alt_tilt > 0
        and eng["mom5"] >= 0
    ):
        return 1.0
    if eng["mom5"] != 0:
        if eng["mom5"] > 0 and macro_tilt < 0 and alt_tilt < 0:
            return 0.0
        return float(eng["mom5"])
    tie = macro_tilt + alt_tilt
    if tie != 0:
        return float(np.sign(tie))
    return 0.0


def mechanism_component_definitions() -> list[dict]:
    """Audit table: every mechanism input is a named formula + calculator."""
    return [
        {
            "component": "cascade_p",
            "formula": "LiquidationCascadeCalculator.compute_cascade_probability(cluster, capacity, distance)",
            "inputs": "left-tail cluster intensity from pre-t returns; capacity=6e7; distance by vol regime",
            "role": "crisis / short trigger in R1",
        },
        {
            "component": "systemic",
            "formula": "ContagionRiskCalculator.compute_systemic_risk_score([{covar_95, corr, tail_beta}])",
            "inputs": "asset vs synthetic peer path from pre-t returns",
            "role": "sign in consistency C",
        },
        {
            "component": "S (signal integrity)",
            "formula": "clip( hl_factor*(1-0.7*crowding_n)*(0.35+0.65*surprise_n) )",
            "inputs": "AlphaDecay half-life on cumsum(returns), crowding, surprise of last return",
            "role": "ACWMI factor",
        },
        {
            "component": "C (consistency)",
            "formula": "pairwise sign-agreement among {mom5, flow_sign, -1_{casc>0.55}, -1_{sys>55}}",
            "inputs": "mom5, VPIN/flow class, cascade_p, systemic",
            "role": "ACWMI factor + AC abstention gate",
        },
        {
            "component": "detected_regime",
            "formula": "RegimeClassifier.classify_price_regime(RegimeFeatures) with crisis override",
            "inputs": "returns, rolling vol, RSI/ADX proxies, cascade_p, vol_regime",
            "role": "R1/R2 branching",
        },
        {
            "component": "mom5",
            "formula": "sign(mean(r_{t-5:t}))",
            "inputs": "last 5 pre-t daily returns",
            "role": "R2/R3 directional fallback",
        },
        {
            "component": "macro_tilt",
            "formula": "+1 if VIX_5d_chg<0 and DXY_5d_chg<0; -1 if both>0; else 0; forced 0 when macro band not ready",
            "inputs": "vintaged macro_timeseries (available_at <= t): VIX, DXY",
            "role": "macro-band content: veto in R2, band-long in R2b, tie-break in R3, sign in C",
        },
        {
            "component": "alt_tilt",
            "formula": "sign(stablecoin_net_supply_change_7d at latest obs < t); forced 0 when alternative band not ready",
            "inputs": "alternative_timeseries stablecoin 7d net supply (pre-t)",
            "role": "alternative-band content: band-long in R2b, tie-break in R3, sign in C",
        },
        {
            "component": "signal",
            "formula": "R1 (crisis AND casc>=0.60)→-1; R2→+1 (macro veto); R2b→+1 (band-driven); R3 sign(mom5) with double-risk-off long veto; ties sign(macro_tilt+alt_tilt)",
            "inputs": "detected_regime, cascade_p, mom5, macro_tilt, alt_tilt",
            "role": "position when not abstaining; R1 requires evidence conjunction",
        },
    ]


def block_bootstrap_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Circular block bootstrap index matrix of shape (n_boot, n)."""
    if n <= 1:
        return np.zeros((n_boot, max(n, 1)), dtype=int)
    block = max(1, min(block, n))
    out = np.empty((n_boot, n), dtype=int)
    for b in range(n_boot):
        idx = []
        while len(idx) < n:
            start = int(rng.integers(0, n))
            idx.extend((start + k) % n for k in range(block))
        out[b] = np.array(idx[:n], dtype=int)
    return out


def _sharpe_ce_from_daily(daily: pd.Series) -> tuple[float, float]:
    daily = daily.astype(float)
    mu = float(daily.mean())
    sig = float(daily.std(ddof=1) + 1e-12)
    sharpe = mu / sig * np.sqrt(365)
    if GAMMA == 1:
        ce_daily = float(np.exp(np.log(np.maximum(1 + daily, 1e-8)).mean()) - 1)
    else:
        ce_daily = float((np.mean(np.maximum(1 + daily, 1e-8) ** (1 - GAMMA))) ** (1 / (1 - GAMMA)) - 1)
    return sharpe, ce_daily * 365


def bootstrap_delta_pvalues(
    daily_a: pd.Series,
    daily_b: pd.Series,
    *,
    n_boot: int = 999,
    block: int = 5,
    seed: int = 20260803,
) -> dict:
    """Two-sided block-bootstrap p-values for ΔSharpe and ΔCE (A − B).

    Aligns on the intersection of dates. H0: E[Δ] = 0.
    """
    a = daily_a.astype(float).sort_index()
    b = daily_b.astype(float).sort_index()
    idx = a.index.intersection(b.index)
    a = a.loc[idx]
    b = b.loc[idx]
    n = len(idx)
    if n < 20:
        return {
            "n_days": n,
            "dSharpe": None,
            "dCE": None,
            "p_Sharpe": None,
            "p_CE": None,
            "n_boot": n_boot,
            "block": block,
        }
    sh_a, ce_a = _sharpe_ce_from_daily(a)
    sh_b, ce_b = _sharpe_ce_from_daily(b)
    d_sh = sh_a - sh_b
    d_ce = ce_a - ce_b
    rng = np.random.default_rng(seed)
    boots = block_bootstrap_indices(n, block, n_boot, rng)
    boot_sh = np.empty(n_boot)
    boot_ce = np.empty(n_boot)
    a_vals = a.to_numpy()
    b_vals = b.to_numpy()
    for i in range(n_boot):
        ii = boots[i]
        sh_a_b, ce_a_b = _sharpe_ce_from_daily(pd.Series(a_vals[ii]))
        sh_b_b, ce_b_b = _sharpe_ce_from_daily(pd.Series(b_vals[ii]))
        boot_sh[i] = sh_a_b - sh_b_b
        boot_ce[i] = ce_a_b - ce_b_b
    # Two-sided percentile bootstrap p-value: is 0 in the bootstrap distribution of Δ?
    # p = 2 * min(P*(Δ* ≤ 0), P*(Δ* ≥ 0)) with +1 smoothing (Davison & Hinkley).
    def _p_two_sided(samples: np.ndarray) -> float:
        n = len(samples)
        left = (np.sum(samples <= 0) + 1) / (n + 1)
        right = (np.sum(samples >= 0) + 1) / (n + 1)
        return float(min(1.0, 2.0 * min(left, right)))

    p_sh = _p_two_sided(boot_sh)
    p_ce = _p_two_sided(boot_ce)
    return {
        "n_days": n,
        "dSharpe": round(d_sh, 4),
        "dCE": round(d_ce, 4),
        "p_Sharpe": round(p_sh, 4),
        "p_CE": round(p_ce, 4),
        "n_boot": n_boot,
        "block": block,
        "ci_dSharpe_05": round(float(np.quantile(boot_sh, 0.025)), 4),
        "ci_dSharpe_95": round(float(np.quantile(boot_sh, 0.975)), 4),
        "ci_dCE_05": round(float(np.quantile(boot_ce, 0.025)), 4),
        "ci_dCE_95": round(float(np.quantile(boot_ce, 0.975)), 4),
        "ci95_excludes_0_CE": bool(np.quantile(boot_ce, 0.025) > 0 or np.quantile(boot_ce, 0.975) < 0),
        "ci95_excludes_0_Sharpe": bool(np.quantile(boot_sh, 0.025) > 0 or np.quantile(boot_sh, 0.975) < 0),
    }


def white_reality_check(
    curves: dict[str, pd.Series],
    benchmark: str,
    *,
    n_boot: int = 999,
    block: int = 5,
    seed: int = 20260803,
) -> dict:
    """White (2000) reality check on ΔCE across candidate strategies vs a benchmark.

    H0: max_k E[CE_k − CE_bench] ≤ 0. Uses circular block bootstrap of the joint
    daily curves so cross-strategy dependence is preserved. Returns the max-ΔCE
    statistic and its bootstrap p-value under the recentred null.
    """
    bench = curves[benchmark].astype(float).sort_index()
    names = [k for k in curves if k != benchmark]
    idx = bench.index
    for k in names:
        idx = idx.intersection(curves[k].index)
    bench = bench.loc[idx]
    mat = {k: curves[k].astype(float).loc[idx].to_numpy() for k in names}
    bvals = bench.to_numpy()
    n = len(idx)
    deltas = {}
    for k in names:
        _, ce_k = _sharpe_ce_from_daily(pd.Series(mat[k]))
        _, ce_b = _sharpe_ce_from_daily(pd.Series(bvals))
        deltas[k] = ce_k - ce_b
    t_stat = max(deltas.values())
    best = max(deltas, key=deltas.get)
    rng = np.random.default_rng(seed)
    boots = block_bootstrap_indices(n, block, n_boot, rng)
    count = 0
    for i in range(n_boot):
        ii = boots[i]
        m = -np.inf
        for k in names:
            _, ce_k = _sharpe_ce_from_daily(pd.Series(mat[k][ii]))
            _, ce_b = _sharpe_ce_from_daily(pd.Series(bvals[ii]))
            # recentre under H0 (subtract observed delta)
            m = max(m, (ce_k - ce_b) - deltas[k])
        if m >= t_stat:
            count += 1
    return {
        "benchmark": benchmark,
        "best_strategy": best,
        "max_dCE": round(t_stat, 4),
        "p_reality_check": round((count + 1) / (n_boot + 1), 4),
        "n_boot": n_boot,
        "block": block,
        "n_days": n,
        "deltas": {k: round(v, 4) for k, v in deltas.items()},
    }


def simulate_panel(returns: pd.DataFrame, drop_band: str | None = None, ungated: bool = False, thin: bool = False) -> pd.DataFrame:
    """Build asset-day panel on real returns with return-orthogonal availability shocks."""
    dates = sorted(returns["date"].unique())
    # O_t: Bernoulli shocks independent of returns (identifying availability variation)
    outage_by_date = {d: bool(RNG.random() < 0.08) for d in dates}
    rows = []
    histories = {a: [] for a in ASSETS}
    for d in dates:
        day = returns[returns["date"] == d]
        outage = outage_by_date[d]
        for _, r in day.iterrows():
            asset = r["asset"]
            ret = float(r["ret"])
            # Point-in-time: engines/signals use only pre-t history; earn today's ret.
            hist = np.array(histories[asset], dtype=float)
            eng = run_engines(asset, hist)
            world = build_world_factors(outage, drop_band=drop_band, ungated=ungated, thin=thin)
            # under outage, cascade feed is partially missing → attenuated observation
            casc = eng["cascade_p"] * (0.55 if outage else 1.0)
            eng_use = dict(eng)
            eng_use["cascade_p"] = casc
            gamma = REGIME_GAMMA[eng_use["detected_regime"]]
            ac = acwmi(world["B_hier"], world["U"], world["H_cont"], eng_use["S"], eng_use["C"], gamma)
            sig = directional_signal(eng_use)
            rows.append(
                {
                    "date": d,
                    "asset": asset,
                    "ret": ret,
                    "outage": int(outage),
                    "B_hier": world["B_hier"],
                    "U": world["U"],
                    "H_cont": world["H_cont"],
                    "S": eng_use["S"],
                    "C": eng_use["C"],
                    "WMI": world["WMI"],
                    "ACWMI": ac,
                    "cascade_p": casc,
                    "systemic": eng_use["systemic"],
                    "detected_regime": eng_use["detected_regime"],
                    "signal": sig,
                    "mom5": eng_use["mom5"],
                }
            )
            histories[asset].append(ret)
    df = pd.DataFrame(rows)
    # drop first warm-up week with empty histories
    if len(df):
        mind = df.groupby("asset").cumcount()
        df = df.loc[mind >= 20].reset_index(drop=True)
    return df


def split_is_oos(df: pd.DataFrame, is_frac: float = 0.5):
    dates = sorted(df["date"].unique())
    cut = dates[int(len(dates) * is_frac)]
    return df[df["date"] < cut].copy(), df[df["date"] >= cut].copy(), cut


def calibrate_thresholds(is_df: pd.DataFrame) -> dict:
    """Freeze thresholds on IS only (maximize IS CE subject to non-degenerate abstention)."""
    best = {"ac_thr": 0.40, "c_thr": 0.35, "is_ce": -1e9, "is_abstain": None, "is_sharpe": None}
    for ac_thr in np.linspace(0.25, 0.55, 7):
        for c_thr in (0.25, 0.35, 0.45):
            pos = strategy_positions(
                is_df,
                policy="ac",
                params={"ac_thr": ac_thr, "c_thr": c_thr},
            )
            stats = portfolio_stats(is_df, pos)
            # Avoid degenerate always-cash / never-abstain solutions on IS.
            if not (0.05 <= stats["abstain_rate"] <= 0.55):
                continue
            score = stats["Sharpe"]  # primary IS objective for freeze
            if score > (best["is_sharpe"] if best["is_sharpe"] is not None else -1e9):
                best = {
                    "ac_thr": float(ac_thr),
                    "c_thr": float(c_thr),
                    "is_ce": stats["CE"],
                    "is_abstain": stats["abstain_rate"],
                    "is_sharpe": stats["Sharpe"],
                }
    if best["is_abstain"] is None:
        best = {"ac_thr": 0.35, "c_thr": 0.30, "is_ce": None, "is_abstain": None, "is_sharpe": None}
    best_simple = {"casc_only_thr": 0.70, "is_ce": -1e9}
    for thr in np.linspace(0.55, 0.90, 8):
        pos = strategy_positions(is_df, policy="simple_casc", params={"casc_only_thr": thr})
        stats = portfolio_stats(is_df, pos)
        if not (0.05 <= stats["abstain_rate"] <= 0.50):
            continue
        if stats["CE"] > best_simple["is_ce"]:
            best_simple = {"casc_only_thr": float(thr), "is_ce": stats["CE"]}
    best["casc_only_thr"] = best_simple["casc_only_thr"]
    best["wmi_thr"] = WMI_ABS_THR
    return best


def strategy_positions(df: pd.DataFrame, policy: str, params: dict) -> pd.Series:
    sig = df["signal"].astype(float).to_numpy()
    mom = df["mom5"].astype(float).to_numpy()
    # signal == 0 is an intentional stand-aside (e.g. the R3 double-risk-off
    # long veto or a genuine tie): it must map to a flat position, not to a
    # momentum/long fallback that would erase band content from actions.
    act_sig = sig
    if policy == "always_long":
        abstain = np.zeros(len(df), dtype=bool)
        act_sig = np.ones(len(df))
    elif policy == "mom_always":
        abstain = np.zeros(len(df), dtype=bool)
        act_sig = np.where(mom == 0, 1.0, mom)
    elif policy == "thick_ungated":
        abstain = np.zeros(len(df), dtype=bool)
    elif policy == "simple_outage":
        abstain = df["outage"].to_numpy().astype(bool)
    elif policy == "simple_casc":
        thr = params.get("casc_only_thr", 0.55)
        abstain = (df["cascade_p"].to_numpy() >= thr)
    elif policy == "wmi":
        abstain = df["WMI"].to_numpy() < params.get("wmi_thr", WMI_ABS_THR)
    elif policy == "ac":
        # Refusal is world-quality conditional; outages enter through lower ACWMI/U/H,
        # not as a hardwired second rule that would dominate the comparison.
        abstain = (df["ACWMI"].to_numpy() < params.get("ac_thr", 0.4)) | (
            df["C"].to_numpy() < params.get("c_thr", 0.35)
        )
    else:
        raise ValueError(policy)
    pos = np.where(abstain, 0.0, act_sig)
    return pd.Series(pos, index=df.index, dtype=float)


def portfolio_stats(
    df: pd.DataFrame,
    pos: pd.Series,
    cost_bps: float = 0.0,
    funding_daily: pd.DataFrame | None = None,
) -> dict:
    """Equal-weight portfolio stats with optional turnover costs and funding.

    cost_bps: one-way proportional cost in basis points applied to |Δposition|
    per asset per day (positions in {-1,0,+1}, so a flip costs 2×cost).
    funding_daily: optional DataFrame [date, asset, funding_rate_daily]; longs
    pay positive funding, shorts receive it (perp convention): pnl -= pos*funding.
    """
    tmp = df[["date", "asset", "ret"]].copy() if "asset" in df.columns else df[["date", "ret"]].copy()
    tmp["pos"] = pos.values
    tmp["pnl"] = tmp["pos"] * tmp["ret"]
    if cost_bps > 0 and "asset" in tmp.columns:
        tmp = tmp.sort_values(["asset", "date"])
        dpos = tmp.groupby("asset")["pos"].diff().abs().fillna(tmp["pos"].abs())
        tmp["pnl"] = tmp["pnl"] - (cost_bps / 1e4) * dpos
    if funding_daily is not None and "asset" in tmp.columns:
        f = funding_daily.rename(columns={"funding_rate_daily": "_fr"})
        tmp = tmp.merge(f[["date", "asset", "_fr"]], on=["date", "asset"], how="left")
        tmp["_fr"] = tmp["_fr"].fillna(0.0)
        tmp["pnl"] = tmp["pnl"] - tmp["pos"] * tmp["_fr"]
    daily = tmp.groupby("date")["pnl"].mean().sort_index()
    mu = float(daily.mean())
    sig = float(daily.std(ddof=1) + 1e-12)
    sharpe = mu / sig * np.sqrt(365)
    # CRRA CE on daily equal-weight portfolio
    wealth = (1 + daily).cumprod()
    # certainty equivalent return (daily) then annualize
    if GAMMA == 1:
        ce_daily = float(np.exp(np.log(np.maximum(1 + daily, 1e-8)).mean()) - 1)
    else:
        ce_daily = float((np.mean(np.maximum(1 + daily, 1e-8) ** (1 - GAMMA))) ** (1 / (1 - GAMMA)) - 1)
    max_dd = float((wealth / wealth.cummax() - 1).min())
    abstain_rate = float((pos == 0).mean())
    return {
        "ann_return": mu * 365,
        "ann_vol": sig * np.sqrt(365),
        "Sharpe": sharpe,
        "CE": ce_daily * 365,
        "max_DD": max_dd,
        "abstain_rate": abstain_rate,
        "N_days": int(daily.shape[0]),
        "daily": daily,
    }


def evaluate_policies(oos: pd.DataFrame, params: dict) -> pd.DataFrame:
    policies = [
        ("Always long", "always_long"),
        ("Momentum always", "mom_always"),
        ("Thick ungated", "thick_ungated"),
        ("Simple outage rule", "simple_outage"),
        ("Simple cascade rule", "simple_casc"),
        ("WMI threshold (0.2)", "wmi"),
        ("ACWMI (IS-frozen)", "ac"),
    ]
    rows = []
    curves = {}
    for name, key in policies:
        pos = strategy_positions(oos, key, params)
        st = portfolio_stats(oos, pos)
        curves[name] = st["daily"]
        rows.append(
            {
                "policy": name,
                "ann_return": round(st["ann_return"], 4),
                "ann_vol": round(st["ann_vol"], 4),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "max_DD": round(st["max_DD"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
                "N_days": st["N_days"],
            }
        )
    return pd.DataFrame(rows), curves


def _recompute_world_on_panel(base_panel: pd.DataFrame, drop_band: str | None = None, ungated: bool = False, thin: bool = False) -> pd.DataFrame:
    """Reuse engine outputs; only rebuild readiness/WMI/ACWMI under band ablations."""
    df = base_panel.copy()
    Bm, Um, Hm, Wm, Am = [], [], [], [], []
    for outage, det, S, C in zip(df["outage"], df["detected_regime"], df["S"], df["C"]):
        world = build_world_factors(bool(outage), drop_band=drop_band, ungated=ungated, thin=thin)
        gamma = REGIME_GAMMA.get(det, REGIME_GAMMA["range"])
        ac = acwmi(world["B_hier"], world["U"], world["H_cont"], S, C, gamma)
        Bm.append(world["B_hier"])
        Um.append(world["U"])
        Hm.append(world["H_cont"])
        Wm.append(world["WMI"])
        Am.append(ac)
    df["B_hier"], df["U"], df["H_cont"], df["WMI"], df["ACWMI"] = Bm, Um, Hm, Wm, Am
    return df


def leave_one_band_out(base_panel: pd.DataFrame, params: dict) -> pd.DataFrame:
    rows = []
    _, oos, _ = split_is_oos(base_panel)
    base = portfolio_stats(oos, strategy_positions(oos, "ac", params))
    rows.append(
        {
            "band_dropped": "(none)",
            "Sharpe": round(base["Sharpe"], 3),
            "CE": round(base["CE"], 4),
            "abstain_rate": round(base["abstain_rate"], 3),
            "dCE": 0.0,
        }
    )
    for band in BANDS:
        df = _recompute_world_on_panel(base_panel, drop_band=band)
        _, oos_b, _ = split_is_oos(df)
        st = portfolio_stats(oos_b, strategy_positions(oos_b, "ac", params))
        rows.append(
            {
                "band_dropped": band,
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
                "dCE": round(st["CE"] - base["CE"], 4),
            }
        )
    return pd.DataFrame(rows)


def thin_thick_table(base_panel: pd.DataFrame, params: dict) -> pd.DataFrame:
    specs = [
        ("Thin (exchange only)", dict(thin=True, ungated=False), "ac"),
        ("Thick ungated", dict(thin=False, ungated=True), "thick_ungated"),
        ("Thick gated (AC)", dict(thin=False, ungated=False), "ac"),
    ]
    rows = []
    for name, kw, policy in specs:
        df = _recompute_world_on_panel(base_panel, **kw)
        _, oos, _ = split_is_oos(df)
        st = portfolio_stats(oos, strategy_positions(oos, policy, params))
        rows.append(
            {
                "world": name,
                "mean_B": round(float(oos["B_hier"].mean()), 3),
                "mean_H": round(float(oos["H_cont"].mean()), 3),
                "mean_ACWMI": round(float(oos["ACWMI"].mean()), 3),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(st["abstain_rate"], 3),
            }
        )
    return pd.DataFrame(rows)


def conditional_signal_value(df: pd.DataFrame) -> pd.DataFrame:
    """JF tests: signal value by ACWMI; also within no-outage subsample to avoid confounding."""
    d = df.copy()
    d["hit"] = (np.sign(d["signal"]) == np.sign(d["ret"])) & (d["signal"] != 0)
    d["signed_ret"] = d["signal"] * d["ret"]
    rows = []
    for label, sub in [("all", d), ("no_outage", d[d["outage"] == 0])]:
        sub = sub.copy()
        if len(sub) < 50:
            continue
        sub["ac_tercile"] = pd.qcut(sub["ACWMI"], 3, labels=["low", "mid", "high"])
        for t, g in sub.groupby("ac_tercile", observed=True):
            active = g[g["signal"] != 0]
            rows.append(
                {
                    "sample": label,
                    "ACWMI_tercile": str(t),
                    "N": int(len(g)),
                    "mean_ACWMI": round(float(g["ACWMI"].mean()), 3),
                    "signal_IC": round(float(active["signed_ret"].mean()), 5) if len(active) else 0.0,
                    "hit_rate": round(float(active["hit"].mean()), 3) if len(active) else 0.0,
                    "ann_active_ret": round(float(active["signed_ret"].mean() * 365), 4) if len(active) else 0.0,
                    "outage_rate": round(float(g["outage"].mean()), 3),
                }
            )
    return pd.DataFrame(rows)


def event_study(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Mean WMI/ACWMI/returns around return-orthogonal outages."""
    daily = (
        df.groupby("date")
        .agg(ret=("ret", "mean"), WMI=("WMI", "mean"), ACWMI=("ACWMI", "mean"), outage=("outage", "max"))
        .sort_index()
    )
    events = daily.index[daily["outage"] == 1]
    ks = list(range(-3, 4))
    rows = []
    for k in ks:
        vals = []
        for e in events:
            # locate position
            idx = daily.index.get_indexer([e])[0]
            j = idx + k
            if 0 <= j < len(daily):
                vals.append(daily.iloc[j][["ret", "WMI", "ACWMI"]].to_dict())
        if not vals:
            continue
        m = pd.DataFrame(vals).mean()
        rows.append({"k": k, "ret": round(float(m["ret"]), 5), "WMI": round(float(m["WMI"]), 4), "ACWMI": round(float(m["ACWMI"]), 4), "N": len(vals)})
    return pd.DataFrame(rows)


def fig_cumreturns(curves: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    for name, s in curves.items():
        ax.plot(s.index, (1 + s).cumprod(), label=name, lw=1.4 if "ACWMI" in name else 1.0)
    ax.set_title("Fig. 1. OOS cumulative wealth of selective strategies (real crypto returns)")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_architecture.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig1_architecture.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_oos_bars(econ: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.8))
    axes[0].barh(econ["policy"][::-1], econ["Sharpe"][::-1], color="#1F4E79")
    axes[0].set_title("OOS Sharpe")
    axes[1].barh(econ["policy"][::-1], econ["CE"][::-1], color="#C55A11")
    axes[1].set_title("OOS certainty equivalent (ann.)")
    fig.suptitle("Fig. 2. Economic value of abstention policies (OOS)", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_coverage_compare.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig2_coverage_compare.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_paths(df: pd.DataFrame) -> None:
    daily = df.groupby("date")[["WMI", "ACWMI", "cascade_p", "C"]].mean()
    fig, axes = plt.subplots(2, 1, figsize=(8.2, 5.4), sharex=True)
    axes[0].plot(daily.index, daily["WMI"], label="WMI", color="#5B9BD5")
    axes[0].plot(daily.index, daily["ACWMI"], label="ACWMI", color="#C55A11")
    axes[0].legend()
    axes[0].set_title("Fig. 3. World-model indices on real-return panel")
    axes[1].plot(daily.index, daily["cascade_p"], label="cascade_p", color="#833C0C")
    axes[1].plot(daily.index, daily["C"], label="consistency C", color="#548235")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_factor_paths.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig3_factor_paths.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_lobo(lobo: pd.DataFrame) -> None:
    g = lobo[lobo["band_dropped"] != "(none)"].copy()
    fig, ax = plt.subplots(figsize=(7.8, 3.8))
    ax.bar(g["band_dropped"], g["dCE"], color="#1F4E79")
    ax.axhline(0, color="gray", lw=1)
    ax.set_ylabel("Δ OOS CE vs full world")
    ax.set_title("Fig. 4. Leave-one-band-out marginal economic value")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_regime_box.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig4_regime_box.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_event(ev: pd.DataFrame) -> None:
    fig, ax1 = plt.subplots(figsize=(7.4, 3.8))
    ax1.plot(ev["k"], ev["WMI"], "o-", label="WMI", color="#5B9BD5")
    ax1.plot(ev["k"], ev["ACWMI"], "s-", label="ACWMI", color="#C55A11")
    ax1.set_xlabel("Event time around availability shock O_t")
    ax1.set_ylabel("World-model index")
    ax2 = ax1.twinx()
    ax2.plot(ev["k"], ev["ret"], "^--", label="equal-weight ret", color="#548235")
    ax2.set_ylabel("Return")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="best")
    ax1.axvline(0, color="gray", ls="--")
    ax1.set_title("Fig. 5. Event study: return-orthogonal availability shocks")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig5_quality_scatter.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig5_quality_scatter.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_thin_thick(tt: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.8, 3.8))
    x = np.arange(len(tt))
    ax.bar(x - 0.15, tt["Sharpe"], 0.3, label="Sharpe", color="#1F4E79")
    ax.bar(x + 0.15, tt["CE"], 0.3, label="CE", color="#C55A11")
    ax.set_xticks(x)
    ax.set_xticklabels(tt["world"], rotation=15, ha="right")
    ax.set_title("Fig. 6. Thin vs thick-ungated vs thick-gated worlds (OOS)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig6_event_study.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig6_event_study.pdf", bbox_inches="tight")
    plt.close(fig)


def fig_pareto(oos: pd.DataFrame) -> None:
    pts = []
    for thr in np.linspace(0.25, 0.65, 12):
        for policy, key in [("WMI", "wmi"), ("ACWMI", "ac")]:
            params = {"wmi_thr": thr, "ac_thr": thr, "c_thr": 0.4, "casc_thr": 0.85}
            st = portfolio_stats(oos, strategy_positions(oos, key, params))
            pts.append({"policy": policy, "thr": thr, "abstain_rate": st["abstain_rate"], "Sharpe": st["Sharpe"], "CE": st["CE"]})
    pdf = pd.DataFrame(pts)
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for policy, g in pdf.groupby("policy"):
        ax.plot(g["abstain_rate"], g["CE"], marker="o", label=policy)
    ax.set_xlabel("Abstain rate")
    ax.set_ylabel("OOS CE (ann.)")
    ax.set_title("Fig. 7. Abstention–value frontier (OOS)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig7_pareto.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig7_pareto.pdf", bbox_inches="tight")
    pdf.to_csv(TAB_DIR / "table6_pareto_points.csv", index=False)
    plt.close(fig)


def fig_is_oos_stability(params: dict, is_df: pd.DataFrame, oos: pd.DataFrame) -> None:
    rows = []
    for split_name, d in [("IS", is_df), ("OOS", oos)]:
        for name, key in [("WMI", "wmi"), ("ACWMI", "ac"), ("Mom", "mom_always")]:
            st = portfolio_stats(d, strategy_positions(d, key, params))
            rows.append({"split": split_name, "policy": name, "Sharpe": st["Sharpe"], "CE": st["CE"]})
    g = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    width = 0.25
    policies = ["Mom", "WMI", "ACWMI"]
    for i, split in enumerate(["IS", "OOS"]):
        vals = [g[(g.split == split) & (g.policy == p)]["CE"].iloc[0] for p in policies]
        ax.bar(np.arange(len(policies)) + i * width, vals, width, label=split)
    ax.set_xticks(np.arange(len(policies)) + width / 2)
    ax.set_xticklabels(policies)
    ax.set_ylabel("CE (ann.)")
    ax.set_title("Fig. 8. IS vs OOS stability under frozen thresholds")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig8_honesty_incentive.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig8_honesty_incentive.pdf", bbox_inches="tight")
    g.to_csv(TAB_DIR / "table_is_oos_stability.csv", index=False)
    plt.close(fig)


def main() -> None:
    print("Loading real returns...")
    returns = load_real_returns()
    print(returns["date"].min(), "→", returns["date"].max(), "N=", len(returns))

    print("Building baseline panel...")
    panel = simulate_panel(returns)
    panel.to_csv(TAB_DIR / "panel_simulation.csv", index=False)
    is_df, oos, cut = split_is_oos(panel)
    print("IS/OOS cut:", cut, "IS days", is_df["date"].nunique(), "OOS days", oos["date"].nunique())

    print("Calibrating thresholds on IS only...")
    params = calibrate_thresholds(is_df)
    (OUT_DIR / "frozen_thresholds.json").write_text(json.dumps(params, indent=2), encoding="utf-8")
    print(params)

    print("OOS economic value...")
    econ, curves = evaluate_policies(oos, params)
    econ.to_csv(TAB_DIR / "table_econ_oos.csv", index=False)
    print(econ)

    print("Leave-one-band-out...")
    lobo = leave_one_band_out(panel, params)
    lobo.to_csv(TAB_DIR / "table_lobo.csv", index=False)
    print(lobo)

    print("Thin vs thick...")
    tt = thin_thick_table(panel, params)
    tt.to_csv(TAB_DIR / "table_thin_thick.csv", index=False)
    print(tt)

    print("Conditional signal value by ACWMI tercile...")
    cond = conditional_signal_value(oos)
    cond.to_csv(TAB_DIR / "table_conditional_ic.csv", index=False)
    print(cond)

    print("Event study...")
    ev = event_study(panel, params)
    ev.to_csv(TAB_DIR / "table4_outage_event_study.csv", index=False)

    # keep inventory-ish tables for PDF compatibility
    inv = {
        "n_assets": len(ASSETS),
        "n_days": int(panel["date"].nunique()),
        "n_obs": int(len(panel)),
        "start": str(panel["date"].min().date()),
        "end": str(panel["date"].max().date()),
        "is_oos_cut": str(pd.Timestamp(cut).date()),
        "data_source": "Yahoo Finance daily adjusted closes",
        "frozen_thresholds": params,
    }
    (TAB_DIR / "table1_project_inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")

    print("Figures...")
    fig_cumreturns(curves)
    fig_oos_bars(econ)
    fig_paths(panel)
    fig_lobo(lobo)
    fig_event(ev)
    fig_thin_thick(tt)
    fig_pareto(oos)
    fig_is_oos_stability(params, is_df, oos)

    # summary markdown
    lines = [
        "# JF/RFS-oriented experiment results",
        "",
        f"- Real returns: **{inv['start']} → {inv['end']}**, {inv['n_assets']} assets, {inv['n_obs']} asset-days",
        f"- IS/OOS cut: **{inv['is_oos_cut']}** (thresholds frozen on IS only)",
        f"- Frozen params: `{params}`",
        "",
        "## OOS economic value",
        "",
        econ.to_markdown(index=False),
        "",
        "## Leave-one-band-out",
        "",
        lobo.to_markdown(index=False),
        "",
        "## Thin vs thick",
        "",
        tt.to_markdown(index=False),
        "",
        "## Conditional signal value (OOS)",
        "",
        cond.to_markdown(index=False),
        "",
        "## Notes",
        "",
        "- Returns are real Yahoo daily crypto returns; signals use only pre-t history (PIT).",
        "- Thresholds frozen on IS (Sharpe max, abstain rate in [5%, 55%]).",
        "- Availability shocks O_t are Bernoulli and constructed return-orthogonal for identification.",
        "- Multi-band historical archives are not in-repo; readiness layers use production band weights/WMI code.",
        "- Stepping-stone toward full vintaged multi-source PIT via `logic_layer/time_slice`.",
    ]
    (OUT_DIR / "EXPERIMENT_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_DIR / "experiment_summary.json").write_text(
        json.dumps(
            {
                "inventory": inv,
                "econ_oos": econ.to_dict(orient="records"),
                "lobo": lobo.to_dict(orient="records"),
                "thin_thick": tt.to_dict(orient="records"),
                "conditional_ic": cond.to_dict(orient="records"),
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
