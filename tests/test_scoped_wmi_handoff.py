"""Scoped WMI opens the production valve on 3/3 archive-ready days."""

from __future__ import annotations

from logic_layer.decision_handoff.service import DecisionHandoffService
from logic_layer.time_slice.world_quality import scoped_wmi_from_statuses


def test_scoped_wmi_opens_when_eval_archive_ready():
    statuses = {
        "exchange": "ready",
        "macro": "ready",
        "alternative": "ready",
        "news": "missing",
        "onchain": "missing",
        "options": "missing",
        "tokenomics": "missing",
        "event_calendar": "missing",
    }
    q = scoped_wmi_from_statuses(statuses, scope="eval_archive")
    assert q["wmi"] >= 0.2
    assert q["should_ai_abstain"] is False
    assert q["n_ready"] == 3


def test_full_schema_wmi_stays_below_gate_with_empty_extra_bands():
    statuses = {
        "exchange": "ready",
        "macro": "ready",
        "alternative": "ready",
        "news": "missing",
        "onchain": "missing",
        "options": "missing",
        "tokenomics": "missing",
        "event_calendar": "missing",
    }
    q = scoped_wmi_from_statuses(statuses, scope="full")
    assert q["wmi"] < 0.2
    assert q["should_ai_abstain"] is True


def test_scoped_wmi_abstains_when_exchange_missing():
    statuses = {
        "exchange": "missing",
        "macro": "ready",
        "alternative": "ready",
        "news": "missing",
        "onchain": "missing",
        "options": "missing",
        "tokenomics": "missing",
        "event_calendar": "missing",
    }
    q = scoped_wmi_from_statuses(statuses, scope="eval_archive")
    assert q["archive_complete"] is False
    assert q["should_ai_abstain"] is True
    assert q["wmi"] < 0.2 or q["n_ready"] < 3


def test_decision_handoff_acts_only_when_valve_open():
    svc = DecisionHandoffService(require_open_valve=True)
    closed = {
        "macro_tilt": 1.0,
        "alt_tilt": 1.0,
        "world_model_index": {"wmi": 0.09, "should_ai_abstain": True},
        "audit": {"evidence_ids": ["band:macro:ready"]},
    }
    opened = {
        "macro_tilt": 1.0,
        "alt_tilt": -1.0,
        "world_model_index": {"wmi": 0.26, "should_ai_abstain": False},
        "audit": {"evidence_ids": ["band:macro:ready"]},
    }
    assert svc.act(closed)["action"] == "abstain"
    assert svc.act(closed)["handoff"] == "blocked"
    out = svc.act(opened)
    assert out["handoff"] == "acted"
    assert out["action"] == "neutral"  # +1 + -1
