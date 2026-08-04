#!/usr/bin/env python3
"""Band-thick split of full-OOS LLM checkpoints (half-B defensive probe).

Splits OOS asset-days by archive readiness (3/3 ready vs exchange gap) and
reports abstain / CE / Sharpe for Compiled, Ungated, and Raw. Does not call
any LLM API.

This supports the trustworthy-interface claim: even when all three archive
bands are ready, WMI still marks the scarce panel thin, Raw over-acts and
often loses, and Compiled continues to refuse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.eval import TRANSCRIPT_DIR, _ensure_panel, build_compiled_bundle
from pdf.sci.run_jf_experiments import portfolio_stats, split_is_oos

TAB = ROOT / "pdf" / "tables"
ICAIF_TAB = ROOT / "pdf" / "icaif26" / "tables"
MODELS = (
    "gpt-5.4-mini",
    "deepseek-v4-flash",
    "glm-5.2",
    "gemini-3.5-flash-lite",
)


def _load(model: str, treatment: str) -> dict[tuple[str, str], dict]:
    path = TRANSCRIPT_DIR / f"{model}_full_{treatment}.ckpt.jsonl"
    out: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if str(rec.get("rationale", "")).startswith("provider-error"):
            continue
        out[(str(rec["date"]), str(rec["asset"]))] = rec
    return out


def main() -> int:
    cfg = load_experiment_config()
    df = _ensure_panel()
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    meta = {}
    for idx, r in oos.iterrows():
        b = build_compiled_bundle(r)
        key = (str(pd.Timestamp(r["date"]).date()), str(r["asset"]))
        meta[key] = {
            "idx": idx,
            "band_thick": b["completeness"]["n_ready"] == 3,
            "thin_world": bool(b["world_model_index"]["thin_world"]),
        }
    print(f"OOS from {cut}; band_thick share={np.mean([m['band_thick'] for m in meta.values()]):.3f}")
    print(f"thin_world share={np.mean([m['thin_world'] for m in meta.values()]):.3f}")

    rows = []
    for model in MODELS:
        for treatment in ("compiled", "ungated", "raw"):
            ckpt = _load(model, treatment)
            for thick_flag, label in ((True, "band_thick"), (False, "band_thin")):
                keys = [k for k in ckpt if k in meta and meta[k]["band_thick"] is thick_flag]
                if not keys:
                    rows.append(
                        {
                            "model": model,
                            "treatment": treatment,
                            "slice": label,
                            "n": 0,
                        }
                    )
                    continue
                abst = float(np.mean([ckpt[k]["action"] == "abstain" for k in keys]))
                sub = oos.loc[[meta[k]["idx"] for k in keys]]
                pos = pd.Series(
                    [float(ckpt[k].get("position") or 0.0) for k in keys],
                    index=sub.index,
                )
                st = portfolio_stats(sub, pos)
                rows.append(
                    {
                        "model": model,
                        "treatment": treatment,
                        "slice": label,
                        "n": len(keys),
                        "abstain": round(abst, 4),
                        "CE": round(float(st["CE"]), 4),
                        "Sharpe": round(float(st["Sharpe"]), 3),
                    }
                )
                print(
                    f"{model}/{treatment}/{label}: n={len(keys)} abs={abst:.3f} "
                    f"CE={st['CE']:.3f}"
                )

    out = pd.DataFrame(rows)
    TAB.mkdir(parents=True, exist_ok=True)
    ICAIF_TAB.mkdir(parents=True, exist_ok=True)
    out.to_csv(TAB / "table_llm_band_thick_split.csv", index=False)
    out.to_csv(ICAIF_TAB / "table_llm_band_thick_split.csv", index=False)
    print("wrote table_llm_band_thick_split.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
