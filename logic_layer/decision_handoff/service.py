"""Decision-layer handoff proxy over a data-end world bundle.

The data end proves it can be handed to decision by exposing a callable
contract: abstain when the valve is closed; otherwise act on disclosed
PIT-safe content fields (no LLM required).
"""

from __future__ import annotations

from typing import Any, Mapping


class DecisionHandoffService:
    """Minimal downstream consumer of the observation-layer bundle."""

    ACTIONS = ("bullish", "bearish", "neutral", "abstain")

    def __init__(self, *, require_open_valve: bool = True):
        self.require_open_valve = bool(require_open_valve)

    @staticmethod
    def _tilt_sign(value: Any) -> int:
        try:
            v = float(value)
        except (TypeError, ValueError):
            return 0
        if v > 0:
            return 1
        if v < 0:
            return -1
        return 0

    def is_valve_open(self, bundle: Mapping[str, Any]) -> bool:
        wmi = bundle.get("world_model_index") or {}
        if "should_ai_abstain" in wmi:
            return not bool(wmi.get("should_ai_abstain"))
        if "should_ai_abstain" in bundle:
            return not bool(bundle.get("should_ai_abstain"))
        return False

    def act(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        """Return a decision action bound to disclosed bundle fields."""
        open_valve = self.is_valve_open(bundle)
        evidence = list((bundle.get("audit") or {}).get("evidence_ids") or [])
        if self.require_open_valve and not open_valve:
            return {
                "action": "abstain",
                "reason": "data_end_valve_closed",
                "valve_open": False,
                "evidence_ids": evidence,
                "handoff": "blocked",
            }

        macro = self._tilt_sign(bundle.get("macro_tilt"))
        alt = self._tilt_sign(bundle.get("alt_tilt"))
        score = macro + alt
        if score > 0:
            action = "bullish"
        elif score < 0:
            action = "bearish"
        else:
            action = "neutral"
        return {
            "action": action,
            "reason": "content_tilts",
            "valve_open": open_valve,
            "macro_tilt_sign": macro,
            "alt_tilt_sign": alt,
            "evidence_ids": evidence
            or [
                f"tilt:macro:{bundle.get('macro_tilt')}",
                f"tilt:alt:{bundle.get('alt_tilt')}",
            ],
            "handoff": "acted",
        }
