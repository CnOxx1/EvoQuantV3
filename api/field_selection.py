from __future__ import annotations

from fastapi import Query

IDENTITY_KEYS = {"symbol", "timestamp"}


def parse_fields(fields: str | None = Query(None)) -> set[str] | None:
    """Parse comma-separated field names from query param."""
    if fields is None:
        return None
    return {f.strip() for f in fields.split(",") if f.strip()}


def filter_response(
    data: dict | list[dict], fields: set[str] | None
) -> dict | list[dict]:
    """Filter response data to only include requested fields."""
    if fields is None:
        return data
    allowed = fields | IDENTITY_KEYS
    if isinstance(data, list):
        return [{k: v for k, v in item.items() if k in allowed} for item in data]
    return {k: v for k, v in data.items() if k in allowed}
