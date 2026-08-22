"""Collect free CoinGecko asset metadata and current supply snapshots into market_data.db."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "market_data.db"
URL = "https://api.coingecko.com/api/v3/coins/markets?" + urlencode({
    "vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1,
    "sparkline": "false", "price_change_percentage": "1h,24h,7d,30d,1y",
})

def main() -> int:
    request = Request(URL, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0"})
    with urlopen(request, timeout=30) as response:
        rows = json.load(response)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS asset_metadata_snapshots (
        coingecko_id TEXT PRIMARY KEY, symbol TEXT, name TEXT, market_cap_rank INTEGER,
        circulating_supply REAL, total_supply REAL, max_supply REAL, market_cap REAL,
        total_volume REAL, source_updated_at TEXT, collected_at TEXT NOT NULL, source_url TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS asset_exchange_pair_mappings (
        asset_symbol TEXT, exchange TEXT, pair TEXT, collected_at TEXT NOT NULL,
        PRIMARY KEY(asset_symbol, exchange, pair))""")
    conn.executemany("""INSERT INTO asset_metadata_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(coingecko_id) DO UPDATE SET symbol=excluded.symbol,name=excluded.name,
        market_cap_rank=excluded.market_cap_rank,circulating_supply=excluded.circulating_supply,
        total_supply=excluded.total_supply,max_supply=excluded.max_supply,market_cap=excluded.market_cap,
        total_volume=excluded.total_volume,source_updated_at=excluded.source_updated_at,
        collected_at=excluded.collected_at,source_url=excluded.source_url""", [
        (r["id"], r.get("symbol"), r.get("name"), r.get("market_cap_rank"), r.get("circulating_supply"),
         r.get("total_supply"), r.get("max_supply"), r.get("market_cap"), r.get("total_volume"),
         r.get("last_updated"), now, "https://api.coingecko.com/api/v3/coins/markets") for r in rows])
    try:
        exchange_conn = sqlite3.connect(ROOT / "database" / "exchange_data.db")
        pairs = exchange_conn.execute("SELECT DISTINCT symbol, exchange FROM market_info").fetchall()
        conn.executemany("INSERT OR IGNORE INTO asset_exchange_pair_mappings VALUES (?,?,?,?)", [
            (symbol.split("/")[0], exchange, symbol, now) for symbol, exchange in pairs])
        exchange_conn.close()
    except sqlite3.OperationalError:
        pass
    conn.commit(); conn.close()
    print(json.dumps({"assets": len(rows), "collected_at": now}, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
