#!/usr/bin/env python3
"""Offline soft evidence-alignment rate from frozen LLM stress transcripts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

TRANSCRIPT_DIR = Path(__file__).resolve().parent / "transcripts"
SEE = Path(__file__).resolve().parents[2] / "icaif26_see" / "tables"
TAB = Path(__file__).resolve().parents[2] / "tables"

CUE = re.compile(
    r"\b(exchange|macro|alternative|macro[_\s-]?tilt|alt[_\s-]?tilt|mom5|"
    r"should_ai_abstain|thin[_\s-]?world|wmi|missing|ready|evidence|"
    r"band:|tilt:)\b",
    re.I,
)
VENDORS = ("gpt-5.4-mini", "deepseek-v4-flash", "glm-5.2", "gemini-3.5-flash-lite")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _score(recs: list[dict]) -> tuple[float, float, int]:
    n = len(recs)
    if not n:
        return float("nan"), float("nan"), 0
    bound = sum(1 for r in recs if CUE.search(str(r.get("rationale") or "")))
    abstain = sum(1 for r in recs if str(r.get("action") or "").lower() == "abstain")
    return round(bound / n, 4), round(abstain / n, 4), n


def main() -> None:
    rows = []
    for model in VENDORS:
        mapping = {
            "compiled": TRANSCRIPT_DIR / f"{model}.jsonl",
            "ungated": TRANSCRIPT_DIR / f"{model}_ungated100.jsonl",
            "raw": TRANSCRIPT_DIR / f"{model}_full_raw.ckpt.jsonl",
        }
        for treatment, path in mapping.items():
            recs = _load(path)
            # For raw, subsample first 100 of full-OOS for a fair-ish stress compare
            if treatment == "raw" and len(recs) > 100:
                recs = recs[:100]
            soft, abs_rate, n = _score(recs)
            if n == 0:
                continue
            rows.append(
                {
                    "model": model,
                    "treatment": treatment,
                    "n": n,
                    "soft_ear": soft,
                    "abstain_rate": abs_rate,
                    "source": path.name,
                }
            )
    df = pd.DataFrame(rows)
    means = {
        t: round(float(g["soft_ear"].mean()), 4) for t, g in df.groupby("treatment")
    } if not df.empty else {}
    summary = {
        "definition": (
            "soft_ear = share of rationales mentioning disclosed band/tilt/quality/"
            "evidence cues (offline transcript audit; not strict evidence_id match)."
        ),
        "stress_means": means,
        "note": (
            "Thin-day harness ear_proxy=1.0 remains the Compiled contract proxy "
            "(abstain when flagged). soft_ear audits free-text binding."
        ),
    }
    for d in (TAB, SEE):
        d.mkdir(parents=True, exist_ok=True)
        df.to_csv(d / "table_soft_ear_stress100.csv", index=False)
        (d / "table_soft_ear_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
    print(df.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
