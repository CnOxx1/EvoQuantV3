"""Record the verified outcome of a queued data backfill attempt."""
from __future__ import annotations
import argparse, sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "market_data.db"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--status", choices=("resolved", "source_omission", "failed"), required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    conn = sqlite3.connect(DB)
    cursor = conn.execute("""UPDATE data_backfill_tasks SET status=?, last_error=?, detected_at=?
        WHERE dataset=? AND status='pending'""", (args.status, args.message, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), args.dataset))
    conn.commit(); conn.close(); print({"dataset": args.dataset, "status": args.status, "tasks_updated": cursor.rowcount}); return 0
if __name__ == "__main__": raise SystemExit(main())
