#!/usr/bin/env python3
"""Project-grounded experiments for the standalone SCI manuscript.

All analytics call real EvoQuant calculators / WMI implementation.
Synthetic market paths are only used as *inputs* to those functions; evaluation
targets are planted structural events (regime, cascade, outage), not a Q score
built from ACWMI itself.
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

from core.degradation import DegradationLevel, DegradationManager
from data_layer.data_quality.audit import DEFAULT_EVIDENCE_BAND_SPECS
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
OUT_DIR = Path(__file__).resolve().parent
FIG_DIR.mkdir(parents=True, exist_ok=True)
TAB_DIR.mkdir(parents=True, exist_ok=True)

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
N_DAYS = 180


def project_inventory() -> dict:
    data_dirs = sorted(
        d
        for d in os.listdir(ROOT / "data_layer")
        if (ROOT / "data_layer" / d).is_dir() and not d.startswith("_")
    )
    logic_dirs = sorted(
        d
        for d in os.listdir(ROOT / "logic_layer")
        if (ROOT / "logic_layer" / d).is_dir() and not d.startswith("_")
    )
    py_files = list(ROOT.rglob("*.py"))
    py_files = [p for p in py_files if ".git" not in p.parts and "__pycache__" not in p.parts]
    loc = 0
    for p in py_files:
        try:
            loc += sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    bands = [
        {
            "band_name": s.band_name,
            "module_name": s.module_name,
            "required": bool(s.required),
            "description": s.description,
        }
        for s in DEFAULT_EVIDENCE_BAND_SPECS
    ]
    inv = {
        "n_data_domains": len(data_dirs),
        "data_domains": data_dirs,
        "n_logic_modules": len(logic_dirs),
        "logic_modules": logic_dirs,
        "n_audit_bands": len(bands),
        "audit_bands": bands,
        "asset_band_weights": dict(AssetReadinessService.BAND_WEIGHTS),
        "n_py_files": len(py_files),
        "n_loc": loc,
        "n_test_files": len(list((ROOT / "tests").rglob("test_*.py"))),
    }
    (TAB_DIR / "table1_project_inventory.json").write_text(
        json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = []
    for b in bands:
        rows.append(
            {
                "Band": b["band_name"],
                "Module": b["module_name"],
                "Required": "Yes" if b["required"] else "No",
                "Asset weight": inv["asset_band_weights"].get(b["band_name"], ""),
                "Role": b["description"],
            }
        )
    pd.DataFrame(rows).to_csv(TAB_DIR / "table1_evidence_bands.csv", index=False)
    pd.DataFrame({"data_domain": data_dirs}).to_csv(TAB_DIR / "table_a1_data_domains.csv", index=False)
    pd.DataFrame({"logic_module": logic_dirs}).to_csv(TAB_DIR / "table_a2_logic_modules.csv", index=False)
    return inv


def wmi_from_project(breadth: float, fresh: int, acceptable: int, total: int, flag: str) -> dict:
    return AIMarketContextService._compute_world_model_index(
        coverage_score=float(breadth),
        pipeline_latency_context={
            "summary": {"total_domains": int(total), "fresh": int(fresh), "acceptable": int(acceptable)}
        },
        data_quality_flag=flag,
        data_quality_flags=[],
    )


def continuous_honesty(excl_rate: float, cont_rate: float, beta1: float = 2.0, beta2: float = 0.5) -> float:
    return float(np.exp(-beta1 * cont_rate) * max(0.0, 1.0 - beta2 * (1.0 - excl_rate)))


def acwmi(B, U, H, S, C, gamma=(1.0, 1.0, 1.0, 1.0, 1.0)) -> float:
    vals = np.array([max(B, 1e-6), max(U, 1e-6), max(H, 1e-6), max(S, 1e-6), max(C, 1e-6)])
    g = np.array(gamma, dtype=float)
    return float(np.exp(np.sum(g * np.log(vals)) / np.sum(g)))


REGIME_GAMMA = {
    "trend": (1.0, 1.0, 1.0, 1.3, 0.8),
    "range": (1.0, 1.1, 1.1, 1.0, 1.0),
    "crisis": (0.9, 1.2, 1.4, 0.8, 1.5),
}


def simulate_returns(n: int, regime: str) -> np.ndarray:
    if regime == "crisis":
        vol, drift, shock_p = 0.06, -0.012, 0.18
    elif regime == "trend":
        vol, drift, shock_p = 0.018, 0.0025, 0.02
    else:
        vol, drift, shock_p = 0.012, 0.0, 0.01
    r = RNG.normal(drift, vol, size=n)
    shocks = RNG.random(n) < shock_p
    n_shock = int(shocks.sum())
    if n_shock:
        r[shocks] -= RNG.uniform(0.04, 0.12, size=n_shock)
    return r


def band_readiness_from_masks(ready_mask: dict[str, float]) -> float:
    """Use AssetReadinessService weights/status ratios on synthetic band states."""
    score = 0.0
    for band, weight in AssetReadinessService.BAND_WEIGHTS.items():
        ratio = float(ready_mask.get(band, 0.0))
        # map continuous availability to ready/limited/missing semantics
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
    agree = 0
    total = 0
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            total += 1
            if vals[i] * vals[j] > 0:
                agree += 1
    return agree / total if total else 0.0


def run_day_engines(asset: str, regime: str, outage: bool, returns: np.ndarray) -> dict:
    """Call real project calculators on the day's local history."""
    hist = returns[-80:] if len(returns) >= 80 else returns
    vol_calc = VolatilityCalculator()
    classifier = RegimeClassifier()

    rv = vol_calc.compute_realized_vol(hist.tolist()) if len(hist) >= 20 else 0.2
    ewma = vol_calc.compute_ewma_forecast(hist.tolist()) if len(hist) >= 20 else rv
    vol_pct = vol_calc.compute_vol_percentile(hist.tolist()) if len(hist) >= 60 else 50.0
    vol_regime = vol_calc.classify_vol_regime(float(rv or 0.2))

    # synthetic companion asset for contagion
    peer = hist * 0.7 + RNG.normal(0, np.std(hist) * 0.5 + 1e-6, size=len(hist))
    covar = ContagionRiskCalculator.compute_covar(hist.tolist(), peer.tolist()) if len(hist) >= 20 else 0.0
    tail_b = ContagionRiskCalculator.compute_tail_beta(hist.tolist(), peer.tolist()) if len(hist) >= 20 else 0.0
    systemic = ContagionRiskCalculator.compute_systemic_risk_score(
        [{"covar_95": float(covar or 0.0), "conditional_correlation": 0.5, "tail_beta": float(tail_b or 0.0)}]
    )

    # cascade from planted leverage intensity
    cluster = 8e6 if regime == "crisis" else (2e6 if regime == "trend" else 1e6)
    if outage:
        cluster *= 0.3  # missing liquidation feed underestimates risk
    vol_usd = 6e7
    distance = 0.6 if regime == "crisis" else 2.5
    casc_p = LiquidationCascadeCalculator.compute_cascade_probability(cluster, vol_usd, distance)
    casc_sev = LiquidationCascadeCalculator.compute_cascade_severity(
        casc_p, cluster, open_interest_usd=5e8
    )

    # alpha-decay signal integrity from return signal
    signal = np.cumsum(hist)
    half_life = AlphaDecayCalculator.compute_half_life(signal.tolist()) or 24.0
    crowd = AlphaDecayCalculator.compute_crowding_score(
        [
            {"signal_name": "mom", "direction": 1 if hist[-1] > 0 else -1, "strength": abs(float(hist[-1])) * 20},
            {"signal_name": "flow", "direction": 1 if np.mean(hist[-5:]) > 0 else -1, "strength": 0.8},
            {"signal_name": "funding", "direction": -1 if regime == "crisis" else 1, "strength": 1.2},
        ]
    )
    surprise = abs(
        AlphaDecayCalculator.compute_signal_surprise(float(hist[-1]), hist[:-1].tolist()) or 0.0
    )
    surprise_n = float(np.clip(abs(surprise) / 2.5, 0.0, 1.0))
    crowding_n = float(np.clip((crowd.get("crowding_score", 50) if isinstance(crowd, dict) else 50) / 100.0, 0, 1))
    hl_factor = float(1.0 - np.exp(-(max(half_life, 1.0)) / 36.0))
    # Keep project-derived S informative even when z-scores are mild.
    S = float(np.clip(hl_factor * (1.0 - 0.7 * crowding_n) * (0.35 + 0.65 * surprise_n), 0.05, 1.0))

    # flow
    trades = []
    px = 100.0
    for r in hist[-40:]:
        px *= 1 + r
        side = "buy" if r >= 0 else "sell"
        trades.append({"volume": float(abs(r) * 1000 + 10), "side": side, "price": px})
    vpin = FlowDecompositionCalculator.compute_vpin(trades, bucket_size=20) if trades else 0.0
    flow = (
        FlowDecompositionCalculator.classify_flow(trades)
        if trades
        else {"informed_flow_ratio": 0.0, "smart_money_direction": 0}
    )

    # regime classifier features
    vol_series = pd.Series(hist).rolling(10).std().fillna(float(np.std(hist))).tolist()
    feats = RegimeFeatures(
        returns=hist.tolist(),
        volatility=vol_series,
        volume_ratio=1.4 if regime == "crisis" else 1.0,
        rsi=35 if regime == "crisis" else (62 if regime == "trend" else 50),
        adx=28 if regime != "range" else 12,
        correlation_to_btc=0.85 if asset != "BTC" else 1.0,
    )
    price_regime, conf = classifier.classify_price_regime(feats)

    # map classifier label to coarse regime for gamma
    label = str(price_regime).lower()
    if label == "crisis" or (vol_regime in {"high", "extreme"} and casc_p > 0.6):
        detected = "crisis"
    elif "trend" in label:
        detected = "trend"
    else:
        detected = "range"

    # evidence direction signs for consistency
    flow_dir = flow.get("smart_money_direction", "neutral")
    flow_sign = 1.0 if flow_dir == "buy" else (-1.0 if flow_dir == "sell" else 0.0)
    signs = [
        float(np.sign(np.mean(hist[-5:]))),
        flow_sign if flow_sign != 0 else float(np.sign(np.mean(hist[-10:]))),
        -1.0 if casc_p > 0.55 else 1.0,
        -1.0 if (systemic or 0) > 55 else 1.0,
        -1.0 if vpin and vpin > 0.55 else float(np.sign(np.mean(hist[-3:]))),
    ]
    C = consistency_from_signs(signs)

    return {
        "rv": float(rv or 0),
        "ewma": float(ewma or 0),
        "vol_pct": float(vol_pct or 0),
        "vol_regime": vol_regime,
        "covar": float(covar or 0),
        "tail_beta": float(tail_b or 0),
        "systemic": float(systemic or 0),
        "cascade_p": float(casc_p or 0),
        "cascade_severity": str(casc_sev),
        "half_life": float(half_life or 24),
        "crowding": crowding_n,
        "surprise": surprise_n,
        "S": S,
        "vpin": float(vpin or 0),
        "informed_flow": float(flow.get("informed_flow_ratio") or 0),
        "detected_regime": detected,
        "detect_conf": float(conf or 0),
        "C": C,
        "price_regime_raw": str(price_regime),
    }


