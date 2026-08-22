"""Summarize real records and research artifacts created by a closure run."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def table_preview(database: Path, table: str, order_by: str, limit: int = 5) -> list[dict]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            f'SELECT * FROM "{table}" ORDER BY "{order_by}" DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, default=ROOT / "reports" / "production_run_before.json")
    parser.add_argument("--after", type=Path, default=ROOT / "reports" / "production_run_after.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "production_run_summary.json")
    args = parser.parse_args()

    before = load_json(args.before)
    after = load_json(args.after)
    deltas = []
    for domain, after_data in after["domains"].items():
        before_count = before["domains"].get(domain, {}).get("row_count")
        after_count = after_data.get("row_count")
        if isinstance(before_count, int) and isinstance(after_count, int):
            delta = after_count - before_count
            if delta:
                deltas.append(
                    {
                        "domain": domain,
                        "table": after_data["table"],
                        "before": before_count,
                        "after": after_count,
                        "added": delta,
                    }
                )

    analytics = ROOT / "database" / "analytics.db"
    result = {
        "status": "passed" if after["status"] == "passed" else "failed",
        "status_before": before["api_summary"],
        "status_after": after["api_summary"],
        "record_deltas": sorted(deltas, key=lambda item: item["added"], reverse=True),
        "total_new_primary_records": sum(item["added"] for item in deltas),
        "research_outputs": {
            "latest_regimes": table_preview(analytics, "regime_states", "as_of"),
            "latest_portfolio_risk": table_preview(analytics, "portfolio_risk_snapshots", "created_at"),
            "latest_cross_asset": table_preview(analytics, "cross_asset_correlation_snapshots", "created_at"),
        },
        "anomaly_scan": {
            "table": "anomaly_events",
            "event_count": after["domains"]["anomaly_detection"]["row_count"],
            "interpretation": "0 表示本次真实扫描未触发阈值，并非缺少扫描。",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(f"\n已写入本次闭环运行汇总: {args.output}")
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
