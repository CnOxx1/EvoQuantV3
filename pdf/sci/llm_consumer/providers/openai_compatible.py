"""OpenAI-compatible chat provider for public LLMs via TeamoRouter / vendor gateways.

Prefer a single gateway:
  OPENAI_BASE_URL=https://api.teamorouter.com/v1
  OPENAI_API_KEY=sk-teamo-...

Model IDs are passed through (gpt-5.4-mini, deepseek-v4-flash, glm-5.2, ...).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

from pdf.sci.llm_consumer.providers.base import ConsumerDecision, validate_action

_ACTION_RE = re.compile(r"\{[^{}]*\"action\"[^{}]*\}", re.DOTALL)


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def live_llm_configured() -> bool:
    return bool(
        _env("OPENAI_API_KEY")
        or _env("LLM_API_KEY")
        or _env("TEAMOROUTER_API_KEY")
        or _env("DEEPSEEK_API_KEY")
        or _env("GLM_API_KEY")
    )


def _endpoint_and_key(model_hint: str) -> tuple[str, str, str]:
    """Return (base_url, api_key, model_name).

    If a gateway base URL is set (TeamoRouter / OpenAI-compatible proxy), use it
    for *all* model IDs so GPT/DeepSeek/GLM share one key.
    """
    model = (model_hint or "").strip()
    # Strip optional prefixes used in config
    for prefix in ("live:", "openai:", "teamo:"):
        if model.lower().startswith(prefix):
            model = model[len(prefix) :]

    gateway = (
        _env("OPENAI_BASE_URL")
        or _env("TEAMOROUTER_BASE_URL")
        or _env("LLM_BASE_URL")
    )
    gateway_key = (
        _env("OPENAI_API_KEY")
        or _env("TEAMOROUTER_API_KEY")
        or _env("LLM_API_KEY")
    )

    if gateway and gateway_key:
        # TeamoRouter docs use .../v1 ; accept with or without trailing /v1
        base = gateway.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        return base, gateway_key, model or _env("OPENAI_MODEL", "gpt-5.4-mini")

    # Per-vendor fallbacks (direct APIs)
    hint = model.lower()
    if "deepseek" in hint:
        return (
            _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            _env("DEEPSEEK_API_KEY") or gateway_key,
            model or "deepseek-chat",
        )
    if "glm" in hint or "zhipu" in hint:
        return (
            _env("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            _env("GLM_API_KEY") or gateway_key,
            model or "glm-4",
        )
    return (
        _env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        gateway_key,
        model or _env("OPENAI_MODEL", "gpt-4o-mini"),
    )


def chat_text(
    model_name: str,
    *,
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout: int = 120,
) -> str:
    """Generic OpenAI-compatible chat call returning raw text ('' on error).

    Reused by non-trading consumer tasks (e.g. grounding eval) so all live
    experiments share one endpoint/key resolution path.
    """
    base_url, api_key, model = _endpoint_and_key(model_name)
    if not api_key:
        raise RuntimeError(f"No API key for live provider {model_name}")
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload["choices"][0]["message"].get("content") or ""
        if isinstance(text, list):
            text = "".join(
                (p.get("text") if isinstance(p, dict) else str(p)) for p in text
            )
        return text if isinstance(text, str) else json.dumps(text)
    except Exception as e:  # noqa: BLE001 — caller scores empty as failure
        return f'{{"error":"{type(e).__name__}"}}'


class OpenAICompatibleProvider:
    """Thin chat.completions adapter for public LLM vendors / gateways."""

    def __init__(self, name: str):
        self.name = name
        self.base_url, self.api_key, self.model = _endpoint_and_key(name)
        if not self.api_key:
            raise RuntimeError(
                f"No API key for live provider {name}; set OPENAI_API_KEY / "
                "TEAMOROUTER_API_KEY / LLM_API_KEY"
            )

    def decide(self, *, treatment: str, prompt: str, bundle: dict[str, Any]) -> ConsumerDecision:
        body = {
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": 1024,
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
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        text = ""
        last_err: Exception | None = None
        # Retry transient gateway failures so provider errors are not silently
        # scored as abstentions in large sweeps.
        for attempt, timeout_s in enumerate((60, 60, 90, 120)):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                msg = payload["choices"][0]["message"]
                text = msg.get("content") or ""
                if isinstance(text, list):  # some gateways return content parts
                    text = "".join(
                        (p.get("text") if isinstance(p, dict) else str(p)) for p in text
                    )
                last_err = None
                break
            except Exception as e:  # noqa: BLE001 — retried; recorded on final failure
                last_err = e
                if attempt < 3:
                    # Rate-limit friendly backoff (429s dominate under load).
                    time.sleep(5.0 * (attempt + 1))
        if last_err is not None:
            action, conf = validate_action("abstain", 0.0)
            return ConsumerDecision(
                action=action,
                confidence=conf,
                rationale=f"provider-error:{type(last_err).__name__}",
                raw_text=str(last_err)[:500],
                model=self.name,
                treatment=treatment,
            )
        parsed = _parse_action(text if isinstance(text, str) else json.dumps(text))
        action, conf = validate_action(
            parsed.get("action", "abstain"), float(parsed.get("confidence") or 0.5)
        )
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
    text = text.strip()
    # strip markdown fences (complete or truncated)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _ACTION_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        # Truncated / partial JSON: recover action + optional confidence
        am = re.search(
            r'"action"\s*:\s*"(bullish|bearish|neutral|abstain)"',
            text,
            flags=re.I,
        )
        if am:
            out: dict[str, Any] = {"action": am.group(1).lower(), "rationale": "partial-json"}
            cm = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
            if cm:
                out["confidence"] = float(cm.group(1))
            return out
    return {"action": "abstain", "confidence": 0.0, "rationale": "parse-fail"}