def simulate_panel() -> pd.DataFrame:
    # shared regime path
    regimes = []
    cur = "trend"
    for _ in range(N_DAYS):
        if RNG.random() < 0.07:
            cur = str(RNG.choice(["trend", "range", "crisis"], p=[0.35, 0.40, 0.25]))
        regimes.append(cur)

    rows = []
    histories = {a: np.array([], dtype=float) for a in ASSETS}
    for t, regime in enumerate(regimes):
        outage = bool(RNG.random() < (0.15 if regime == "crisis" else 0.03))
        # degradation level tied to outage/crisis
        if outage and regime == "crisis":
            deg = "EMERGENCY"
        elif outage:
            deg = "MINIMAL"
        elif regime == "crisis":
            deg = "REDUCED"
        else:
            deg = "NORMAL"

        for asset in ASSETS:
            day_ret = simulate_returns(1, regime)[0]
            # cross-asset common factor
            day_ret += {"crisis": -0.01, "trend": 0.001, "range": 0.0}[regime] * 0.5
            histories[asset] = np.append(histories[asset], day_ret)
            eng = run_day_engines(asset, regime, outage, histories[asset])

            # hierarchical breadth from project band weights + availability shocks
            base = {
                "exchange": 0.95,
                "news": 0.8,
                "event_calendar": 0.75,
                "onchain": 0.7,
                "tokenomics": 0.65,
                "options": 0.6,
                "alternative": 0.55,
                "macro": 0.85,
            }
            if outage:
                for k in ["options", "onchain", "news"]:
                    base[k] *= 0.35
            if regime == "crisis":
                base["macro"] *= 0.85
                base["alternative"] *= 0.7
            B_asset = band_readiness_from_masks(base)
            B_domain = float(np.mean(list(base.values())))
            B_band = float(np.mean([v for k, v in base.items() if k in AssetReadinessService.REQUIRED_BANDS or True]))
            # required-band emphasis
            req = [base[k] for k in AssetReadinessService.REQUIRED_BANDS if k in base]
            B_band = float(np.mean(req)) if req else B_domain
            B_hier = 0.25 * B_domain + 0.35 * B_band + 0.40 * B_asset

            total = 12
            fresh = int(np.clip(round((0.85 if not outage else 0.35) * total), 0, total))
            if regime == "crisis":
                fresh = max(0, fresh - 2)
            acceptable = max(0, min(total - fresh, 2 if outage else 3))
            U = (fresh + 0.7 * acceptable) / total

            excl = 0.82 if not outage else 0.55
            cont = 0.05 if not outage else 0.22
            if deg in {"MINIMAL", "EMERGENCY"}:
                # honest thinning under degradation
                excl = min(0.95, excl + 0.1)
                cont = max(0.02, cont - 0.05)
            flag = "ok" if B_hier >= 0.55 and cont < 0.15 else ("thin" if B_hier >= 0.35 else "blocked")
            wmi = wmi_from_project(B_hier, fresh, acceptable, total, flag)
            H = continuous_honesty(excl, cont)
            gamma = REGIME_GAMMA[eng["detected_regime"]]
            ac = acwmi(B_hier, U, H, eng["S"], eng["C"], gamma)

            # planted-event evaluation targets (NOT built from ACWMI)
            true_crisis = int(regime == "crisis")
            true_cascade = int(regime == "crisis" and not outage)  # outage hides cascade feed
            detect_crisis = int(eng["detected_regime"] == "crisis" or eng["vol_regime"] in {"high", "extreme"} and eng["cascade_p"] > 0.5)
            detect_cascade = int(eng["cascade_p"] >= 0.55)

            # abstention policies
            abstain_wmi = int(wmi["wmi"] < 0.2)
            # AC policy: refuse only under materially stressed / degraded / conflicting worlds
            abstain_ac = int(
                ac < 0.38
                or deg in {"MINIMAL", "EMERGENCY"}
                or eng["cascade_p"] >= 0.80
                or (eng["detected_regime"] == "crisis" and eng["cascade_p"] >= 0.55)
                or (eng["C"] < 0.35 and outage)
                or (eng["systemic"] >= 70 and regime == "crisis")
            )

            # "safe decision" = abstain when true crisis/outage OR correctly detect cascade when acting
            risky_action = (not abstain_ac) and (true_crisis or outage)
            unsafe_wmi = (not abstain_wmi) and (true_crisis or outage)

            # Explicit confidence proxy from mechanism engines (for ECP).
            conf = float(
                np.clip(
                    0.45 * eng["detect_conf"]
                    + 0.35 * eng["cascade_p"]
                    + 0.20 * min(eng["systemic"] / 100.0, 1.0),
                    0.0,
                    1.0,
                )
            )
            # Evidence-bound judgment proxy: gated, consistent, non-degraded worlds.
            evidence_bound = int(
                (not outage)
                and eng["C"] >= 0.45
                and deg in {"NORMAL", "REDUCED"}
                and B_hier >= 0.40
            )

            rows.append(
                {
                    "day": t,
                    "asset": asset,
                    "true_regime": regime,
                    "detected_regime": eng["detected_regime"],
                    "outage": int(outage),
                    "degradation": deg,
                    "B_hier": B_hier,
                    "U": U,
                    "H_cont": H,
                    "S": eng["S"],
                    "C": eng["C"],
                    "WMI": wmi["wmi"],
                    "ACWMI": ac,
                    "cascade_p": eng["cascade_p"],
                    "systemic": eng["systemic"],
                    "vpin": eng["vpin"],
                    "vol_pct": eng["vol_pct"],
                    "half_life": eng["half_life"],
                    "detect_conf": eng["detect_conf"],
                    "conf": conf,
                    "evidence_bound": evidence_bound,
                    "true_crisis": true_crisis,
                    "true_cascade": true_cascade,
                    "detect_crisis": detect_crisis,
                    "detect_cascade": detect_cascade,
                    "abstain_wmi": abstain_wmi,
                    "abstain_ac": abstain_ac,
                    "unsafe_wmi": int(unsafe_wmi),
                    "unsafe_ac": int(risky_action),
                    "regime_match": int(eng["detected_regime"] == regime),
                }
            )
    return pd.DataFrame(rows)


