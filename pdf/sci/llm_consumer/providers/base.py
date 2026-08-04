"""Provider interface for LLM consumer validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


ACTIONS = ("bullish", "bearish", "neutral", "abstain")


@dataclass
class ConsumerDecision:
    action: str
    confidence: float
    rationale: str = ""
    raw_text: str = ""
    model: str = ""
    treatment: str = ""

    def position(self) -> float:
        if self.action == "bullish":
            return 1.0
        if self.action == "bearish":
            return -1.0
        return 0.0

    def is_abstain(self) -> bool:
        return self.action == "abstain"


class LLMProvider(Protocol):
    name: str

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        ...


def validate_action(action: str, confidence: float) -> tuple[str, float]:
    a = str(action).strip().lower()
    if a not in ACTIONS:
        a = "neutral"
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        c = 0.0
    c = max(0.0, min(1.0, c))
    return a, c
