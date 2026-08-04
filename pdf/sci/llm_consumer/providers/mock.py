"""Deterministic mock LLM providers for offline / CI replication.

These are not claims about commercial LLMs. They implement stylized consumers
that either respect compiled world-model fields or ignore them, so the
Compiled vs Raw within-model contrast is testable without API keys.
"""

from __future__ import annotations

import json
from typing import Any

from pdf.sci.llm_consumer.providers.base import ConsumerDecision, validate_action


class MockCompiledAwareProvider:
    """Uses WMI/ACWMI abstention and band tilts when treatment=compiled."""

    name = "mock-compiled-aware"

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        if treatment == "raw":
            mom = float(bundle.get("mom5") or 0.0)
            action = "bullish" if mom > 0 else "bearish" if mom < 0 else "neutral"
            action, conf = validate_action(action, 0.55)
            return ConsumerDecision(
                action=action,
                confidence=conf,
                rationale="raw-momentum",
                raw_text=json.dumps({"action": action, "confidence": conf}),
                model=self.name,
                treatment=treatment,
            )
        wmi = bundle.get("world_model_index") or {}
        should_abs = bool(wmi.get("should_ai_abstain"))
        idx = float(wmi.get("acwmi") or wmi.get("wmi") or 0.0)
        if should_abs or idx < float(bundle.get("abstain_threshold") or 0.25):
            action, conf = validate_action("abstain", 0.9)
            return ConsumerDecision(
                action=action,
                confidence=conf,
                rationale="world-thin-abstain",
                raw_text=json.dumps({"action": action, "confidence": conf}),
                model=self.name,
                treatment=treatment,
            )
        macro = float(bundle.get("macro_tilt") or 0.0)
        alt = float(bundle.get("alt_tilt") or 0.0)
        cascade = float(bundle.get("cascade_p") or 0.0)
        regime = str(bundle.get("detected_regime") or "range")
        if regime == "crisis" and cascade >= 0.6:
            action = "bearish"
        elif macro > 0 and alt > 0:
            action = "bullish"
        elif macro < 0 and alt < 0:
            action = "abstain"
        else:
            mom = float(bundle.get("mom5") or 0.0)
            action = "bullish" if mom > 0 else "bearish" if mom < 0 else "neutral"
        action, conf = validate_action(action, 0.7)
        return ConsumerDecision(
            action=action,
            confidence=conf,
            rationale="compiled-band-content",
            raw_text=json.dumps({"action": action, "confidence": conf}),
            model=self.name,
            treatment=treatment,
        )


class MockMomentumProvider:
    """Ignores compiled fields even when present (compiled≈raw)."""

    name = "mock-momentum"

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        mom = float(bundle.get("mom5") or 0.0)
        action = "bullish" if mom > 0 else "bearish" if mom < 0 else "neutral"
        action, conf = validate_action(action, 0.6)
        return ConsumerDecision(
            action=action,
            confidence=conf,
            rationale=f"momentum-only:{treatment}",
            raw_text=json.dumps({"action": action, "confidence": conf}),
            model=self.name,
            treatment=treatment,
        )


class MockNoisyProvider:
    """Overconfident trader that rarely abstains (ECP stress case)."""

    name = "mock-noisy"

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        mom = float(bundle.get("mom5") or 0.0)
        # Flip sign half-deterministically from asset hash-like field
        flip = 1.0 if int(bundle.get("noise_bit") or 0) % 2 == 0 else -1.0
        signed = mom * flip
        action = "bullish" if signed >= 0 else "bearish"
        if treatment == "compiled":
            wmi = bundle.get("world_model_index") or {}
            if bool(wmi.get("should_ai_abstain")):
                action = "neutral"  # still does not fully abstain — calibration fail
        action, conf = validate_action(action, 0.95)
        return ConsumerDecision(
            action=action,
            confidence=conf,
            rationale="noisy-overconfident",
            raw_text=json.dumps({"action": action, "confidence": conf}),
            model=self.name,
            treatment=treatment,
        )


class PublicLLMCompiledFollower:
    """Stylized public-LLM consumer: follows compiled world guidance when present.

    Named to represent the intended GLM/DeepSeek/GPT usage pattern in offline
    replication (not a claim about any vendor's weights). Prefer live adapters
    in ``openai_compatible`` when API keys exist.
    """

    name = "public-llm-compiled-follower"

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        # Delegate to compiled-aware semantics — public LLMs are instructed to
        # honor should_ai_abstain and band roles in the frozen compiled prompt.
        return MockCompiledAwareProvider().decide(treatment=treatment, prompt=prompt, bundle=bundle)


PROVIDERS = {
    MockCompiledAwareProvider.name: MockCompiledAwareProvider,
    MockMomentumProvider.name: MockMomentumProvider,
    MockNoisyProvider.name: MockNoisyProvider,
    PublicLLMCompiledFollower.name: PublicLLMCompiledFollower,
}


def get_provider(name: str):
    # Live public LLMs: gpt-*, deepseek-*, glm-* when keys are configured
    live_prefixes = ("gpt-", "deepseek", "glm", "openai:", "live:")
    lname = name.lower()
    if lname.startswith(live_prefixes) or lname in {"gpt", "deepseek-chat", "glm-4"}:
        from pdf.sci.llm_consumer.providers.openai_compatible import (
            OpenAICompatibleProvider,
            live_llm_configured,
        )

        if not live_llm_configured():
            # Fall back to stylized public follower so the pipeline still runs
            return PublicLLMCompiledFollower()
        return OpenAICompatibleProvider(name.replace("openai:", "").replace("live:", ""))

    cls = PROVIDERS.get(name)
    if cls is None:
        raise KeyError(f"Unknown mock provider: {name}")
    return cls()