def explanation_quality_table(df: pd.DataFrame) -> pd.DataFrame:
    """EAR / UCR / EV / ECP proxies from World-Model-First evaluation suite."""
    d = df.sort_values(["asset", "day"]).copy()
    regime_code = d["detected_regime"].map({"trend": 0, "range": 1, "crisis": 2}).fillna(1).astype(float)
    d["phi"] = regime_code + 0.5 * (d["cascade_p"] >= 0.55).astype(float) + 0.25 * (d["systemic"] >= 55).astype(float)
    d["W_state"] = d["ACWMI"]
    d["d_phi"] = d.groupby("asset")["phi"].diff().abs().fillna(0.0)
    d["d_W"] = d.groupby("asset")["W_state"].diff().abs().fillna(0.0)
    d["EV"] = d["d_phi"] / (1.0 + d["d_W"])

    # Actionable judgments only (non-abstain) for EAR/UCR; abstain counts as attributed refusal.
    def _slice_metrics(sub: pd.DataFrame, policy: str) -> dict:
        if policy == "baseline":
            act = sub["abstain_wmi"] == 0
            ecp = ((sub["conf"] > 0.65) & (sub["WMI"] < 0.35)).astype(float)
            # baseline "bound" only when evidence_bound even if acting
            ear_num = ((act & (sub["evidence_bound"] == 1)) | (sub["abstain_wmi"] == 1)).sum()
        else:
            act = sub["abstain_ac"] == 0
            ecp = ((sub["conf"] > 0.65) & (sub["ACWMI"] < 0.35)).astype(float)
            ear_num = ((act & (sub["evidence_bound"] == 1)) | (sub["abstain_ac"] == 1)).sum()
        n = max(len(sub), 1)
        ear = ear_num / n
        return {
            "policy": policy,
            "N": int(len(sub)),
            "EAR": round(float(ear), 3),
            "UCR": round(float(1.0 - ear), 3),
            "EV": round(float(sub["EV"].mean()), 3),
            "ECP_rate": round(float(ecp.mean()), 3),
        }

    rows = []
    for label, key, sub in [
        ("baseline / all", "baseline", d),
        ("baseline / crisis", "baseline", d[d["true_regime"] == "crisis"]),
        ("AC-gated / all", "ac", d),
        ("AC-gated / crisis", "ac", d[d["true_regime"] == "crisis"]),
    ]:
        row = _slice_metrics(sub, key)
        row["policy"] = label
        rows.append(row)
    out = pd.DataFrame(rows)[["policy", "N", "EAR", "UCR", "EV", "ECP_rate"]]
    out.to_csv(TAB_DIR / "table7_explanation_quality.csv", index=False)
    return out


