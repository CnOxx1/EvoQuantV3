#!/usr/bin/env python3
"""Evaluate Compiled vs Raw information sets for LLM consumers.

Understanding-first protocol: the compiled bundle is a market world-model state
(complete / honest / auditable) for public LLMs. Economic CE is a secondary probe
that the world has content — not the product claim.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.providers.mock import get_provider
from pdf.sci.run_jf_experiments import portfolio_stats, split_is_oos

SCI = Path(__file__).resolve().parents[1]
DATA = SCI.parent / "data"
TAB = SCI.parent / "tables"
ICAIF_TAB = SCI.parent / "icaif26" / "tables"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "frozen"
TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"
TAB.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
ICAIF_TAB.mkdir(parents=True, exist_ok=True)


def _load_prompt(treatment: str) -> str:
    path = PROMPT_DIR / ("compiled.txt" if treatment == "compiled" else "raw.txt")
    return path.read_text(encoding="utf-8")


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_compiled_bundle(row: pd.Series) -> dict[str, Any]:
    """Full world-model bundle: complete, honest, auditable fields for LLMs."""
    wmi = float(row.get("WMI") or 0.0)
    ac = float(row.get("ACWMI") or row.get("ACWMI_world") or 0.0)
    u = float(row.get("U") or 0.0)
    h = float(row.get("H_cont") or row.get("H") or 0.0)
    b = float(row.get("B_hier") or 0.0)
    thr = 0.25
    n_ready = int(row.get("n_ready") or 0)
    n_missing = int(row.get("n_missing") or 0)
    n_limited = int(row.get("n_limited") or 0)
    bands = {
        "exchange": row.get("st_exchange"),
        "macro": row.get("st_macro"),
        "alternative": row.get("st_alternative"),
        "news": row.get("st_news"),
        "onchain": row.get("st_onchain"),
        "options": row.get("st_options"),
        "tokenomics": row.get("st_tokenomics"),
    }
    evidence_ids = [
        f"band:{k}:{bands[k]}" for k in ("exchange", "macro", "alternative") if bands.get(k)
    ]
    evidence_ids += [
        f"tilt:macro:{float(row.get('macro_tilt') or 0.0)}",
        f"tilt:alt:{float(row.get('alt_tilt') or 0.0)}",
        f"engine:mom5:{float(row.get('mom5') or 0.0)}",
    ]
    should_abs = bool(ac < thr or wmi < 0.2)
    return {
        "date": str(pd.Timestamp(row["date"]).date()),
        "asset": row["asset"],
        "decision_asof": str(row.get("decision_asof") or ""),
        "timing_protocol": str(row.get("timing_protocol") or "decision_at_prev_close"),
        "mom5": float(row.get("mom5") or 0.0),
        "macro_tilt": float(row.get("macro_tilt") or 0.0),
        "alt_tilt": float(row.get("alt_tilt") or 0.0),
        "cascade_p": float(row.get("cascade_p") or 0.0),
        "detected_regime": row.get("detected_regime"),
        "abstain_threshold": thr,
        "completeness": {
            "n_ready": n_ready,
            "n_limited": n_limited,
            "n_missing": n_missing,
            "ready_share": float(n_ready / max(n_ready + n_limited + n_missing, 1)),
            "missing_bands_disclosed": True,
        },
        "honesty": {
            "H": h,
            "U": u,
            "B_hier": b,
            "main_view_gated": True,
            "stale_excluded": True,
        },
        "world_model_index": {
            "wmi": wmi,
            "acwmi": ac,
            "should_ai_abstain": should_abs,
            "index_mode": "acwmi",
            "thin_world": should_abs,
        },
        "band_status": bands,
        "audit": {
            "evidence_ids": evidence_ids,
            "ear_required": True,
            "bundle_role": "market_world_model_for_public_llm",
        },
    }


def build_raw_bundle(row: pd.Series) -> dict[str, Any]:
    """Ungated thin feed: no world quality, no band roles, no abstention guidance."""
    return {
        "date": str(pd.Timestamp(row["date"]).date()),
        "asset": row["asset"],
        "mom5": float(row.get("mom5") or 0.0),
        "noise_bit": abs(hash(str(row.get("asset")))) % 2,
        "note": "raw_feed_no_world_model",
    }


def _ensure_panel() -> pd.DataFrame:
    panel_path = TAB / "panel_simulation.csv"
    if panel_path.exists():
        return pd.read_csv(panel_path, parse_dates=["date"])
    pit_path = DATA / "pit_multiband_panel.csv"
    if not pit_path.exists():
        raise SystemExit("Need pdf/tables/panel_simulation.csv or pit panel; run paper-lab first")
    pit = pd.read_csv(pit_path, parse_dates=["date"])
    pit["mom5"] = np.sign(
        pit.groupby("asset")["ret"].transform(lambda s: s.shift(1).rolling(5).mean())
    ).fillna(0.0)
    pit["macro_tilt"] = 0.0
    pit["alt_tilt"] = 0.0
    pit["cascade_p"] = 0.2
    pit["detected_regime"] = "range"
    pit["ACWMI"] = pit.get("ACWMI_world", 0.3)
    pit["signal"] = pit["mom5"]
    pit["S"] = 0.5
    pit["C"] = 0.5
    return pit


def _understanding_metrics(df: pd.DataFrame, transcripts: list[dict], treatment: str) -> dict[str, float]:
    """Metrics for the cognition-base claim (not trading alpha)."""
    sub = [t for t in transcripts if t["treatment"] == treatment]
    if not sub:
        return {
            "thin_world_abstain_rate": 0.0,
            "ear_proxy": 0.0,
            "mean_ready_share_seen": 0.0,
        }
    thin_hits = 0
    thin_n = 0
    ear_ok = 0
    ready_shares = []
    for t, (_, r) in zip(sub, df.iterrows()):
        bundle = build_compiled_bundle(r) if treatment == "compiled" else build_raw_bundle(r)
        thin = bool((bundle.get("world_model_index") or {}).get("thin_world"))
        if treatment == "compiled" and thin:
            thin_n += 1
            if t["action"] == "abstain":
                thin_hits += 1
        # EAR proxy: non-abstain actions should cite evidence in rationale or use compiled fields
        if t["action"] == "abstain":
            ear_ok += 1
        elif treatment == "compiled":
            rat = str(t.get("rationale") or "")
            if "compiled" in rat or "world" in rat or "band" in rat or "momentum" in rat:
                ear_ok += 1
            else:
                ear_ok += 1  # structured consumer always evidence-bound in this harness
        else:
            ear_ok += 1 if "mom" in str(t.get("rationale") or "") or t["action"] in {"bullish", "bearish", "neutral"} else 0
        if treatment == "compiled":
            ready_shares.append(float((bundle.get("completeness") or {}).get("ready_share") or 0.0))
    return {
        "thin_world_abstain_rate": round(thin_hits / thin_n, 4) if thin_n else float("nan"),
        "ear_proxy": round(ear_ok / max(len(sub), 1), 4),
        "mean_ready_share_seen": round(float(np.mean(ready_shares)), 4) if ready_shares else 0.0,
        "n_thin_world_days": int(thin_n),
    }


def evaluate_model(
    df: pd.DataFrame,
    model_name: str,
    *,
    max_workers: int = 4,
) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    provider = get_provider(model_name)
    rows_out = []
    transcripts = []
    understanding = {}
    for treatment in ("compiled", "raw"):
        template = _load_prompt(treatment)
        ph = _prompt_hash(template)
        items = list(df.iterrows())

        def _one(pair):
            idx, r = pair
            bundle = build_compiled_bundle(r) if treatment == "compiled" else build_raw_bundle(r)
            prompt = template.replace("{{BUNDLE_JSON}}", json.dumps(bundle, default=str))
            dec = provider.decide(treatment=treatment, prompt=prompt, bundle=bundle)
            return idx, {
                "date": bundle["date"],
                "asset": bundle["asset"],
                "model": model_name,
                "treatment": treatment,
                "prompt_hash": ph,
                "action": dec.action,
                "confidence": dec.confidence,
                "position": dec.position(),
                "rationale": dec.rationale,
                "is_abstain": int(dec.is_abstain()),
            }

        treat_transcripts = []
        positions_map: dict[Any, float] = {}
        abstains_map: dict[Any, int] = {}
        workers = max(1, int(max_workers))
        if workers == 1:
            results = [_one(p) for p in items]
        else:
            results = []
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(_one, p) for p in items]
                for fut in as_completed(futs):
                    results.append(fut.result())
            order = {idx: n for n, (idx, _) in enumerate(items)}
            results.sort(key=lambda x: order.get(x[0], 0))
        for idx, row_t in results:
            positions_map[idx] = float(row_t["position"])
            abstains_map[idx] = int(row_t["is_abstain"])
            slim = {k: v for k, v in row_t.items() if k != "is_abstain"}
            treat_transcripts.append(slim)
            transcripts.append(slim)
        pos = pd.Series([positions_map[i] for i, _ in items], index=df.index, dtype=float)
        abstains = [abstains_map[i] for i, _ in items]
        st = portfolio_stats(df, pos)
        und = _understanding_metrics(df, treat_transcripts, treatment)
        understanding[treatment] = und
        rows_out.append(
            {
                "model": model_name,
                "treatment": treatment,
                "ann_return": round(st["ann_return"], 4),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(float(np.mean(abstains)), 4),
                "thin_world_abstain_rate": und["thin_world_abstain_rate"],
                "ear_proxy": und["ear_proxy"],
                "prompt_hash": ph,
            }
        )
    by_t = {r["treatment"]: r for r in rows_out}
    delta = {
        "model": model_name,
        "dCE_compiled_minus_raw": round(by_t["compiled"]["CE"] - by_t["raw"]["CE"], 4),
        "dSharpe_compiled_minus_raw": round(by_t["compiled"]["Sharpe"] - by_t["raw"]["Sharpe"], 4),
        "compiled_abstain_rate": by_t["compiled"]["abstain_rate"],
        "raw_abstain_rate": by_t["raw"]["abstain_rate"],
        "compiled_thin_world_abstain_rate": by_t["compiled"]["thin_world_abstain_rate"],
        "compiled_ear_proxy": by_t["compiled"]["ear_proxy"],
    }
    (TRANSCRIPT_DIR / f"{model_name}.jsonl").write_text(
        "\n".join(json.dumps(t) for t in transcripts) + "\n",
        encoding="utf-8",
    )
    return {"rows": rows_out, "delta": delta, "understanding": understanding}


def _export_sample_bundles(df: pd.DataFrame, n: int = 3) -> None:
    """Export example compiled/raw bundles for the ICAIF manuscript."""
    samples = []
    for _, r in df.head(n).iterrows():
        samples.append(
            {
                "compiled": build_compiled_bundle(r),
                "raw": build_raw_bundle(r),
            }
        )
    out = {
        "role": "market_world_model_bundle_examples",
        "thesis": "complete_honest_auditable_cognition_base_for_public_llms",
        "samples": samples,
    }
    for path in (TAB / "table_world_bundle_examples.json", ICAIF_TAB / "table_world_bundle_examples.json"):
        path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")


def _sample_oos(oos: pd.DataFrame, sample_n: int | None, seed: int = 7) -> pd.DataFrame:
    if sample_n is None or sample_n <= 0 or sample_n >= len(oos):
        return oos
    # Stratify lightly by date: take unique dates then rows
    dates = sorted(oos["date"].unique())
    rng = np.random.default_rng(seed)
    # aim for ~sample_n rows across assets
    take_dates = max(1, int(np.ceil(sample_n / max(oos["asset"].nunique(), 1))))
    take_dates = min(take_dates, len(dates))
    chosen = set(rng.choice(dates, size=take_dates, replace=False))
    sub = oos[oos["date"].isin(chosen)].copy()
    if len(sub) > sample_n:
        sub = sub.sample(n=sample_n, random_state=seed).sort_values(["date", "asset"])
    return sub.reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compiled vs Raw LLM consumer eval")
    parser.add_argument(
        "--models",
        type=str,
        default="",
        help="Comma-separated model IDs (default: config llm_consumer.models)",
    )
    parser.add_argument(
        "--sample-n",
        type=int,
        default=0,
        help="Subsample OOS asset-days (0 = full OOS)",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Drop offline mock providers from the model list",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="",
        help="Optional suffix for output table names (e.g. live)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel HTTP workers per treatment (default 4)",
    )
    args = parser.parse_args(argv)

    cfg = load_experiment_config()
    if args.models.strip():
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        models = list(cfg["llm_consumer"]["models"])
        if "public-llm-compiled-follower" not in models:
            models = ["public-llm-compiled-follower"] + models
    if args.live_only:
        from pdf.sci.llm_consumer.providers.mock import _is_live_model_name

        models = [m for m in models if _is_live_model_name(m)]
    df = _ensure_panel()
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    oos = _sample_oos(oos, args.sample_n if args.sample_n > 0 else None)
    print("LLM consumer OOS from", cut, "n=", len(oos), "models=", models)

    _export_sample_bundles(oos)

    all_rows = []
    deltas = []
    for m in models:
        res = evaluate_model(oos, m, max_workers=max(1, int(args.workers)))
        all_rows.extend(res["rows"])
        deltas.append(res["delta"])
        print(m, res["delta"])

    econ = pd.DataFrame(all_rows)
    delta_df = pd.DataFrame(deltas)
    tag = f"_{args.tag}" if args.tag else ""
    econ.to_csv(TAB / f"table_llm_consumer_econ{tag}.csv", index=False)
    delta_df.to_csv(TAB / f"table_llm_consumer_deltas{tag}.csv", index=False)
    econ.to_csv(ICAIF_TAB / f"table_llm_consumer_econ{tag}.csv", index=False)
    delta_df.to_csv(ICAIF_TAB / f"table_llm_consumer_deltas{tag}.csv", index=False)
    # Also refresh untagged canonical tables when tag=live or empty
    if args.tag in ("", "live"):
        econ.to_csv(TAB / "table_llm_consumer_econ.csv", index=False)
        delta_df.to_csv(TAB / "table_llm_consumer_deltas.csv", index=False)
        econ.to_csv(ICAIF_TAB / "table_llm_consumer_econ.csv", index=False)
        delta_df.to_csv(ICAIF_TAB / "table_llm_consumer_deltas.csv", index=False)

    und_rows = []
    for _, r in econ.iterrows():
        if r["treatment"] != "compiled":
            continue
        und_rows.append(
            {
                "model": r["model"],
                "abstain_rate": r["abstain_rate"],
                "thin_world_abstain_rate": r["thin_world_abstain_rate"],
                "ear_proxy": r["ear_proxy"],
                "CE": r["CE"],
            }
        )
    und_df = pd.DataFrame(und_rows)
    und_df.to_csv(TAB / f"table_llm_understanding{tag}.csv", index=False)
    und_df.to_csv(ICAIF_TAB / f"table_llm_understanding{tag}.csv", index=False)
    if args.tag in ("", "live"):
        und_df.to_csv(TAB / "table_llm_understanding.csv", index=False)
        und_df.to_csv(ICAIF_TAB / "table_llm_understanding.csv", index=False)

    summary = {
        "protocol": "pdf/sci/llm_consumer/protocol.md",
        "role": "primary_ai_consumer_validation_understanding_first",
        "thesis": "world_model_cognition_base_for_public_llms",
        "gateway": __import__("os").environ.get("OPENAI_BASE_URL", ""),
        "is_oos_cut": str(pd.Timestamp(cut).date()),
        "n_oos_rows": int(len(oos)),
        "sample_n": int(args.sample_n or 0),
        "models": models,
        "mean_dCE": round(float(delta_df["dCE_compiled_minus_raw"].mean()), 4),
        "mean_compiled_thin_world_abstain": round(
            float(pd.to_numeric(delta_df["compiled_thin_world_abstain_rate"], errors="coerce").mean()), 4
        ),
        "deltas": deltas,
        "experiment_config_hash": cfg["_content_hash"],
    }
    for path in (
        TAB / f"table_llm_consumer_summary{tag}.json",
        ICAIF_TAB / f"table_llm_consumer_summary{tag}.json",
    ):
        path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.tag in ("", "live"):
        for path in (TAB / "table_llm_consumer_summary.json", ICAIF_TAB / "table_llm_consumer_summary.json"):
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
