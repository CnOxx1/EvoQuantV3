"""OpenAI-compatible chat provider for public LLMs (GPT / DeepSeek / GLM, etc.).

Enabled only when an API key is present. Does not change the Compiled vs Raw
estimand: same frozen prompts, temperature 0, JSON action schema.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from pdf.sci.llm_consumer.providers.base import ConsumerDecision, validate_action

_ACTION_RE = re.compile(r"\{[^{}]*\"action\"[^{}]*\}", re.DOTALL)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def live_llm_configured() -> bool:
    return bool(_env("OPENAI_API_KEY") or _env("LLM_API_KEY") or _env("DEEPSEEK_API_KEY") or _env("GLM_API_KEY"))


def _endpoint_and_key(model_hint: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, model_name)."""
    hint = (model_hint or "").lower()
    if "deepseek" in hint or _env("DEEPSEEK_API_KEY"):
        return (
            _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            _env("DEEPSEEK_API_KEY") or _env("LLM_API_KEY") or _env("OPENAI_API_KEY"),
            _env("DEEPSEEK_MODEL", model_hint if "deepseek" in hint else "deepseek-chat"),
        )
    if "glm" in hint or "zhipu" in hint or _env("GLM_API_KEY"):
        return (
            _env("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            _env("GLM_API_KEY") or _env("LLM_API_KEY") or _env("OPENAI_API_KEY"),
            _env("GLM_MODEL", model_hint if model_hint else "glm-4"),
        )
    return (
        _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        _env("OPENAI_API_KEY") or _env("LLM_API_KEY"),
        _env("OPENAI_MODEL", model_hint if model_hint else "gpt-4o-mini"),
    )


class OpenAICompatibleProvider:
    """Thin chat.completions adapter for public LLM vendors."""

    def __init__(self, name: str):
        self.name = name
        self.base_url, self.api_key, self.model = _endpoint_and_key(name)
        if not self.api_key:
            raise RuntimeError(
                f"No API key for live provider {name}; set OPENAI_API_KEY / "
                "DEEPSEEK_API_KEY / GLM_API_KEY / LLM_API_KEY"
            )

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        body = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a market decision agent. Reply with ONLY a JSON object: "
                        '{"action":"bullish|bearish|neutral|abstain","confidence":0-1,'
                        '"rationale":"short"}.'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as e:
            action, conf = validate_action("abstain", 0.0)
            return ConsumerDecision(
                action=action,
                confidence=conf,
                rationale=f"provider-error:{type(e).__name__}",
                raw_text=str(e),
                model=self.name,
                treatment=treatment,
            )
        parsed = _parse_action(text)
        action, conf = validate_action(parsed.get("action", "abstain"), float(parsed.get("confidence") or 0.5))
        return ConsumerDecision(
            action=action,
            confidence=conf,
            rationale=str(parsed.get("rationale") or "live-llm")[:200],
            raw_text=text if isinstance(text, str) else json.dumps(text),
            model=self.name,
            treatment=treatment,
        )


def _parse_action(text: str) -> dict[str, Any]:
    if not text:
        return {"action": "abstain", "confidence": 0.0}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _ACTION_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"action": "abstain", "confidence": 0.0, "rationale": "parse-fail"}