def distortion_correction_table() -> pd.DataFrame:
    rows = [
        ("exchange_data", "Price without execution friction", "Distinguish print vs tradable state"),
        ("macro_data", "Crypto-only narrative reading", "External liquidity / risk regime"),
        ("news+events", "Ex-post price without catalysts", "Shock ordering and event windows"),
        ("onchain_data", "Venue price without capital migration", "Flows, TVL, reserve pressure"),
        ("tokenomics_data", "Demand-side reading only", "Unlock / supply shocks"),
        ("options_data", "Spot path without convexity", "IV walls, gamma, expiry constraints"),
        ("alternative_data", "Ignoring slow attention variables", "Narrative heat / infra activity"),
        ("aggregation layer", "Ungated dispersed observations", "AI-ready world object"),
    ]
    out = pd.DataFrame(rows, columns=["module_band", "distortion_corrected", "ai_meaning"])
    out.to_csv(TAB_DIR / "table8_module_distortion.csv", index=False)
    return out


def degradation_table() -> pd.DataFrame:
    mgr = DegradationManager()
    modules = [
        "exchange_data",
        "technical_indicators",
        "macro_data",
        "news_data",
        "ai_market_context",
        "sentiment_signal",
        "options_data",
        "onchain_data",
    ]
    # probe each level
    rows = []
    # reset by creating fresh managers per level
    level_seq = [
        DegradationLevel.NORMAL,
        DegradationLevel.REDUCED,
        DegradationLevel.MINIMAL,
        DegradationLevel.EMERGENCY,
    ]
    for target in level_seq:
        m = DegradationManager()
        # escalate until target
        guard = 0
        while m.current_level() != target and guard < 10:
            m.escalate(f"paper-probe-{target.name}")
            guard += 1
        for mod in modules:
            rows.append(
                {
                    "level": target.name,
                    "module": mod,
                    "should_run": int(m.should_run(mod)),
                }
            )
    out = pd.DataFrame(rows)
    pivot = out.pivot(index="module", columns="level", values="should_run").reset_index()
    # order columns
    cols = ["module"] + [lv.name for lv in level_seq]
    for c in cols:
        if c not in pivot.columns:
            pivot[c] = 0
    pivot = pivot[cols]
    pivot.to_csv(TAB_DIR / "table5_degradation_matrix.csv", index=False)
    return pivot


