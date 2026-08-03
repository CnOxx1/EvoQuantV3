"""Availability-shock helpers for paper identification (O_t).

Treats collection_runs failures/gaps as queryable availability shocks without
requiring a new table. Optional metadata_json fields:
  event_kind, band, outage_flag, planted
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def _parse_metadata(raw: Any) -> dict:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _rows_to_dicts(cursor) -> list[dict]:
    if not cursor.description:
        return []
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def load_availability_shocks(
    *,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    modules: list[str] | None = None,
    statuses: tuple[str, ...] = ("error", "empty"),
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Load availability shocks from collection_runs across split DBs.

    A shock is a collection_run with status in ``statuses`` (default error/empty),
    optionally tagged via metadata_json.event_kind == "availability_shock".
    """
    from database.router import DatabaseRouter, Domain

    if isinstance(start, datetime):
        start = start.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%dT%H:%M:%S")

    router = DatabaseRouter()
    dbs = [
        router.get_manager(Domain.EXCHANGE_DATA),
        router.get_manager(Domain.MARKET_DATA),
        router.get_analytics_db(),
    ]
    shocks: list[dict[str, Any]] = []
    for db in dbs:
        try:
            exists = db.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collection_runs'"
            ).fetchone()
            if not exists:
                continue
        except Exception:
            continue

        clauses = ["status IN ({})".format(",".join("?" * len(statuses)))]
        params: list[Any] = list(statuses)
        if start:
            clauses.append("COALESCE(finished_at, started_at, created_at) >= ?")
            params.append(start)
        if end:
            clauses.append("COALESCE(finished_at, started_at, created_at) <= ?")
            params.append(end)
        if modules:
            clauses.append("module_name IN ({})".format(",".join("?" * len(modules))))
            params.extend(modules)
        params.append(int(limit))
        sql = f"""
            SELECT id, module_name, source_name, job_name, status,
                   item_count, started_at, finished_at, duration_seconds,
                   message, metadata_json, created_at
            FROM collection_runs
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(finished_at, started_at, created_at) DESC
            LIMIT ?
        """
        try:
            rows = _rows_to_dicts(db.conn.execute(sql, params))
        except Exception:
            continue
        for row in rows:
            meta = _parse_metadata(row.get("metadata_json"))
            shocks.append(
                {
                    "id": row.get("id"),
                    "module_name": row.get("module_name"),
                    "source_name": row.get("source_name"),
                    "job_name": row.get("job_name"),
                    "status": row.get("status"),
                    "item_count": row.get("item_count"),
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                    "created_at": row.get("created_at"),
                    "message": row.get("message"),
                    "event_kind": meta.get("event_kind") or "collection_failure",
                    "band": meta.get("band") or meta.get("band_name") or row.get("module_name"),
                    "outage_flag": bool(meta.get("outage_flag", True)),
                    "planted": bool(meta.get("planted", False)),
                    "metadata": meta,
                    "event_time": row.get("finished_at") or row.get("started_at") or row.get("created_at"),
                }
            )

    shocks.sort(key=lambda x: str(x.get("event_time") or ""), reverse=True)
    return shocks[:limit]


def tag_availability_shock_metadata(
    *,
    band: str,
    planted: bool = False,
    extra: dict | None = None,
) -> str:
    """Serialize metadata_json for collectors/audit when recording a shock."""
    payload = {
        "event_kind": "availability_shock",
        "band": band,
        "outage_flag": True,
        "planted": planted,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)
