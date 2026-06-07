from __future__ import annotations

import os
import uuid
import contextvars

_current_traceparent: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_traceparent", default=None
)


def _new_id(length: int) -> str:
    return uuid.uuid4().hex[:length]


class TracePropagator:
    def current_traceparent(self) -> str:
        tp = _current_traceparent.get()
        if tp is None:
            tp = self.create_child_context()
        return tp

    def create_child_context(self, parent_traceparent: str | None = None) -> str:
        if parent_traceparent:
            parts = parent_traceparent.split("-")
            trace_id = parts[1]
        else:
            trace_id = _new_id(32)
        span_id = _new_id(16)
        tp = f"00-{trace_id}-{span_id}-01"
        _current_traceparent.set(tp)
        return tp

    def inject_env(self, env: dict | None = None) -> dict:
        env = env.copy() if env else os.environ.copy()
        env["TRACEPARENT"] = self.current_traceparent()
        return env

    def extract_from_env(self) -> str | None:
        tp = os.environ.get("TRACEPARENT")
        if tp:
            _current_traceparent.set(tp)
        return tp


trace_propagator = TracePropagator()
