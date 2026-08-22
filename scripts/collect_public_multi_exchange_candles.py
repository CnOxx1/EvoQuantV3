"""Collect normalized public spot OHLCV from Coinbase, Kraken and Bitstamp."""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
BAR = "1H"; GRANULARITY_SECONDS = 3_600
PAIRS = ("BTC-USD", "ETH-USD")

def get_json(url: str):
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response: return json.load(response)

def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS public_exchange_candle_history_raw (
        exchange TEXT NOT NULL, pair TEXT NOT NULL, bar TEXT NOT NULL, open_time_ms INTEGER NOT NULL,
        open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL,
        payload_json TEXT NOT NULL, source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
        PRIMARY KEY(exchange, pair, bar, open_time_ms))""")

def store(conn: sqlite3.Connection, exchange: str, pair: str, rows: list[tuple], source_url: str) -> int:
    collected_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    values = [(exchange, pair, BAR, timestamp * 1000, op, high, low, close, volume, json.dumps(raw, ensure_ascii=False), source_url, collected_at)
              for timestamp, op, high, low, close, volume, raw in rows]
    conn.executemany("INSERT OR IGNORE INTO public_exchange_candle_history_raw VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
    conn.commit(); return len(values)

def collect_coinbase(conn: sqlite3.Connection, pair: str, start: datetime, end: datetime, pause: float) -> int:
    cursor = start; written = 0; pages = 0
    while cursor < end:
        chunk_end = min(cursor + timedelta(seconds=GRANULARITY_SECONDS * 300), end)
        url = "https://api.exchange.coinbase.com/products/" + pair + "/candles?" + urlencode({"granularity": GRANULARITY_SECONDS, "start": cursor.isoformat(), "end": chunk_end.isoformat()})
        payload = get_json(url)
        rows = [(int(row[0]), float(row[3]), float(row[2]), float(row[1]), float(row[4]), float(row[5]), row) for row in payload]
        written += store(conn, "coinbase", pair, rows, url); pages += 1
        print(json.dumps({"exchange": "coinbase", "pair": pair, "page": pages, "rows": len(rows)}, ensure_ascii=False))
        cursor = chunk_end
        if cursor < end: time.sleep(pause)
    return written

def collect_kraken(conn: sqlite3.Connection, pair: str) -> int:
    source_pair = "XBTUSD" if pair == "BTC-USD" else "ETHUSD"
    url = "https://api.kraken.com/0/public/OHLC?" + urlencode({"pair": source_pair, "interval": 60, "assetVersion": 1})
    payload = get_json(url)
    if payload.get("error"): raise RuntimeError(payload["error"])
    result = payload["result"]; raw_rows = next(value for key, value in result.items() if key != "last")
    committed = raw_rows[:-1]  # Kraken documents the final row as the currently forming, uncommitted hour.
    rows = [(int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[6]), row) for row in committed]
    print(json.dumps({"exchange": "kraken", "pair": pair, "rows": len(rows)}, ensure_ascii=False)); return store(conn, "kraken", pair, rows, url)

def collect_bitstamp(conn: sqlite3.Connection, pair: str, limit: int) -> int:
    source_pair = "btcusd" if pair == "BTC-USD" else "ethusd"
    url = "https://www.bitstamp.net/api/v2/ohlc/" + source_pair + "/?" + urlencode({"step": GRANULARITY_SECONDS, "limit": limit, "exclude_current_candle": "true"})
    payload = get_json(url); raw_rows = payload["data"]["ohlc"]
    rows = [(int(row["timestamp"]), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"]), row) for row in raw_rows]
    print(json.dumps({"exchange": "bitstamp", "pair": pair, "rows": len(rows)}, ensure_ascii=False)); return store(conn, "bitstamp", pair, rows, url)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coinbase-days", type=int, default=90)
    parser.add_argument("--bitstamp-limit", type=int, default=720)
    parser.add_argument("--pause-seconds", type=float, default=0.15)
    args = parser.parse_args()
    end = datetime.now(timezone.utc); start = end - timedelta(days=args.coinbase_days)
    conn = sqlite3.connect(DB); create_table(conn)
    summary = []
    for pair in PAIRS:
        summary.append({"exchange": "coinbase", "pair": pair, "rows_seen": collect_coinbase(conn, pair, start, end, args.pause_seconds)})
        summary.append({"exchange": "kraken", "pair": pair, "rows_seen": collect_kraken(conn, pair)})
        summary.append({"exchange": "bitstamp", "pair": pair, "rows_seen": collect_bitstamp(conn, pair, args.bitstamp_limit)})
    conn.close(); print(json.dumps({"bar": BAR, "summary": summary, "collected_at": end.isoformat()}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
