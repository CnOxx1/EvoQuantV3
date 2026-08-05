#!/usr/bin/env python3
"""One-command paper lab: archive → PIT panel → JF experiments → PDF.

Uses production BandPIT / WMI-ACWMI / availability helpers wherever possible.
Subcommands can be run individually for iterative manuscript work.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCI = Path(__file__).resolve().parent
DATA = SCI.parent / "data"


def _run(script: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(SCI / script), *(extra or [])]
    print("+", " ".join(cmd), flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    # Paper archives live in domain-split SQLite files (exchange/market/analytics).
    # Cloud envs sometimes export DB_SPLIT_ENABLED=0, which collapses all domains
    # onto empty crypto_data.db and zeros band readiness — force split for paper lab.
    env["DB_SPLIT_ENABLED"] = "1"
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def cmd_smoke() -> int:
    """Import/production API smoke without requiring a full archive."""
    sys.path.insert(0, str(ROOT))
    from config.settings import (
        ACWMI_ABSTAIN_THRESHOLD,
        EVAL_ARCHIVE_BANDS,
        WMI_ABSTAIN_THRESHOLD,
        WORLD_MODEL_BAND_SCOPE,
        WORLD_MODEL_INDEX_MODE,
    )
    from data_layer.data_quality.availability import (
        load_availability_shocks,
        tag_availability_shock_metadata,
    )
    from logic_layer.ai_market_context.service import AIMarketContextService
    from logic_layer.decision_handoff.service import DecisionHandoffService
    from logic_layer.time_slice.band_pit import BandPITService
    from logic_layer.time_slice.service import TimeSliceService
    from logic_layer.time_slice.world_quality import scoped_wmi_from_statuses

    assert "band_readiness" in TimeSliceService.DOMAINS
    meta = tag_availability_shock_metadata(band="macro", planted=False)
    assert "availability_shock" in meta
    wmi = AIMarketContextService._compute_world_model_index(
        coverage_score=0.7,
        pipeline_latency_context={"summary": {"total_domains": 8, "fresh": 5, "acceptable": 2}},
        data_quality_flag="partial",
        data_quality_flags=["thin_macro"],
        signal_integrity=0.8,
        cross_evidence=0.6,
        index_mode="acwmi",
    )
    assert "acwmi" in wmi
    assert wmi["index_mode"] == "acwmi"
    assert "acwmi_input_source" in wmi
    # Explicit proxy vs paper disclosure on sample
    s, c, src = AIMarketContextService._acwmi_proxies(
        asset_readiness_row={"ready_band_count": 3, "limited_band_count": 1, "missing_band_count": 4},
        data_quality_flags=[],
    )
    assert src == "production_proxy" and 0 < s <= 1 and 0 < c <= 1
    # Scoped archive opens; full schema stays closed on the same statuses.
    ready3 = {
        "exchange": "ready",
        "macro": "ready",
        "alternative": "ready",
        "news": "missing",
        "onchain": "missing",
        "options": "missing",
        "tokenomics": "missing",
        "event_calendar": "missing",
    }
    scoped_open = scoped_wmi_from_statuses(ready3, scope="eval_archive")
    full_closed = scoped_wmi_from_statuses(ready3, scope="full")
    assert scoped_open["should_ai_abstain"] is False
    assert full_closed["should_ai_abstain"] is True
    handoff = DecisionHandoffService().act(
        {
            "macro_tilt": 1.0,
            "alt_tilt": 1.0,
            "world_model_index": scoped_open,
            "audit": {"evidence_ids": ["band:exchange:ready"]},
        }
    )
    assert handoff["handoff"] == "acted"
    # BandPIT + shocks tolerate empty DBs
    _ = BandPITService().get_band_readiness_at("2026-01-01T00:00:00", symbols=["BTC/USDT"])
    _ = load_availability_shocks(limit=5)
    print(
        json.dumps(
            {
                "ok": True,
                "WORLD_MODEL_INDEX_MODE": WORLD_MODEL_INDEX_MODE,
                "WORLD_MODEL_BAND_SCOPE": WORLD_MODEL_BAND_SCOPE,
                "EVAL_ARCHIVE_BANDS": list(EVAL_ARCHIVE_BANDS),
                "WMI_ABSTAIN_THRESHOLD": WMI_ABSTAIN_THRESHOLD,
                "ACWMI_ABSTAIN_THRESHOLD": ACWMI_ABSTAIN_THRESHOLD,
                "wmi_sample": wmi,
                "scoped_wmi_open": {
                    "wmi": scoped_open["wmi"],
                    "should_ai_abstain": scoped_open["should_ai_abstain"],
                },
                "full_schema_closed": {
                    "wmi": full_closed["wmi"],
                    "should_ai_abstain": full_closed["should_ai_abstain"],
                },
                "handoff_sample": handoff,
                "acwmi_proxy_smoke": {"S": s, "C": c, "source": src},
                "data_dir": str(DATA),
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="EvoQuant paper lab")
    p.add_argument(
        "step",
        nargs="?",
        default="all",
        choices=[
            "all",
            "smoke",
            "bootstrap",
            "pit",
            "pit-exp",
            "yahoo-exp",
            "reconcile",
            "llm-consumer",
            "scoped-handoff",
            "pdf",
            "experiments",
        ],
        help="Pipeline step (default: all = pit→pit-exp→llm→pdf; bootstrap is opt-in)",
    )
    p.add_argument(
        "--with-bootstrap",
        action="store_true",
        help="When step=all, also run multi-band archive bootstrap first",
    )
    args = p.parse_args()

    if args.step == "smoke":
        return cmd_smoke()
    if args.step == "bootstrap":
        return _run("bootstrap_multiband_archive.py")
    if args.step == "pit":
        return _run("build_pit_archive.py")
    if args.step == "pit-exp":
        return _run("run_pit_jf_experiments.py")
    if args.step == "yahoo-exp":
        return _run("run_jf_experiments.py")
    if args.step == "reconcile":
        return _run("reconcile_returns.py")
    if args.step == "llm-consumer":
        cmd = [sys.executable, "-m", "pdf.sci.llm_consumer.eval"]
        print("+", " ".join(cmd), flush=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        env["DB_SPLIT_ENABLED"] = "1"
        return subprocess.call(cmd, cwd=str(ROOT), env=env)
    if args.step == "scoped-handoff":
        return _run("scoped_wmi_handoff.py")
    if args.step == "pdf":
        # Prefer the complete JF/RFS manuscript renderer when present.
        full = SCI / "generate_full_manuscript_pdf.py"
        if full.exists():
            return _run("generate_full_manuscript_pdf.py")
        return _run("generate_sci_pdf.py")
    if args.step == "experiments":
        return _run("run_paper_experiments.py")

    # all
    steps = []
    if args.with_bootstrap:
        steps.append("bootstrap_multiband_archive.py")
    steps.extend(
        [
            "build_pit_archive.py",
            "run_pit_jf_experiments.py",
            "reconcile_returns.py",
            "run_longspan_backtest.py",
            "run_longspan_content_audit.py",
        ]
    )
    for script in steps:
        code = _run(script)
        if code != 0:
            return code
    # LLM consumer is a module invocation (secondary validation)
    code = subprocess.call(
        [sys.executable, "-m", "pdf.sci.llm_consumer.eval"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT), "DB_SPLIT_ENABLED": "1"},
    )
    if code != 0:
        return code
    for script in (
        "generate_core_figures.py",
        "generate_core_manuscript_pdf.py",
        "generate_sci_pdf.py",
    ):
        code = _run(script)
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
