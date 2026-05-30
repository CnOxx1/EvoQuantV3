from __future__ import annotations

from collections.abc import Iterable, Mapping


KNOWN_HEALTH_STATUSES = (
    "ready",
    "stale",
    "error",
    "empty",
    "missing",
    "unconfigured",
    "disabled",
    "cooldown",
)
KNOWN_QUALITY_FLAGS = (
    "ok",
    "partial",
    "fallback",
    "stale",
)


def normalize_quality_flag(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "unknown"


def resolve_source_health_status(
    *,
    enabled: bool,
    configuration_ready: bool = True,
    last_run_status: str | None = None,
    latest_point_count: int = 0,
    is_stale: bool = False,
) -> str:
    normalized_status = str(last_run_status or "").strip().lower()

    if not enabled:
        return "disabled"
    if not configuration_ready or normalized_status == "unconfigured":
        return "unconfigured"
    if normalized_status == "cooldown":
        return "cooldown"
    if normalized_status == "error":
        return "error"
    if normalized_status == "empty":
        return "empty"
    if is_stale:
        return "stale"
    if int(latest_point_count or 0) > 0:
        return "ready"
    return "missing"


def summarize_health_rows(rows: Iterable[dict]) -> dict[str, int]:
    rows = list(rows)
    summary = {
        f"{status}_source_count": 0
        for status in KNOWN_HEALTH_STATUSES
    }
    for row in rows:
        status = str(row.get("health_status") or "missing").strip().lower()
        key = f"{status}_source_count"
        if key not in summary:
            continue
        summary[key] += 1
    summary["problem_source_count"] = sum(
        1
        for row in rows
        if str(row.get("health_status") or "missing").strip().lower() != "ready"
    )
    return summary


def summarize_quality_flag_counts(
    counts_or_rows: Mapping[str, int] | Iterable[tuple[str, int] | dict],
) -> dict[str, object]:
    counts = {
        flag: 0
        for flag in KNOWN_QUALITY_FLAGS
    }
    unknown_count = 0

    if isinstance(counts_or_rows, Mapping):
        iterator = counts_or_rows.items()
    else:
        iterator = counts_or_rows

    for item in iterator:
        if isinstance(item, Mapping):
            quality_flag = normalize_quality_flag(item.get("quality_flag"))
            count = int(item.get("count") or item.get("point_count") or 1)
        else:
            quality_flag, raw_count = item
            quality_flag = normalize_quality_flag(quality_flag)
            count = int(raw_count or 0)
        if quality_flag in counts:
            counts[quality_flag] += count
        else:
            unknown_count += count

    total_count = sum(counts.values()) + unknown_count
    ok_count = counts["ok"]
    non_ok_count = total_count - ok_count
    return {
        "breakdown": {
            **counts,
            "unknown": unknown_count,
        },
        "total_count": total_count,
        "ok_count": ok_count,
        "partial_count": counts["partial"],
        "fallback_count": counts["fallback"],
        "stale_count": counts["stale"],
        "unknown_count": unknown_count,
        "non_ok_count": non_ok_count,
        "ready_ratio": (ok_count / total_count) if total_count else 0.0,
    }


def is_quality_summary_ai_ready(
    quality_summary: Mapping[str, object] | None,
    *,
    require_ok: bool = True,
    allow_partial: bool = False,
    allow_fallback: bool = False,
    allow_stale: bool = False,
    allow_unknown: bool = False,
) -> bool:
    summary = quality_summary or {}
    ok_count = int(summary.get("ok_count") or 0)
    partial_count = int(summary.get("partial_count") or 0)
    fallback_count = int(summary.get("fallback_count") or 0)
    stale_count = int(summary.get("stale_count") or 0)
    unknown_count = int(summary.get("unknown_count") or 0)

    if require_ok and ok_count <= 0:
        return False
    if not allow_partial and partial_count > 0:
        return False
    if not allow_fallback and fallback_count > 0:
        return False
    if not allow_stale and stale_count > 0:
        return False
    if not allow_unknown and unknown_count > 0:
        return False
    return True
