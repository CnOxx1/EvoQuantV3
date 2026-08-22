"""Probe public 1-hour OHLC endpoints before production multi-exchange ingestion."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def get_json(url: str):
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response: return json.load(response)

def check(name: str, pair: str, url: str, rows_fn):
    try:
        rows = rows_fn(get_json(url))
        timestamps = [int(row[0]) for row in rows]
        return {"exchange": name, "pair": pair, "available": True, "rows": len(rows), "first_time_ms": min(timestamps) * 1000, "last_time_ms": max(timestamps) * 1000, "sample": rows[0] if rows else None, "source_url": url}
    except Exception as exc:
        return {"exchange": name, "pair": pair, "available": False, "error": str(exc), "source_url": url}

def main() -> int:
    now = datetime.now(timezone.utc); start = now - timedelta(days=3)
    outcome = []
    for product in ("BTC-USD", "ETH-USD"):
        url = "https://api.exchange.coinbase.com/products/" + product + "/candles?" + urlencode({"granularity": 3600, "start": start.isoformat(), "end": now.isoformat()})
        outcome.append(check("coinbase", product, url, lambda data: data))
    for pair in ("XBTUSD", "ETHUSD"):
        url = "https://api.kraken.com/0/public/OHLC?" + urlencode({"pair": pair, "interval": 60})
        outcome.append(check("kraken", "BTC-USD" if pair == "XBTUSD" else "ETH-USD", url, lambda data: next(value for key, value in data["result"].items() if key != "last")))
    for pair in ("btcusd", "ethusd"):
        url = "https://www.bitstamp.net/api/v2/ohlc/" + pair + "/?" + urlencode({"step": 3600, "limit": 72})
        outcome.append(check("bitstamp", "BTC-USD" if pair == "btcusd" else "ETH-USD", url, lambda data: [[int(row["timestamp"]), row["open"], row["high"], row["low"], row["close"], row["volume"]] for row in data["data"]["ohlc"]]))
    print(json.dumps({"probed_at": now.isoformat(), "results": outcome}, ensure_ascii=False, indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
