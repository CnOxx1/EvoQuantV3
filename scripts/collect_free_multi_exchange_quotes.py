"""Collect public BTC/ETH spot quotes from Kraken and Coinbase without API keys."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
SOURCES = {
    "kraken": {"BTC/USD": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD", "ETH/USD": "https://api.kraken.com/0/public/Ticker?pair=ETHUSD"},
    "coinbase": {"BTC/USD": "https://api.exchange.coinbase.com/products/BTC-USD/ticker", "ETH/USD": "https://api.exchange.coinbase.com/products/ETH-USD/ticker"},
}

def load(url: str):
    with urlopen(Request(url, headers={"User-Agent":"EvoQuant-FreeDataLayer/1.0"}), timeout=20) as r: return json.load(r)

def main() -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(); rows=[]
    for exchange, pairs in SOURCES.items():
        for pair, url in pairs.items():
            raw=load(url)
            if exchange == "kraken":
                value=next(iter(raw["result"].values())); bid, ask, last, vol=value["b"][0],value["a"][0],value["c"][0],value["v"][1]
            else: bid,ask,last,vol=raw.get("bid"),raw.get("ask"),raw.get("price"),raw.get("volume")
            rows.append((exchange,pair,float(bid),float(ask),float(last),float(vol),now,url,json.dumps(raw,ensure_ascii=False)))
    conn=sqlite3.connect(DB); conn.execute("""CREATE TABLE IF NOT EXISTS public_exchange_quote_snapshots (
        exchange TEXT,pair TEXT,bid REAL,ask REAL,last REAL,volume_24h REAL,observed_at TEXT,source_url TEXT,raw_json TEXT,
        PRIMARY KEY(exchange,pair,observed_at))"""); conn.executemany("INSERT INTO public_exchange_quote_snapshots VALUES (?,?,?,?,?,?,?,?,?)",rows); conn.commit(); conn.close(); print(json.dumps({"quotes":len(rows),"observed_at":now})); return 0

if __name__ == "__main__": raise SystemExit(main())
