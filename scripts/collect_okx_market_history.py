"""Backfill free, paginated OKX spot and perpetual OHLCV history into a raw table."""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
BASE = "https://www.okx.com/api/v5/market/history-candles"
INSTRUMENTS = ("BTC-USDT", "ETH-USDT", "BTC-USDT-SWAP", "ETH-USDT-SWAP")

def request_rows(params: dict[str, object]) -> tuple[list[list[str]], str]:
    url = BASE + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0": raise RuntimeError(payload)
    return payload.get("data") or [], url

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--bar", default="1H")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages-per-instrument", type=int, default=30)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    boundary_ms = int((now - timedelta(days=args.days)).timestamp() * 1000)
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS okx_market_candle_history_raw (
        instrument TEXT NOT NULL, market_type TEXT NOT NULL, bar TEXT NOT NULL, open_time_ms INTEGER NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL, volume_ccy REAL, payload_json TEXT NOT NULL,
        source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
        PRIMARY KEY(instrument, bar, open_time_ms))""")
    total = 0; summary = []
    for instrument in INSTRUMENTS:
        after = None; rows_written = pages = 0; reached_boundary = False
        while pages < args.max_pages_per_instrument:
            params: dict[str, object] = {"instId": instrument, "bar": args.bar, "limit": args.page_size}
            if after is not None: params["after"] = after
            rows, source_url = request_rows(params)
            pages += 1
            if not rows: break
            oldest_ms = min(int(row[0]) for row in rows)
            collected_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            payload_rows = []
            for row in rows:
                ts = int(row[0])
                if ts < boundary_ms: continue
                payload_rows.append((instrument, "swap" if instrument.endswith("-SWAP") else "spot", args.bar, ts,
                    float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]),
                    float(row[6]) if len(row) > 6 and row[6] else None, json.dumps(row, ensure_ascii=False), source_url, collected_at))
            conn.executemany("INSERT OR IGNORE INTO okx_market_candle_history_raw VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", payload_rows)
            conn.commit(); rows_written += len(payload_rows); total += len(payload_rows)
            print(json.dumps({"instrument": instrument, "page": pages, "page_rows": len(rows), "written": len(payload_rows), "oldest_open_time_ms": oldest_ms}, ensure_ascii=False))
            if oldest_ms <= boundary_ms or len(rows) < args.page_size:
                reached_boundary = oldest_ms <= boundary_ms; break
            after = oldest_ms
            time.sleep(args.pause_seconds)
        summary.append({"instrument": instrument, "pages": pages, "rows_written": rows_written, "reached_boundary": reached_boundary})
    conn.close()
    print(json.dumps({"days": args.days, "bar": args.bar, "rows_written": total, "summary": summary, "collected_at": now.isoformat()}, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
