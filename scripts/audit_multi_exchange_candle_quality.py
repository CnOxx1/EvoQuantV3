"""Report source coverage and quality-gated composite candle outcomes."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
REPORT = ROOT / "reports" / "multi_exchange_candle_quality_report.json"

def rows_to_dict(rows): return [dict(row) for row in rows]

def main() -> int:
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    raw = rows_to_dict(conn.execute("""SELECT exchange,pair,COUNT(*) AS rows,MIN(open_time_ms) AS first_open_time_ms,
        MAX(open_time_ms) AS last_open_time_ms FROM public_exchange_candle_history_raw GROUP BY exchange,pair ORDER BY pair,exchange"""))
    composites = rows_to_dict(conn.execute("""SELECT pair,COUNT(*) AS rows,MIN(open_time_ms) AS first_open_time_ms,
        MAX(open_time_ms) AS last_open_time_ms,MIN(source_count) AS min_source_count,MAX(source_count) AS max_source_count,
        MAX(max_deviation_bps) AS max_observed_deviation_bps FROM multi_exchange_composite_candles GROUP BY pair ORDER BY pair"""))
    events = rows_to_dict(conn.execute("""SELECT status,COALESCE(reason,'accepted') AS reason,COUNT(*) AS rows
        FROM multi_exchange_candle_quality_events GROUP BY status,COALESCE(reason,'accepted') ORDER BY status,reason"""))
    no_single_source = conn.execute("SELECT COUNT(*) FROM multi_exchange_composite_candles WHERE source_count < 2").fetchone()[0]
    conn.close()
    report = {"audited_at": datetime.now(timezone.utc).isoformat(), "raw_coverage": raw, "composite_coverage": composites,
              "quality_event_summary": events, "single_source_composite_rows": no_single_source,
              "quality_gate": {"minimum_sources": 2, "maximum_close_deviation_bps": 100.0},
              "status": "passed" if no_single_source == 0 and composites else "failed"}
    REPORT.parent.mkdir(exist_ok=True); REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)); return 0 if report["status"] == "passed" else 1
if __name__ == "__main__": raise SystemExit(main())
