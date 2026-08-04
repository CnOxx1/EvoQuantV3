#!/usr/bin/env python3
"""Blind direct-ask arm: 'How should I trade BTC today?' with no data feed.

The product-realistic control requested for the ICAIF paper: the same live
LLMs, same 100 OOS asset-days, same action schema — but the prompt contains
only the date and asset name (no world bundle, no momentum, no quality
fields). Contrast: Compiled (world model) vs Blind (no world model at all).

Usage:
  python -m pdf.sci.llm_consumer.blind_eval \
      --models gpt-5.4-mini,deepseek-v4-flash,glm-5.2,gemini-3.5-flash-lite \
      --sample-n 100 --workers 6
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.eval import (
    _ensure_panel,
    _sample_oos,
    build_compiled_bundle,
)
from pdf.sci.llm_consumer.providers.openai_compatible import OpenAICompatibleProvider
from pdf.sci.run_jf_experiments import portfolio_stats, split_is_oos

SCI = Path(__file__).resolve().parents[1]
TAB = SCI.parent / "tables"
ICAIF_TAB = SCI.parent / "icaif26" / "tables"
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "frozen"
TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"


def evaluate(models: list[str], sample_n: int, workers: int) -> None:
    cfg = load_experiment_config()
    df = _ensure_panel()
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    oos = _sample_oos(oos, sample_n if sample_n > 0 else None)
    print(f"Blind direct-ask eval: OOS from {cut}, n={len(oos)}, models={models}")

    template = (PROMPT_DIR / "blind.txt").read_text(encoding="utf-8")
    rows = []
    for model in models:
        provider = OpenAICompatibleProvider(model)
        items = list(oos.iterrows())

        def _one(pair, _m=model, _p=provider):
            idx, r = pair
            date = str(pd.Timestamp(r["date"]).date())
            prompt = template.replace("{{DATE}}", date).replace("{{ASSET}}", str(r["asset"]))
            dec = _p.decide(treatment="blind", prompt=prompt, bundle={})
            thin = bool(
                (build_compiled_bundle(r).get("world_model_index") or {}).get("thin_world")
            )
            return idx, {
                "date": date,
                "asset": str(r["asset"]),
                "model": _m,
                "treatment": "blind",
                "action": dec.action,
                "confidence": dec.confidence,
                "position": dec.position(),
                "rationale": dec.rationale,
                "thin_world": int(thin),
                "is_abstain": int(dec.is_abstain()),
            }

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = [ex.submit(_one, p) for p in items]
            results = [f.result() for f in as_completed(futs)]
        order = {idx: n for n, (idx, _) in enumerate(items)}
        results.sort(key=lambda x: order.get(x[0], 0))
        transcripts = [t for _, t in results]
        (TRANSCRIPT_DIR / f"{model}_blind.jsonl").write_text(
            "\n".join(json.dumps(t) for t in transcripts) + "\n", encoding="utf-8"
        )

        pos = pd.Series([t["position"] for t in transcripts], index=oos.index, dtype=float)
        st = portfolio_stats(oos, pos)
        n = len(transcripts) or 1
        thin_days = [t for t in transcripts if t["thin_world"]]
        row = {
            "model": model,
            "treatment": "blind",
            "n": len(transcripts),
            "abstain_rate": round(float(np.mean([t["is_abstain"] for t in transcripts])), 4),
            "thin_world_abstain_rate": round(
                float(np.mean([t["is_abstain"] for t in thin_days])), 4
            )
            if thin_days
            else float("nan"),
            "bullish": round(sum(t["action"] == "bullish" for t in transcripts) / n, 4),
            "bearish": round(sum(t["action"] == "bearish" for t in transcripts) / n, 4),
            "neutral": round(sum(t["action"] == "neutral" for t in transcripts) / n, 4),
            "Sharpe": round(st["Sharpe"], 3),
            "CE": round(st["CE"], 4),
        }
        rows.append(row)
        print(row)

    out = pd.DataFrame(rows)
    ICAIF_TAB.mkdir(parents=True, exist_ok=True)
    for d in (TAB, ICAIF_TAB):
        out.to_csv(d / "table_llm_blind_live.csv", index=False)
    print(out.to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Blind direct-ask LLM eval")
    ap.add_argument("--models", type=str, required=True)
    ap.add_argument("--sample-n", type=int, default=100)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args(argv)
    evaluate([m.strip() for m in a.models.split(",") if m.strip()], a.sample_n, a.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