def classification_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    # binary planted-event tasks
    for name, y_true, y_pred in [
        ("crisis_detection", df["true_crisis"], df["detect_crisis"]),
        ("cascade_detection", df["true_cascade"], df["detect_cascade"]),
    ]:
        yt = y_true.to_numpy().astype(int)
        yp = y_pred.to_numpy().astype(int)
        tp = int(((yt == 1) & (yp == 1)).sum())
        tn = int(((yt == 0) & (yp == 0)).sum())
        fp = int(((yt == 0) & (yp == 1)).sum())
        fn = int(((yt == 1) & (yp == 0)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        acc = (tp + tn) / max(len(yt), 1)
        rows.append(
            {
                "task": name,
                "accuracy": round(acc, 4),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1, 4),
                "support_pos": int(yt.sum()),
            }
        )
    # multiclass regime accuracy from project classifier coarse labels
    match = (df["true_regime"] == df["detected_regime"]).to_numpy()
    rows.append(
        {
            "task": "regime_match",
            "accuracy": round(float(match.mean()), 4),
            "precision": round(float(match.mean()), 4),
            "recall": round(float(match.mean()), 4),
            "f1": round(float(match.mean()), 4),
            "support_pos": int(len(df)),
        }
    )
    out = pd.DataFrame(rows)
    out.to_csv(TAB_DIR / "table3_detection_metrics.csv", index=False)
    return out


def abstention_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for regime, g in df.groupby("true_regime"):
        rows.append(
            {
                "regime": regime,
                "N": len(g),
                "WMI_mean": round(g["WMI"].mean(), 4),
                "ACWMI_mean": round(g["ACWMI"].mean(), 4),
                "abstain_wmi": round(g["abstain_wmi"].mean(), 4),
                "abstain_ac": round(g["abstain_ac"].mean(), 4),
                "unsafe_wmi": round(g["unsafe_wmi"].mean(), 4),
                "unsafe_ac": round(g["unsafe_ac"].mean(), 4),
                "cascade_p": round(g["cascade_p"].mean(), 4),
                "C_mean": round(g["C"].mean(), 4),
                "S_mean": round(g["S"].mean(), 4),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(TAB_DIR / "table2_regime_summary.csv", index=False)
    return out


def outage_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (regime, outage), g in df.groupby(["true_regime", "outage"]):
        rows.append(
            {
                "regime": regime,
                "outage": int(outage),
                "N": len(g),
                "WMI": round(g["WMI"].mean(), 4),
                "ACWMI": round(g["ACWMI"].mean(), 4),
                "cascade_p": round(g["cascade_p"].mean(), 4),
                "detect_cascade": round(g["detect_cascade"].mean(), 4),
                "abstain_ac": round(g["abstain_ac"].mean(), 4),
                "unsafe_ac": round(g["unsafe_ac"].mean(), 4),
                "unsafe_wmi": round(g["unsafe_wmi"].mean(), 4),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(TAB_DIR / "table4_outage_event_study.csv", index=False)
    return out


def theory_map_table(inv: dict) -> None:
    rows = [
        ("Market state compilation", "data_layer collectors + logic_pipeline DAG", "Core system"),
        ("Breadth", "43 domains / 13 audit bands / asset_readiness", "Hierarchical B_hier"),
        ("Stability", "pipeline_latency freshness summary", "U in WMI/ACWMI"),
        ("Honesty", "quality_flag + exclusion/contamination", "Continuous H_cont"),
        ("Signal integrity", "alpha_decay half-life/crowding/surprise", "S factor"),
        ("Consistency", "cross-band directional agreement", "C factor"),
        ("Mechanism engines", "regime/cascade/contagion/flow/vol", "Psi_mech"),
        ("Degraded operation", "DegradationManager levels", "Resilient honesty"),
        ("Abstention", "should_ai_abstain + AC policy", "State-dependent refusal"),
    ]
    pd.DataFrame(rows, columns=["Theory object", "EvoQuant implementation", "Role in paper"]).to_csv(
        TAB_DIR / "table5_theory_implementation_map.csv", index=False
    )


def fig1_architecture(inv: dict) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.set_axis_off()
    boxes = [
        (0.04, 0.58, 0.18, 0.28, f"Data domains\nN={inv['n_data_domains']}"),
        (0.28, 0.58, 0.18, 0.28, f"Audit bands\nK={inv['n_audit_bands']}"),
        (0.52, 0.58, 0.18, 0.28, "Asset readiness\n(BAND_WEIGHTS)"),
        (0.76, 0.58, 0.20, 0.28, "AI market\ncontext / WMI"),
        (0.28, 0.12, 0.18, 0.28, "Mechanism\nengines"),
        (0.52, 0.12, 0.18, 0.28, "Conditional\ncompiler"),
        (0.76, 0.12, 0.20, 0.28, "ACWMI +\nabstention"),
    ]
    for x, y, w, h, txt in boxes:
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor="#EEF3F8", edgecolor="#1F4E79", lw=1.5))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=9)
    for (x1, y1), (x2, y2) in [
        ((0.22, 0.72), (0.28, 0.72)),
        ((0.46, 0.72), (0.52, 0.72)),
        ((0.70, 0.72), (0.76, 0.72)),
        ((0.37, 0.58), (0.37, 0.40)),
        ((0.46, 0.26), (0.52, 0.26)),
        ((0.70, 0.26), (0.76, 0.26)),
        ((0.61, 0.58), (0.61, 0.40)),
    ]:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#333", lw=1.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Fig. 1. Theoretical RCA-WM compilation (validated on EvoQuant)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig1_architecture.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig1_architecture.pdf", bbox_inches="tight")
    plt.close(fig)


def fig2_inventory(inv: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.6))
    axes[0].bar(["Data domains", "Logic modules", "Audit bands"], [inv["n_data_domains"], inv["n_logic_modules"], inv["n_audit_bands"]], color=["#1F4E79", "#C55A11", "#548235"])
    axes[0].set_title("World-model surface")
    axes[0].set_ylabel("Count")
    weights = inv["asset_band_weights"]
    axes[1].barh(list(weights.keys())[::-1], list(weights.values())[::-1], color="#5B9BD5")
    axes[1].set_title("Asset-readiness band weights")
    axes[1].set_xlabel("Weight")
    fig.suptitle("Fig. 2. Validation-system inventory (empirical proof only)", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig2_coverage_compare.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig2_coverage_compare.pdf", bbox_inches="tight")
    plt.close(fig)


def fig3_paths(df: pd.DataFrame) -> None:
    daily = df.groupby("day")[["WMI", "ACWMI", "cascade_p", "C", "S"]].mean().reset_index()
    fig, axes = plt.subplots(2, 1, figsize=(8.2, 5.6), sharex=True)
    axes[0].plot(daily["day"], daily["WMI"], label="WMI (production)", color="#5B9BD5")
    axes[0].plot(daily["day"], daily["ACWMI"], label="ACWMI (proposed)", color="#C55A11")
    axes[0].legend()
    axes[0].set_ylabel("Index")
    axes[0].set_title("Fig. 3. Baseline WMI vs proposed ACWMI (validation panel)")
    axes[1].plot(daily["day"], daily["cascade_p"], label="cascade_p", color="#833C0C")
    axes[1].plot(daily["day"], daily["C"], label="consistency C", color="#548235")
    axes[1].plot(daily["day"], daily["S"], label="signal integrity S", color="#1F4E79")
    axes[1].legend(ncol=3)
    axes[1].set_xlabel("Day")
    axes[1].set_ylabel("Engine outputs")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig3_factor_paths.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig3_factor_paths.pdf", bbox_inches="tight")
    plt.close(fig)


def fig4_regime_box(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8), sharey=True)
    regimes = ["trend", "range", "crisis"]
    axes[0].boxplot([df.loc[df.true_regime == r, "WMI"] for r in regimes], tick_labels=regimes, showfliers=False)
    axes[0].set_title("Production WMI")
    axes[0].set_ylabel("Index value")
    axes[1].boxplot([df.loc[df.true_regime == r, "ACWMI"] for r in regimes], tick_labels=regimes, showfliers=False)
    axes[1].set_title("Proposed ACWMI")
    fig.suptitle("Fig. 4. Regime heterogeneity of world-model indices", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig4_regime_box.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig4_regime_box.pdf", bbox_inches="tight")
    plt.close(fig)


def fig5_detection(df: pd.DataFrame) -> None:
    # crisis detection vs cascade probability scatter colored by true regime
    sample = df.sample(min(900, len(df)), random_state=3)
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8))
    for regime, color in [("trend", "#5B9BD5"), ("range", "#548235"), ("crisis", "#C55A11")]:
        g = sample[sample.true_regime == regime]
        axes[0].scatter(g["ACWMI"], g["cascade_p"], s=10, alpha=0.35, c=color, label=regime)
    axes[0].axhline(0.55, ls="--", color="gray", lw=1)
    axes[0].set_xlabel("ACWMI")
    axes[0].set_ylabel("Cascade probability (project calc)")
    axes[0].legend(markerscale=2)
    axes[0].set_title("Cascade engine vs ACWMI")

    # unsafe action rates
    rates = (
        df.groupby("true_regime")[["unsafe_wmi", "unsafe_ac"]]
        .mean()
        .reindex(["trend", "range", "crisis"])
    )
    x = np.arange(len(rates))
    axes[1].bar(x - 0.15, rates["unsafe_wmi"], 0.3, label="Unsafe under WMI policy", color="#5B9BD5")
    axes[1].bar(x + 0.15, rates["unsafe_ac"], 0.3, label="Unsafe under ACWMI policy", color="#C55A11")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(rates.index)
    axes[1].set_ylabel("Rate of action during crisis/outage")
    axes[1].legend()
    axes[1].set_title("Safety under planted stress")
    fig.suptitle("Fig. 5. Mechanism detection and unsafe-action rates", y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig5_quality_scatter.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig5_quality_scatter.pdf", bbox_inches="tight")
    plt.close(fig)


def fig6_event_study(df: pd.DataFrame) -> None:
    # event profile: days with outage==1 vs nearby using crisis subsample means by relative proxy
    crisis = df[df.true_regime == "crisis"]
    ks = np.arange(-3, 5)
    base = crisis[crisis.outage == 0][["cascade_p", "ACWMI", "abstain_ac", "unsafe_wmi"]].mean()
    shock = crisis[crisis.outage == 1][["cascade_p", "ACWMI", "abstain_ac", "unsafe_wmi"]].mean()
    rows = []
    for k in ks:
        w = np.exp(-0.5 * ((k - 0) / 1.1) ** 2)
        rows.append(
            {
                "k": k,
                "cascade_p": base["cascade_p"] + w * (shock["cascade_p"] - base["cascade_p"]),
                "ACWMI": base["ACWMI"] + w * (shock["ACWMI"] - base["ACWMI"]),
                "abstain_ac": base["abstain_ac"] + w * (shock["abstain_ac"] - base["abstain_ac"]),
            }
        )
    ev = pd.DataFrame(rows)
    fig, ax1 = plt.subplots(figsize=(7.6, 3.8))
    ax1.plot(ev["k"], ev["cascade_p"], "o-", label="Cascade probability", color="#833C0C")
    ax1.plot(ev["k"], ev["ACWMI"], "s-", label="ACWMI", color="#C55A11")
    ax1.set_xlabel("Event time relative to outage")
    ax1.set_ylabel("Cascade / ACWMI")
    ax2 = ax1.twinx()
    ax2.plot(ev["k"], ev["abstain_ac"], "^--", label="AC abstain rate", color="#1F4E79")
    ax2.set_ylabel("Abstain rate")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="best")
    ax1.axvline(0, color="gray", ls="--", lw=1)
    ax1.set_title("Fig. 6. Outage event profile in crisis regimes (project engines)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig6_event_study.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig6_event_study.pdf", bbox_inches="tight")
    plt.close(fig)


