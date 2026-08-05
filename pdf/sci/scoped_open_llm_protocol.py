#!/usr/bin/env python3
"""Frozen protocol stub: scoped-open LLM arms (not run in Paper B main results).

Paper B's live LLM arms freeze full-schema stress bundles (RQ1--RQ2).
This module documents the orthogonal protocol for a future / optional
Compiled-scoped arm on archive-complete days only. It does not claim
results and does not require API keys unless executed explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass


CUT = "2026-01-16"
PRODUCTION_GATE = 0.2
BAND_SCOPE = "eval_archive"


@dataclass(frozen=True)
class ScopedOpenArm:
    name: str
    bundle_kind: str
    hard_valve: bool
    band_scope: str


ARMS = (
    ScopedOpenArm("blind", "none", False, "n/a"),
    ScopedOpenArm("raw", "mom5", False, "n/a"),
    ScopedOpenArm("ungated", "world_bundle", False, BAND_SCOPE),
    ScopedOpenArm("compiled_scoped", "world_bundle", True, BAND_SCOPE),
)


PRIMARY_METRICS = (
    "open_day_abstain_rate",  # Compiled should act only when valve open
    "valve_obedience",  # fraction of closed days with action=abstain
    "act_conditional_CE_vs_raw",  # usability / avoided loss, not alpha
)

SECONDARY_METRICS = (
    "sharpe",
    "CE",
)


def protocol_card() -> dict:
    return {
        "purpose": "Optional scoped-open LLM usability arm (downstream of Paper B)",
        "panel_cut": CUT,
        "eligible_days": "valve_open_scoped == True (archive-complete AND WMI_scoped>=0.2)",
        "arms": [a.__dict__ for a in ARMS],
        "primary_metrics": list(PRIMARY_METRICS),
        "secondary_metrics": list(SECONDARY_METRICS),
        "claim_boundary": (
            "Measures whether a public LLM can consume an open production "
            "valve; not a trading-alpha or generative world-model claim."
        ),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(protocol_card(), indent=2))
