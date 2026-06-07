from __future__ import annotations

import contextvars
import json
import os
import sys

from loguru import logger

# Context variable holding per-request correlation ID
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current async/thread context."""
    _correlation_id_var.set(cid)


def get_correlation_id() -> str | None:
    """Retrieve the current correlation ID, or None if unset."""
    return _correlation_id_var.get()


def _patcher(record: dict) -> None:
    """Loguru patcher that injects correlation_id into record['extra']."""
    record["extra"]["correlation_id"] = get_correlation_id()


def _json_formatter(record: dict) -> str:
    """Serialize a log record as a single-line JSON string."""
    payload = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "correlation_id": record["extra"].get("correlation_id"),
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
    }
    return json.dumps(payload, default=str) + "\n"


def configure_structured_logging() -> None:
    """Configure loguru with correlation ID patching and optional JSON output."""
    logger.configure(patcher=_patcher)

    if os.environ.get("STRUCTURED_LOGS", "").lower() == "true":
        logger.remove()
        logger.add(sys.stdout, format=_json_formatter, level="DEBUG")
