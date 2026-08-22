"""Audit continuous raw-data coverage and queue idempotent manual backfill tasks."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCHANGE_DB = ROOT / "database" / "exchange_data.db"
MARKET_DB = ROOT / "database" / "market_data.db"
REPORT = ROOT / "reports" / "data_coverage_gaps.json"

SPECS = (
    {"dataset": "okx_market_candle_history", "db": EXCHANGE_DB, "table": "okx_market_candle_history_raw", "partition": "instrument", "time": "open_time_ms", "interval_ms": 3_600_000, "command": "python scripts/collect_okx_market_history.py --days 90 --bar 1H"},
    {"dataset": "okx_funding_history", "db": EXCHANGE_DB, "table": "okx_funding_history_raw", "partition": "instrument", "time": "funding_time_ms", "interval_ms": 28_800_000, "command": "python scripts/collect_okx_funding_history.py --days 90"},
    {"dataset": "deribit_funding_history", "db": EXCHANGE_DB, "table": "deribit_funding_history_raw", "partition": "instrument", "time": "funding_time_ms", "interval_ms": 3_600_000, "command": "python scripts/collect_deribit_funding_history.py --days 90 --chunk-hours 168"},
    {"dataset": "bitcoin_onchain_history", "db": MARKET_DB, "table": "bitcoin_onchain_history", "partition": "metric", "time": "observed_at", "interval_ms": 86_400_000, "command": "python scripts/collect_bitcoin_onchain_history.py"},
)

def parse_time(value) -> int:
    if isinstance(value, int): return value
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() * 1000)

def audit_spec(spec: dict) -> dict:
    conn = sqlite3.connect(spec["db"])
    rows = conn.execute(f'SELECT "{spec["partition"]}", "{spec["time"]}" FROM "{spec["table"]}" ORDER BY 1, 2').fetchall()
    conn.close()
    groups: dict[str, list[int]] = {}
    for partition, timestamp in rows: groups.setdefault(str(partition), []).append(parse_time(timestamp))
    partitions = []; gap_tasks = []
    for partition, values in groups.items():
        gaps = [{"after": values[i - 1], "before": values[i], "gap_ms": values[i] - values[i - 1]} for i in range(1, len(values)) if values[i] - values[i - 1] > spec["interval_ms"] * 1.5]
        partitions.append({"partition": partition, "rows": len(values), "first_time_ms": values[0], "last_time_ms": values[-1], "gap_count": len(gaps), "max_gap_ms": max((item["gap_ms"] for item in gaps), default=0)})
        for gap in gaps:
            gap_tasks.append({"partition": partition, **gap})
    return {"dataset": spec["dataset"], "table": spec["table"], "interval_ms": spec["interval_ms"], "partitions": partitions, "gaps": gap_tasks, "recommended_command": spec["command"]}

def queue_tasks(results: list[dict]) -> int:
    conn = sqlite3.connect(MARKET_DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS data_backfill_tasks (
        task_key TEXT PRIMARY KEY, dataset TEXT NOT NULL, partition_key TEXT NOT NULL,
        gap_after_ms INTEGER NOT NULL, gap_before_ms INTEGER NOT NULL, status TEXT NOT NULL,
        recommended_command TEXT NOT NULL, detected_at TEXT NOT NULL, last_error TEXT)""")
    detected_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(); queued = 0
    for result in results:
        for gap in result["gaps"]:
            key = f'{result["dataset"]}:{gap["partition"]}:{gap["after"]}:{gap["before"]}'
            conn.execute("""INSERT INTO data_backfill_tasks VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_key) DO UPDATE SET detected_at=excluded.detected_at,
                recommended_command=excluded.recommended_command""", (key, result["dataset"], gap["partition"], gap["after"], gap["before"], "pending", result["recommended_command"], detected_at, None))
            queued += 1
    conn.commit(); conn.close(); return queued

def task_status_counts() -> dict[str, int]:
    conn = sqlite3.connect(MARKET_DB)
    try:
        present = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='data_backfill_tasks'").fetchone()
        if not present: return {}
        return {str(status): int(count) for status, count in conn.execute("SELECT status, COUNT(*) FROM data_backfill_tasks GROUP BY status")}
    finally:
        conn.close()

def main() -> int:
    results = [audit_spec(spec) for spec in SPECS]
    queued = queue_tasks(results)
    report = {"audited_at": datetime.now(timezone.utc).isoformat(), "datasets": results, "queued_backfill_tasks": queued, "backfill_task_status": task_status_counts(),
              "status": "attention" if queued else "healthy"}
    REPORT.parent.mkdir(exist_ok=True); REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