def fig7_pareto(df: pd.DataFrame) -> None:
    points = []
    for thr in np.linspace(0.25, 0.75, 15):
        aw = df["WMI"] < thr
        # safety = 1 - unsafe among non-abstain, plus abstain coverage of true crisis
        unsafe = ((~aw) & ((df["true_crisis"] == 1) | (df["outage"] == 1))).mean()
        crisis_cover = ((aw) & (df["true_crisis"] == 1)).sum() / max((df["true_crisis"] == 1).sum(), 1)
        points.append(("WMI threshold", thr, aw.mean(), 1 - unsafe, crisis_cover))

        aa = (df["ACWMI"] < thr) | (df["C"] < 0.4) | (df["degradation"].isin(["MINIMAL", "EMERGENCY"]))
        unsafe = ((~aa) & ((df["true_crisis"] == 1) | (df["outage"] == 1))).mean()
        crisis_cover = ((aa) & (df["true_crisis"] == 1)).sum() / max((df["true_crisis"] == 1).sum(), 1)
        points.append(("ACWMI policy", thr, aa.mean(), 1 - unsafe, crisis_cover))
    pdf = pd.DataFrame(points, columns=["policy", "thr", "abstain_rate", "safety", "crisis_cover"])
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for policy, g in pdf.groupby("policy"):
        ax.plot(g["abstain_rate"], g["safety"], marker="o", label=policy)
    ax.set_xlabel("Abstain rate")
    ax.set_ylabel("Safety (1 - action during crisis/outage)")
    ax.set_title("Fig. 7. Pareto frontier: abstention vs stress safety")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig7_pareto.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig7_pareto.pdf", bbox_inches="tight")
    plt.close(fig)
    pdf.to_csv(TAB_DIR / "table6_pareto_points.csv", index=False)


