#!/usr/bin/env python3
"""Aggregate clean full-OOS RQ1 checkpoints into tables / ICAIF numbers.

Does not call any LLM API. Reads ``*_full_{treatment}.ckpt.jsonl`` under
transcripts/, drops ``provider-error*`` rows, and recomputes understanding +
portfolio metrics on the intersecting OOS rows.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.eval import (
    TRANSCRIPT_DIR,
    _ensure_panel,
    _understanding_metrics,
    build_compiled_bundle,
)
from pdf.sci.run_jf_experiments import portfolio_stats, split_is_oos

TAB = ROOT / "pdf" / "tables"
ICAIF_TAB = ROOT / "pdf" / "icaif26" / "tables"
MODELS = (
    "gpt-5.4-mini",
    "deepseek-v4-flash",
    "glm-5.2",
    "gemini-3.5-flash-lite",
)
TREATMENTS = ("compiled", "ungated", "raw")


def wilson(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = min(max(p, 0.0), 1.0)
    den = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = (z / den) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


def _load_ckpt(model: str, treatment: str) -> list[dict[str, Any]]:
    path = TRANSCRIPT_DIR / f"{model}_full_{treatment}.ckpt.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(rec.get("rationale", "")).startswith("provider-error"):
            continue
        key = (str(rec["date"]), str(rec["asset"]))
        # last write wins (append-resume may duplicate before unique keying)
        if key in seen:
            # replace previous
            for i, prev in enumerate(out):
                if (prev["date"], prev["asset"]) == key:
                    out[i] = rec
                    break
        else:
            seen.add(key)
            out.append(rec)
    return out


def _metrics_for(
    oos: pd.DataFrame, transcripts: list[dict[str, Any]], treatment: str
) -> dict[str, Any]:
    if not transcripts:
        return {"n": 0}
    # align panel rows to transcript (date, asset) order
    idx = {(str(pd.Timestamp(r.date).date()), str(r.asset)): i for i, r in oos.iterrows()}
    rows = []
    keep_t = []
    for t in transcripts:
        key = (str(t["date"]), str(t["asset"]))
        if key not in idx:
            continue
        rows.append(oos.loc[idx[key]])
        keep_t.append(t)
    if not keep_t:
        return {"n": 0}
    sub = pd.DataFrame(rows)
    pos = pd.Series([float(t.get("position") or 0.0) for t in keep_t], index=sub.index)
    st = portfolio_stats(sub, pos)
    und = _understanding_metrics(sub, keep_t, treatment)
    abstain = float(np.mean([int(t.get("action") == "abstain") for t in keep_t]))
    # thin abstain uses understanding metric when defined
    thin_rate = und.get("thin_world_abstain_rate")
    if treatment == "raw":
        # paper reports overall abstain for Raw arm
        thin_n = len(keep_t)
        thin_rate = abstain
    else:
        thin_n = int(und.get("n_thin_world_days") or 0)
        # if every day is thin, thin_rate == abstain_rate on thin days
    acts = {"abstain": 0, "bullish": 0, "bearish": 0, "neutral": 0}
    for t in keep_t:
        a = str(t.get("action") or "neutral")
        acts[a] = acts.get(a, 0) + 1
    n = len(keep_t)
    lo, hi = wilson(float(thin_rate) if thin_rate == thin_rate else abstain, max(thin_n, n) if treatment != "raw" else n)
    # For compiled/ungated CI on thin-world days:
    if treatment in {"compiled", "ungated"} and thin_n > 0:
        # recompute hits for CI n
        thin_hits = 0
        for t, (_, r) in zip(keep_t, sub.iterrows()):
            compiled = build_compiled_bundle(r)
            thin = bool((compiled.get("world_model_index") or {}).get("thin_world"))
            if thin and t["action"] == "abstain":
                thin_hits += 1
        p = thin_hits / thin_n
        lo, hi = wilson(p, thin_n)
        thin_rate = p
    elif treatment == "raw":
        lo, hi = wilson(abstain, n)

    return {
        "n": n,
        "abstain": round(abstain, 4),
        "thin_n": int(thin_n) if treatment != "raw" else n,
        "thin_abstain": round(float(thin_rate), 4) if thin_rate == thin_rate else None,
        "thin_ci": [round(lo, 4), round(hi, 4)],
        "CE": round(float(st["CE"]), 4),
        "Sharpe": round(float(st["Sharpe"]), 3),
        "ann_return": round(float(st["ann_return"]), 4),
        "action_mix": {k: round(v / n, 4) for k, v in acts.items()},
        "ear_proxy": und.get("ear_proxy"),
    }


def main() -> int:
    cfg = load_experiment_config()
    df = _ensure_panel()
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    print(f"OOS from {cut} n={len(oos)} {oos['date'].min().date()} → {oos['date'].max().date()}")

    report: dict[str, Any] = {"oos_n": int(len(oos)), "models": {}}
    rows_csv = []
    complete = True
    for model in MODELS:
        report["models"][model] = {}
        by_t = {}
        for treatment in TREATMENTS:
            ckpt = _load_ckpt(model, treatment)
            print(f"  {model}/{treatment}: {len(ckpt)} clean decisions")
            if len(ckpt) < len(oos) * 0.95:
                complete = False
            m = _metrics_for(oos, ckpt, treatment)
            report["models"][model][treatment] = m
            by_t[treatment] = m
            rows_csv.append(
                {
                    "model": model,
                    "treatment": treatment,
                    **{k: v for k, v in m.items() if k != "action_mix"},
                    **{f"mix_{k}": v for k, v in (m.get("action_mix") or {}).items()},
                }
            )
        if "compiled" in by_t and "raw" in by_t and by_t["compiled"].get("n") and by_t["raw"].get("n"):
            report["models"][model]["dCE_compiled_minus_raw"] = round(
                float(by_t["compiled"]["CE"]) - float(by_t["raw"]["CE"]), 4
            )

    TAB.mkdir(parents=True, exist_ok=True)
    ICAIF_TAB.mkdir(parents=True, exist_ok=True)
    out_json = TAB / "table_llm_full_oos_all.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # also refresh gpt-only convenience file
    if "gpt-5.4-mini" in report["models"]:
        (TAB / "table_llm_full_oos_gpt.json").write_text(
            json.dumps(report["models"]["gpt-5.4-mini"], indent=2), encoding="utf-8"
        )
    pd.DataFrame(rows_csv).to_csv(TAB / "table_llm_full_oos_all.csv", index=False)
    pd.DataFrame(rows_csv).to_csv(ICAIF_TAB / "table_llm_full_oos_all.csv", index=False)
    report["complete"] = complete
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("wrote", out_json, "complete=", complete)

    # Print LaTeX-ready paragraph snippet
    print("\n--- LaTeX snippet ---")
    for model in MODELS:
        m = report["models"][model]
        if not all(t in m and m[t].get("n") for t in TREATMENTS):
            print(f"% {model}: incomplete")
            continue
        c, u, r = m["compiled"], m["ungated"], m["raw"]
        dce = m.get("dCE_compiled_minus_raw")
        print(
            f"% {model}: C thin={c['thin_abstain']} {c['thin_ci']} n={c['n']}; "
            f"U={u['thin_abstain']} {u['thin_ci']}; R abs={r['abstain']} {r['thin_ci']}; "
            f"dCE={dce}"
        )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
