#!/usr/bin/env python3
"""Non-trading cognition task: world-state grounding workflow for public LLMs.

Multi-step analyst workflow scored against the PIT archive (three durable bands):

  - sufficiency_acc: model says "insufficient" on thin-world days
  - ready_f1 / missing_f1: F1 of predicted ready/missing sets vs band_status
  - tilt_sign_acc: accuracy of macro_tilt_sign and alt_tilt_sign

Compiled vs Raw: only the compiled bundle makes ready/missing and tilts
verifiable.

Usage:
  python -m pdf.sci.llm_consumer.grounding_eval \
      --models gpt-5.4-mini,deepseek-v4-flash --sample-n 50 --workers 8
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.eval import (
    DURABLE_BANDS,
    _ensure_panel,
    _sample_oos,
    build_compiled_bundle,
    build_raw_bundle,
)
from pdf.sci.llm_consumer.providers.openai_compatible import chat_text
from pdf.sci.run_jf_experiments import split_is_oos

SCI = Path(__file__).resolve().parents[1]
TAB = SCI.parent / "tables"
ICAIF_TAB = SCI.parent / "icaif26" / "tables"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "frozen"
TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"

BANDS = DURABLE_BANDS

SYSTEM = (
    "You are a careful market analyst. Reply with ONLY a JSON object matching "
    'the requested schema: {"data_sufficiency":"sufficient|insufficient",'
    '"ready_bands":[...],"missing_bands":[...],'
    '"macro_tilt_sign":-1,"alt_tilt_sign":0,"summary":"..."}.'
)


def _parse(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}


def _norm_bands(items: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(items, list):
        return out
    for it in items:
        s = str(it).strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        for b in BANDS:
            key = b.replace("_", "")
            if s == key or key in s or s in key:
                out.add(b)
    return out


def _f1(pred: set[str], true: set[str]) -> float:
    if not pred and not true:
        return 1.0
    if not pred or not true:
        return 0.0
    tp = len(pred & true)
    prec = tp / len(pred)
    rec = tp / len(true)
    return 0.0 if (prec + rec) == 0 else 2 * prec * rec / (prec + rec)


def _sign(x: float) -> int:
    if abs(float(x)) < 1e-9:
        return 0
    return 1 if float(x) > 0 else -1


def _pred_sign(obj: dict[str, Any], key: str) -> int | None:
    v = obj.get(key)
    if v is None or v == "":
        return None
    try:
        return _sign(float(v))
    except (TypeError, ValueError):
        s = str(v).strip().lower()
        if s in {"-1", "neg", "negative", "bearish"}:
            return -1
        if s in {"1", "+1", "pos", "positive", "bullish"}:
            return 1
        if s in {"0", "zero", "flat", "neutral"}:
            return 0
    return None


def evaluate(models: list[str], sample_n: int, workers: int) -> None:
    cfg = load_experiment_config()
    df = _ensure_panel()
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    oos = _sample_oos(oos, sample_n if sample_n > 0 else None)
    print(f"Grounding workflow: OOS from {cut}, n={len(oos)}, models={models}")

    prompts = {
        "compiled": (PROMPT_DIR / "grounding_compiled.txt").read_text(encoding="utf-8"),
        "raw": (PROMPT_DIR / "grounding_raw.txt").read_text(encoding="utf-8"),
    }

    rows = []
    for model in models:
        for treatment in ("compiled", "raw"):
            items = list(oos.iterrows())

            def _one(pair, _t=treatment, _m=model):
                _, r = pair
                bundle = (
                    build_compiled_bundle(r) if _t == "compiled" else build_raw_bundle(r)
                )
                status = {
                    b: str(r.get(f"st_{b}") or "missing") for b in BANDS
                }
                true_missing = {b for b, st in status.items() if st == "missing"}
                true_ready = {b for b, st in status.items() if st == "ready"}
                thin = bool(
                    (build_compiled_bundle(r).get("world_model_index") or {}).get("thin_world")
                )
                true_m_sign = _sign(float(r.get("macro_tilt") or 0.0))
                true_a_sign = _sign(float(r.get("alt_tilt") or 0.0))
                prompt = prompts[_t].replace("{{ASSET}}", str(r["asset"])).replace(
                    "{{BUNDLE_JSON}}", json.dumps(bundle, default=str)
                )
                text = chat_text(_m, system=SYSTEM, user=prompt, max_tokens=2000)
                obj = _parse(text)
                suff = str(obj.get("data_sufficiency") or "").strip().lower()
                pred_missing = _norm_bands(obj.get("missing_bands"))
                pred_ready = _norm_bands(obj.get("ready_bands"))
                pm = _pred_sign(obj, "macro_tilt_sign")
                pa = _pred_sign(obj, "alt_tilt_sign")
                tilt_hits = 0
                tilt_n = 0
                for pred, true in ((pm, true_m_sign), (pa, true_a_sign)):
                    tilt_n += 1
                    if pred is not None and pred == true:
                        tilt_hits += 1
                return {
                    "date": str(pd.Timestamp(r["date"]).date()),
                    "asset": r["asset"],
                    "model": _m,
                    "treatment": _t,
                    "thin_world": int(thin),
                    "pred_sufficiency": suff,
                    "suff_correct": int(thin and suff == "insufficient"),
                    "missing_f1": round(_f1(pred_missing, true_missing), 4),
                    "ready_f1": round(_f1(pred_ready, true_ready), 4),
                    "tilt_sign_acc": round(tilt_hits / max(tilt_n, 1), 4),
                    "pred_missing": sorted(pred_missing),
                    "true_missing": sorted(true_missing),
                    "pred_ready": sorted(pred_ready),
                    "true_ready": sorted(true_ready),
                    "pred_macro_tilt_sign": pm,
                    "true_macro_tilt_sign": true_m_sign,
                    "pred_alt_tilt_sign": pa,
                    "true_alt_tilt_sign": true_a_sign,
                    "summary": str(obj.get("summary") or "")[:300],
                    "raw_head": "" if obj else (text or "")[:200],
                }

            with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
                futs = [ex.submit(_one, p) for p in items]
                results = [f.result() for f in as_completed(futs)]
            results.sort(key=lambda x: (x["date"], x["asset"]))
            (TRANSCRIPT_DIR / f"{model}_grounding_{treatment}.jsonl").write_text(
                "\n".join(json.dumps(t) for t in results) + "\n", encoding="utf-8"
            )
            n = len(results) or 1
            row = {
                "model": model,
                "treatment": treatment,
                "n": len(results),
                "sufficiency_acc": round(sum(t["suff_correct"] for t in results) / n, 4),
                "missing_f1": round(sum(t["missing_f1"] for t in results) / n, 4),
                "ready_f1": round(sum(t["ready_f1"] for t in results) / n, 4),
                "tilt_sign_acc": round(sum(t["tilt_sign_acc"] for t in results) / n, 4),
            }
            rows.append(row)
            print(row)

    out = pd.DataFrame(rows)
    ICAIF_TAB.mkdir(parents=True, exist_ok=True)
    for d in (TAB, ICAIF_TAB):
        out.to_csv(d / "table_llm_grounding_live.csv", index=False)
        out.to_csv(d / "table_llm_grounding_workflow.csv", index=False)
    print(out.to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="World-state grounding workflow eval")
    ap.add_argument("--models", type=str, required=True)
    ap.add_argument("--sample-n", type=int, default=50)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    evaluate([m.strip() for m in a.models.split(",") if m.strip()], a.sample_n, a.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