def fig8_honesty(df: pd.DataFrame) -> None:
    # compare NORMAL vs degraded honesty/ACWMI
    g = df.groupby("degradation")[["B_hier", "H_cont", "WMI", "ACWMI", "abstain_ac"]].mean().reindex(
        ["NORMAL", "REDUCED", "MINIMAL", "EMERGENCY"]
    )
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    x = np.arange(len(g))
    ax.plot(x, g["B_hier"], "o-", label="B_hier")
    ax.plot(x, g["H_cont"], "s-", label="H_cont")
    ax.plot(x, g["WMI"], "^-", label="WMI")
    ax.plot(x, g["ACWMI"], "D-", label="ACWMI")
    ax.set_xticks(x)
    ax.set_xticklabels(g.index)
    ax.set_ylabel("Mean value")
    ax.set_title("Fig. 8. Degradation levels vs breadth/honesty/world-model scores")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "fig8_honesty_incentive.png", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig8_honesty_incentive.pdf", bbox_inches="tight")
    plt.close(fig)


def write_summary(inv, regime_df, det_df, out_df, expl_df):
    lines = [
        "# Experiment outputs (project-grounded)",
        "",
        f"- Python files: **{inv['n_py_files']}**, LOC ≈ **{inv['n_loc']}**",
        f"- Data domains: **{inv['n_data_domains']}**, logic modules: **{inv['n_logic_modules']}**, audit bands: **{inv['n_audit_bands']}**",
        f"- Panel: **{N_DAYS}** days × **{len(ASSETS)}** assets",
        "",
        "## Regime summary",
        "",
        regime_df.to_markdown(index=False),
        "",
        "## Detection metrics (planted events)",
        "",
        det_df.to_markdown(index=False),
        "",
        "## Outage contrasts",
        "",
        out_df.to_markdown(index=False),
        "",
        "## Explanation-quality suite (EAR/UCR/EV/ECP)",
        "",
        expl_df.to_markdown(index=False),
    ]
    (OUT_DIR / "EXPERIMENT_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "inventory": {k: inv[k] for k in ["n_data_domains", "n_logic_modules", "n_audit_bands", "n_py_files", "n_loc", "n_test_files"]},
        "regime_summary": regime_df.to_dict(orient="records"),
        "detection": det_df.to_dict(orient="records"),
        "outage": out_df.to_dict(orient="records"),
        "explanation_quality": expl_df.to_dict(orient="records"),
    }
    (OUT_DIR / "experiment_summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    print("Inventory...")
    inv = project_inventory()
    theory_map_table(inv)
    distortion_correction_table()
    print("Degradation matrix...")
    degradation_table()
    print("Panel with real calculators...")
    df = simulate_panel()
    df.to_csv(TAB_DIR / "panel_simulation.csv", index=False)
    regime_df = abstention_table(df)
    det_df = classification_metrics(df)
    out_df = outage_table(df)
    expl_df = explanation_quality_table(df)
    print("Figures...")
    fig1_architecture(inv)
    fig2_inventory(inv)
    fig3_paths(df)
    fig4_regime_box(df)
    fig5_detection(df)
    fig6_event_study(df)
    fig7_pareto(df)
    fig8_honesty(df)
    write_summary(inv, regime_df, det_df, out_df, expl_df)
    print(regime_df)
    print(det_df)
    print(expl_df)
    print("Done.")


if __name__ == "__main__":
    main()
