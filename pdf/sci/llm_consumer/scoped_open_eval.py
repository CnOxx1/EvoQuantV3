#!/usr/bin/env python3
"""Live LLM eval under the scoped-archive production valve (Paper B RQ3a).

Unlike the frozen full-schema stress arms (RQ1--RQ2), bundles here expose
scoped WMI + archive_complete so the production valve opens on 3/3-ready days.
Primary metrics: valve obedience on closed days; open-day usability vs Raw.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pdf.sci.experiment_config import load_experiment_config
from pdf.sci.llm_consumer.eval import (  # noqa: E402
    DURABLE_BANDS,
    PROMPT_DIR,
    TRANSCRIPT_DIR,
    _ensure_panel,
    _load_prompt,
    _prompt_hash,
    build_raw_bundle,
)
from pdf.sci.llm_consumer.providers.mock import get_provider
from pdf.sci.run_jf_experiments import portfolio_stats, split_is_oos
from logic_layer.time_slice.world_quality import scoped_wmi_from_statuses

TAB = ROOT / "pdf" / "tables"
SEE_TAB = ROOT / "pdf" / "icaif26_see" / "tables"
ICAIF_TAB = ROOT / "pdf" / "icaif26" / "tables"
CUT = "2026-01-16"
MODELS = (
    "gpt-5.4-mini",
    "deepseek-v4-flash",
    "glm-5.2",
    "gemini-3.5-flash-lite",
)


def _attach_scoped(df: pd.DataFrame) -> pd.DataFrame:
    scoped_path = TAB / "panel_scoped_wmi.csv"
    if scoped_path.exists():
        sc = pd.read_csv(scoped_path, parse_dates=["date"])
        keep = [
            "date",
            "asset",
            "WMI_scoped",
            "should_ai_abstain_scoped",
            "valve_open_scoped",
            "n_ready_scoped",
        ]
        out = df.merge(sc[keep], on=["date", "asset"], how="left")
        if out["WMI_scoped"].notna().all():
            return out
    # recompute if join incomplete
    rows = []
    for _, r in df.iterrows():
        st = {b: str(r.get(f"st_{b}", "missing")) for b in DURABLE_BANDS}
        # include missing schema bands for full contrast if present
        for b in (
            "news",
            "onchain",
            "options",
            "tokenomics",
            "event_calendar",
        ):
            st[b] = str(r.get(f"st_{b}", "missing"))
        q = scoped_wmi_from_statuses(st, scope="eval_archive")
        rows.append(q)
    out = df.copy()
    out["WMI_scoped"] = [r["wmi"] for r in rows]
    out["should_ai_abstain_scoped"] = [r["should_ai_abstain"] for r in rows]
    out["valve_open_scoped"] = [not r["should_ai_abstain"] for r in rows]
    out["n_ready_scoped"] = [r["n_ready"] for r in rows]
    return out


def build_scoped_compiled_bundle(row: pd.Series) -> dict[str, Any]:
    """Compiled bundle with production-valve fields (scoped archive)."""
    bands = {k: str(row.get(f"st_{k}") or "missing") for k in DURABLE_BANDS}
    n_ready = sum(1 for v in bands.values() if v == "ready")
    n_limited = sum(1 for v in bands.values() if v == "limited")
    n_missing = sum(1 for v in bands.values() if v == "missing")
    wmi_scoped = float(row.get("WMI_scoped") or 0.0)
    should_abs = bool(row.get("should_ai_abstain_scoped"))
    if "should_ai_abstain_scoped" not in row.index or pd.isna(row.get("should_ai_abstain_scoped")):
        should_abs = not bool(row.get("valve_open_scoped"))
    wmi_full = float(row.get("WMI") or 0.0)
    evidence_ids = [f"band:{k}:{bands[k]}" for k in DURABLE_BANDS]
    evidence_ids += [
        f"tilt:macro:{float(row.get('macro_tilt') or 0.0)}",
        f"tilt:alt:{float(row.get('alt_tilt') or 0.0)}",
        f"engine:mom5:{float(row.get('mom5') or 0.0)}",
    ]
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
        "wmi_abstain_threshold": 0.2,
        "completeness": {
            "n_ready": n_ready,
            "n_limited": n_limited,
            "n_missing": n_missing,
            "ready_share": float(n_ready / max(n_ready + n_limited + n_missing, 1)),
            "archive_bands": list(DURABLE_BANDS),
            "archive_complete": bool(n_ready == 3),
            "missing_bands_disclosed": True,
        },
        "world_model_index": {
            "band_scope": "eval_archive",
            "wmi": wmi_scoped,
            "archive_complete": bool(n_ready == 3),
            "should_ai_abstain": should_abs,
            "thin_world": should_abs,
            "wmi_abstain_threshold": 0.2,
            "full_schema_wmi": wmi_full,
            "index_mode": "wmi",
        },
        "band_status": bands,
        "audit": {
            "evidence_ids": evidence_ids,
            "ear_required": True,
            "bundle_role": "scoped_production_valve_for_public_llm",
        },
    }


def build_scoped_ungated_bundle(row: pd.Series) -> dict[str, Any]:
    bundle = build_scoped_compiled_bundle(row)
    wmi = dict(bundle.get("world_model_index") or {})
    wmi.pop("should_ai_abstain", None)
    wmi.pop("thin_world", None)
    wmi["note"] = "numeric_quality_only_no_hard_abstain_flag"
    bundle["world_model_index"] = wmi
    return bundle


def build_scoped_hpo_bundle(row: pd.Series) -> dict[str, Any]:
    """Hard-prompt-only on scoped numeric WMI (no boolean / thin_world)."""
    bundle = build_scoped_ungated_bundle(row)
    wmi = dict(bundle.get("world_model_index") or {})
    wmi["note"] = "hpo_hard_prompt_numeric_threshold_no_boolean"
    # Ensure threshold fields remain readable for the frozen HPO prompt.
    wmi.setdefault("wmi_abstain_threshold", 0.2)
    bundle["world_model_index"] = wmi
    return bundle


def _build(treatment: str, row: pd.Series) -> dict[str, Any]:
    if treatment == "compiled":
        return build_scoped_compiled_bundle(row)
    if treatment == "ungated":
        return build_scoped_ungated_bundle(row)
    if treatment == "hpo":
        return build_scoped_hpo_bundle(row)
    if treatment == "raw":
        return build_raw_bundle(row)
    raise KeyError(treatment)


def _sample_open_closed(
    oos: pd.DataFrame,
    *,
    n_open: int,
    n_closed: int,
    seed: int = 7,
) -> pd.DataFrame:
    open_df = oos[oos["valve_open_scoped"].astype(bool)].copy()
    closed_df = oos[~oos["valve_open_scoped"].astype(bool)].copy()
    rng = np.random.default_rng(seed)

    def _take(frame: pd.DataFrame, n: int) -> pd.DataFrame:
        if len(frame) == 0 or n <= 0:
            return frame.iloc[0:0].copy()
        n = min(n, len(frame))
        idx = rng.choice(frame.index.to_numpy(), size=n, replace=False)
        return frame.loc[sorted(idx)].copy()

    parts = [_take(open_df, n_open), _take(closed_df, n_closed)]
    out = pd.concat(parts, axis=0).sort_values(["date", "asset"]).reset_index(drop=True)
    return out


def _evaluate(
    df: pd.DataFrame,
    model_name: str,
    *,
    treatments: tuple[str, ...],
    workers: int,
    tag: str,
) -> list[dict[str, Any]]:
    provider = get_provider(model_name)
    transcripts: list[dict[str, Any]] = []
    for treatment in treatments:
        template = _load_prompt(treatment)
        ph = _prompt_hash(template)
        items = list(df.iterrows())
        ckpt_path = TRANSCRIPT_DIR / f"{model_name}_{tag}_{treatment}.ckpt.jsonl"
        done: dict[tuple[str, str], dict] = {}
        if ckpt_path.exists():
            for line in ckpt_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not str(rec.get("rationale", "")).startswith("provider-error"):
                    done[(rec["date"], rec["asset"])] = rec
            if done:
                print(f"  resume {model_name}/{treatment}: {len(done)}", flush=True)
        lock = threading.Lock()
        fh = ckpt_path.open("a", encoding="utf-8")

        def _one(pair, _t=treatment, _tmpl=template, _ph=ph):
            idx, r = pair
            bundle = _build(_t, r)
            key = (bundle["date"], str(bundle["asset"]))
            if key in done:
                out = dict(done[key])
                out["prompt_hash"] = _ph
                out["valve_open"] = bool(r["valve_open_scoped"])
                return idx, out
            dec = provider.decide(
                treatment=_t,
                prompt=_tmpl.replace("{{BUNDLE_JSON}}", json.dumps(bundle, default=str)),
                bundle=bundle,
            )
            out = {
                "date": bundle["date"],
                "asset": bundle["asset"],
                "model": model_name,
                "treatment": _t,
                "prompt_hash": _ph,
                "action": dec.action,
                "confidence": dec.confidence,
                "position": dec.position(),
                "rationale": dec.rationale,
                "is_abstain": int(dec.is_abstain()),
                "valve_open": bool(r["valve_open_scoped"]),
                "WMI_scoped": float(r.get("WMI_scoped") or 0.0),
            }
            with lock:
                fh.write(json.dumps(out) + "\n")
                fh.flush()
            return idx, out

        if workers <= 1:
            results = [_one(p) for p in items]
        else:
            results = []
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = [ex.submit(_one, p) for p in items]
                for n, fut in enumerate(as_completed(futs), 1):
                    results.append(fut.result())
                    if n % 50 == 0:
                        print(f"  {model_name}/{treatment}: {n}/{len(items)}", flush=True)
            order = {idx: i for i, (idx, _) in enumerate(items)}
            results.sort(key=lambda x: order.get(x[0], 0))
        fh.close()
        for _, row_t in results:
            transcripts.append(row_t)
    return transcripts


def _summarize(df: pd.DataFrame, transcripts: list[dict], model: str) -> list[dict]:
    rows = []
    for treatment in ("compiled", "ungated", "raw"):
        sub_t = [t for t in transcripts if t["treatment"] == treatment and t["model"] == model]
        if not sub_t:
            continue
        # align to df by (date, asset)
        key_to_idx = {
            (str(pd.Timestamp(r["date"]).date()), str(r["asset"])): idx
            for idx, r in df.iterrows()
        }
        for slice_name, pred in (
            ("all", lambda t: True),
            ("open", lambda t: bool(t.get("valve_open"))),
            ("closed", lambda t: not bool(t.get("valve_open"))),
        ):
            ts = [t for t in sub_t if pred(t)]
            if not ts:
                rows.append(
                    {
                        "model": model,
                        "treatment": treatment,
                        "slice": slice_name,
                        "n": 0,
                    }
                )
                continue
            idxs = [key_to_idx[(t["date"], t["asset"])] for t in ts if (t["date"], t["asset"]) in key_to_idx]
            sub = df.loc[idxs]
            pos = pd.Series([float(t.get("position") or 0.0) for t in ts], index=sub.index)
            st = portfolio_stats(sub, pos)
            abst = float(np.mean([t["action"] == "abstain" for t in ts]))
            rows.append(
                {
                    "model": model,
                    "treatment": treatment,
                    "slice": slice_name,
                    "n": len(ts),
                    "abstain": round(abst, 4),
                    "CE": round(float(st["CE"]), 4),
                    "Sharpe": round(float(st["Sharpe"]), 3),
                    "ann_return": round(float(st["ann_return"]), 4),
                }
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Scoped-open production-valve LLM eval")
    p.add_argument("--n-open", type=int, default=70)
    p.add_argument("--n-closed", type=int, default=30)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--tag", type=str, default="scoped_open")
    p.add_argument(
        "--models",
        type=str,
        default=",".join(MODELS),
    )
    p.add_argument(
        "--treatments",
        type=str,
        default="compiled,ungated,raw",
    )
    args = p.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    treatments = tuple(t.strip() for t in args.treatments.split(",") if t.strip())

    cfg = load_experiment_config()
    panel = _attach_scoped(_ensure_panel())
    _, oos, cut = split_is_oos(panel, is_frac=float(cfg["split"]["is_frac"]))
    oos = oos[oos["date"] >= CUT].copy() if hasattr(oos["date"].iloc[0], "strftime") else oos
    sample = _sample_open_closed(
        oos, n_open=int(args.n_open), n_closed=int(args.n_closed), seed=7
    )
    print(
        f"Scoped-open LLM eval cut={cut} sample_n={len(sample)} "
        f"open={int(sample['valve_open_scoped'].sum())} "
        f"closed={int((~sample['valve_open_scoped']).sum())} "
        f"models={models} treatments={treatments}",
        flush=True,
    )

    all_rows: list[dict] = []
    all_transcripts: list[dict] = []
    for model in models:
        tr = _evaluate(
            sample,
            model,
            treatments=treatments,
            workers=max(1, int(args.workers)),
            tag=args.tag,
        )
        all_transcripts.extend(tr)
        rows = _summarize(sample, tr, model)
        all_rows.extend(rows)
        for r in rows:
            if r.get("n"):
                print(
                    f"{r['model']}/{r['treatment']}/{r['slice']}: "
                    f"n={r['n']} abs={r.get('abstain')} CE={r.get('CE')} Sharpe={r.get('Sharpe')}",
                    flush=True,
                )

    out = pd.DataFrame(all_rows)
    # wide contrast on open slice
    contrast_rows = []
    for model in models:
        def _get(treatment: str, slice_name: str = "open") -> dict:
            hit = out[
                (out["model"] == model)
                & (out["treatment"] == treatment)
                & (out["slice"] == slice_name)
            ]
            return hit.iloc[0].to_dict() if len(hit) else {}

        c, u, r = _get("compiled"), _get("ungated"), _get("raw")
        h = _get("hpo")
        c_closed = _get("compiled", "closed")
        h_closed = _get("hpo", "closed")
        contrast_rows.append(
            {
                "model": model,
                "n_open": int(c.get("n") or h.get("n") or 0),
                "abs_C_open": c.get("abstain"),
                "CE_C_open": c.get("CE"),
                "Sharpe_C_open": c.get("Sharpe"),
                "abs_HPO_open": h.get("abstain"),
                "abs_U_open": u.get("abstain"),
                "CE_U_open": u.get("CE"),
                "abs_R_open": r.get("abstain"),
                "CE_R_open": r.get("CE"),
                "dCE_C_minus_R_open": (
                    None
                    if c.get("CE") is None or r.get("CE") is None
                    else round(float(c["CE"]) - float(r["CE"]), 4)
                ),
                "abs_C_closed": c_closed.get("abstain"),
                "abs_HPO_closed": h_closed.get("abstain"),
                "n_closed": int(c_closed.get("n") or h_closed.get("n") or 0),
            }
        )
    contrast = pd.DataFrame(contrast_rows) if contrast_rows else pd.DataFrame()

    def _mean_col(name: str):
        if contrast.empty or name not in contrast.columns:
            return None
        s = contrast[name].dropna()
        return None if s.empty else round(float(s.mean()), 4)

    summary = {
        "protocol": "scoped_archive_production_valve_llm",
        "band_scope": "eval_archive",
        "n_open_target": int(args.n_open),
        "n_closed_target": int(args.n_closed),
        "n_sample": int(len(sample)),
        "models": models,
        "treatments": list(treatments),
        "mean_dCE_C_minus_R_open": _mean_col("dCE_C_minus_R_open"),
        "mean_abs_C_closed": _mean_col("abs_C_closed"),
        "mean_abs_HPO_closed": _mean_col("abs_HPO_closed"),
        "mean_abs_C_open": _mean_col("abs_C_open"),
        "mean_abs_HPO_open": _mean_col("abs_HPO_open"),
        "claim_boundary": (
            "Open-day LLM usability under scoped production valve; "
            "not a generative world-model or alpha claim."
        ),
    }

    for d in (TAB, SEE_TAB, ICAIF_TAB):
        d.mkdir(parents=True, exist_ok=True)
        out.to_csv(d / "table_llm_scoped_open_slices.csv", index=False)
        contrast.to_csv(d / "table_llm_scoped_open_contrast.csv", index=False)
        (d / "table_llm_scoped_open_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    # persist sample keys for reproducibility
    sample_keys = sample[["date", "asset", "valve_open_scoped", "WMI_scoped"]].copy()
    sample_keys["date"] = pd.to_datetime(sample_keys["date"]).dt.strftime("%Y-%m-%d")
    sample_keys.to_csv(TAB / "table_llm_scoped_open_sample.csv", index=False)
    sample_keys.to_csv(SEE_TAB / "table_llm_scoped_open_sample.csv", index=False)

    print(json.dumps(summary, indent=2))
    print(contrast.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
