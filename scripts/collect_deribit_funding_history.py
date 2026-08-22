"""Backfill free Deribit hourly funding history in bounded time chunks."""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
BASE = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
INSTRUMENTS = ("BTC-PERPETUAL", "ETH-PERPETUAL")

def fetch(instrument: str, start: datetime, end: datetime) -> tuple[list[dict], str]:
    url = BASE + "?" + urlencode({"instrument_name": instrument, "start_timestamp": int(start.timestamp() * 1000), "end_timestamp": int(end.timestamp() * 1000)})
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response: payload = json.load(response)
    if payload.get("error"): raise RuntimeError(payload["error"])
    return payload.get("result") or [], url

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--chunk-hours", type=int, default=168)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    args = parser.parse_args()
    end = datetime.now(timezone.utc); start = end - timedelta(days=args.days)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS deribit_funding_history_raw (
        instrument TEXT NOT NULL, funding_time_ms INTEGER NOT NULL, index_price REAL,
        interest_1h REAL, interest_8h REAL, prev_index_price REAL, payload_json TEXT NOT NULL,
        source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
        PRIMARY KEY(instrument, funding_time_ms))""")
    total = 0; summary = []
    for instrument in INSTRUMENTS:
        cursor = start; rows_written = chunks = 0
        while cursor < end:
            chunk_end = min(cursor + timedelta(hours=args.chunk_hours), end)
            rows, source_url = fetch(instrument, cursor, chunk_end)
            collected_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            values = [(instrument, int(row["timestamp"]), row.get("index_price"), row.get("interest_1h"), row.get("interest_8h"),
                row.get("prev_index_price"), json.dumps(row, ensure_ascii=False, sort_keys=True), source_url, collected_at) for row in rows]
            conn.executemany("INSERT OR IGNORE INTO deribit_funding_history_raw VALUES (?,?,?,?,?,?,?,?,?)", values)
            conn.commit(); rows_written += len(values); total += len(values); chunks += 1
            print(json.dumps({"instrument": instrument, "chunk": chunks, "start": cursor.isoformat(), "end": chunk_end.isoformat(), "rows": len(values)}, ensure_ascii=False))
            cursor = chunk_end
            if cursor < end: time.sleep(args.pause_seconds)
        summary.append({"instrument": instrument, "chunks": chunks, "rows_written": rows_written})
    conn.close()
    print(json.dumps({"days": args.days, "rows_written": total, "summary": summary, "collected_at": end.isoformat()}, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
