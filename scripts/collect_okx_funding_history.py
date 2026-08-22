"""Backfill free, paginated OKX perpetual funding-rate history into a dedicated raw table."""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
BASE = "https://www.okx.com/api/v5/public/funding-rate-history"
INSTRUMENTS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")

def request_rows(params: dict[str, object]) -> tuple[list[dict], str]:
    url = BASE + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0": raise RuntimeError(payload)
    return payload.get("data") or [], url

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages-per-instrument", type=int, default=10)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    boundary_ms = int((now - timedelta(days=args.days)).timestamp() * 1000)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS okx_funding_history_raw (
        instrument TEXT NOT NULL, funding_time_ms INTEGER NOT NULL, funding_rate REAL,
        realized_rate REAL, formula_type TEXT, method TEXT, payload_json TEXT NOT NULL,
        source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
        PRIMARY KEY(instrument, funding_time_ms))""")
    total = 0; summary = []
    for instrument in INSTRUMENTS:
        after = None; pages = rows_written = 0; reached_boundary = False
        while pages < args.max_pages_per_instrument:
            params: dict[str, object] = {"instId": instrument, "limit": args.page_size}
            if after is not None: params["after"] = after
            rows, source_url = request_rows(params)
            pages += 1
            if not rows: break
            oldest_ms = min(int(row["fundingTime"]) for row in rows)
            collected_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            payload_rows = [(instrument, int(row["fundingTime"]), float(row["fundingRate"]),
                float(row["realizedRate"]) if row.get("realizedRate") else None, row.get("formulaType"), row.get("method"),
                json.dumps(row, ensure_ascii=False, sort_keys=True), source_url, collected_at)
                for row in rows if int(row["fundingTime"]) >= boundary_ms]
            conn.executemany("INSERT OR IGNORE INTO okx_funding_history_raw VALUES (?,?,?,?,?,?,?,?,?)", payload_rows)
            conn.commit(); rows_written += len(payload_rows); total += len(payload_rows)
            print(json.dumps({"instrument": instrument, "page": pages, "page_rows": len(rows), "written": len(payload_rows), "oldest_funding_time_ms": oldest_ms}, ensure_ascii=False))
            if oldest_ms <= boundary_ms or len(rows) < args.page_size:
                reached_boundary = oldest_ms <= boundary_ms; break
            after = oldest_ms
            time.sleep(args.pause_seconds)
        summary.append({"instrument": instrument, "pages": pages, "rows_written": rows_written, "reached_boundary": reached_boundary})
    conn.close()
    print(json.dumps({"days": args.days, "rows_written": total, "summary": summary, "collected_at": now.isoformat()}, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
