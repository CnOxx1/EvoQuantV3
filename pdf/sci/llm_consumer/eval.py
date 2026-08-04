#!/usr/bin/env python3
"""Evaluate Compiled vs Raw information sets for configured LLM consumers.

Default providers are deterministic mocks (no API keys). Economic metrics mirror
the paper (CRRA CE γ=2, abstain rate). Primary paper identification is unchanged.
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
PROMPT_DIR = Path(__file__).resolve().parent / "prompts" / "frozen"
TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"
TAB.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def _load_prompt(treatment: str) -> str:
    path = PROMPT_DIR / ("compiled.txt" if treatment == "compiled" else "raw.txt")
    return path.read_text(encoding="utf-8")


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_compiled_bundle(row: pd.Series) -> dict[str, Any]:
    wmi = float(row.get("WMI") or 0.0)
    ac = float(row.get("ACWMI") or row.get("ACWMI_world") or 0.0)
    thr = 0.25
    return {
        "date": str(pd.Timestamp(row["date"]).date()),
        "asset": row["asset"],
        "mom5": float(row.get("mom5") or 0.0),
        "macro_tilt": float(row.get("macro_tilt") or 0.0),
        "alt_tilt": float(row.get("alt_tilt") or 0.0),
        "cascade_p": float(row.get("cascade_p") or 0.0),
        "detected_regime": row.get("detected_regime"),
        "B_hier": float(row.get("B_hier") or 0.0),
        "abstain_threshold": thr,
        "world_model_index": {
            "wmi": wmi,
            "acwmi": ac,
            "should_ai_abstain": bool(ac < thr or wmi < 0.2),
            "index_mode": "acwmi",
        },
        "band_status": {
            "exchange": row.get("st_exchange"),
            "macro": row.get("st_macro"),
            "alternative": row.get("st_alternative"),
        },
    }


def build_raw_bundle(row: pd.Series) -> dict[str, Any]:
    return {
        "date": str(pd.Timestamp(row["date"]).date()),
        "asset": row["asset"],
        "mom5": float(row.get("mom5") or 0.0),
        "recent_ret": float(row.get("ret") or 0.0),
        "noise_bit": abs(hash(str(row.get("asset")))) % 2,
    }


def _ensure_panel() -> pd.DataFrame:
    panel_path = TAB / "panel_simulation.csv"
    if panel_path.exists():
        return pd.read_csv(panel_path, parse_dates=["date"])
    pit_path = DATA / "pit_multiband_panel.csv"
    if not pit_path.exists():
        raise SystemExit("Need pdf/tables/panel_simulation.csv or pit panel; run paper-lab first")
    # Minimal synthetic engines for smoke when full panel absent
    pit = pd.read_csv(pit_path, parse_dates=["date"])
    pit["mom5"] = np.sign(pit.groupby("asset")["ret"].transform(lambda s: s.shift(1).rolling(5).mean())).fillna(0.0)
    pit["macro_tilt"] = 0.0
    pit["alt_tilt"] = 0.0
    pit["cascade_p"] = 0.2
    pit["detected_regime"] = "range"
    pit["ACWMI"] = pit.get("ACWMI_world", 0.3)
    pit["signal"] = pit["mom5"]
    pit["S"] = 0.5
    pit["C"] = 0.5
    return pit


def evaluate_model(df: pd.DataFrame, model_name: str) -> dict[str, Any]:
    provider = get_provider(model_name)
    rows_out = []
    transcripts = []
    for treatment in ("compiled", "raw"):
        template = _load_prompt(treatment)
        ph = _prompt_hash(template)
        positions = []
        abstains = []
        for _, r in df.iterrows():
            bundle = build_compiled_bundle(r) if treatment == "compiled" else build_raw_bundle(r)
            # Raw arm must not see day-t return as a feature (payoff leakage).
            if treatment == "raw":
                bundle.pop("recent_ret", None)
            prompt = template.replace("{{BUNDLE_JSON}}", json.dumps(bundle, default=str))
            dec = provider.decide(treatment=treatment, prompt=prompt, bundle=bundle)
            positions.append(dec.position())
            abstains.append(int(dec.is_abstain()))
            transcripts.append(
                {
                    "date": bundle["date"],
                    "asset": bundle["asset"],
                    "model": model_name,
                    "treatment": treatment,
                    "prompt_hash": ph,
                    "action": dec.action,
                    "confidence": dec.confidence,
                    "position": dec.position(),
                    "rationale": dec.rationale,
                }
            )
        pos = pd.Series(positions, index=df.index, dtype=float)
        st = portfolio_stats(df, pos)
        rows_out.append(
            {
                "model": model_name,
                "treatment": treatment,
                "ann_return": round(st["ann_return"], 4),
                "Sharpe": round(st["Sharpe"], 3),
                "CE": round(st["CE"], 4),
                "abstain_rate": round(float(np.mean(abstains)), 4),
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
    }
    (TRANSCRIPT_DIR / f"{model_name}.jsonl").write_text(
        "\n".join(json.dumps(t) for t in transcripts) + "\n",
        encoding="utf-8",
    )
    return {"rows": rows_out, "delta": delta}


def main() -> int:
    cfg = load_experiment_config()
    models = list(cfg["llm_consumer"]["models"])
    df = _ensure_panel()
    # Evaluate on OOS only (thresholds/prompts frozen)
    _, oos, cut = split_is_oos(df, is_frac=float(cfg["split"]["is_frac"]))
    print("LLM consumer OOS from", cut, "n=", len(oos), "models=", models)

    all_rows = []
    deltas = []
    for m in models:
        res = evaluate_model(oos, m)
        all_rows.extend(res["rows"])
        deltas.append(res["delta"])
        print(m, res["delta"])

    econ = pd.DataFrame(all_rows)
    delta_df = pd.DataFrame(deltas)
    econ.to_csv(TAB / "table_llm_consumer_econ.csv", index=False)
    delta_df.to_csv(TAB / "table_llm_consumer_deltas.csv", index=False)
    summary = {
        "protocol": "pdf/sci/llm_consumer/protocol.md",
        "role": "secondary_ai_consumer_validation",
        "is_oos_cut": str(pd.Timestamp(cut).date()),
        "n_oos_rows": int(len(oos)),
        "models": models,
        "mean_dCE": round(float(delta_df["dCE_compiled_minus_raw"].mean()), 4),
        "deltas": deltas,
        "experiment_config_hash": cfg["_content_hash"],
    }
    (TAB / "table_llm_consumer_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
