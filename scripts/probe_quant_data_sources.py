"""Probe candidate public API endpoints before adding them to the data layer."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def get_json(url: str):
    request = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)

def probe(name: str, url: str, extractor):
    try:
        payload = get_json(url)
        sample, count = extractor(payload)
        return {"name": name, "available": True, "count": count, "sample": sample, "source_url": url}
    except Exception as exc:
        return {"name": name, "available": False, "error": str(exc), "source_url": url}

def main() -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)
    deribit_url = "https://www.deribit.com/api/v2/public/get_funding_rate_history?" + urlencode({
        "instrument_name": "BTC-PERPETUAL", "start_timestamp": int(start.timestamp() * 1000),
        "end_timestamp": int(end.timestamp() * 1000),
    })
    probes = [
        probe("okx_history_candles", "https://www.okx.com/api/v5/market/history-candles?instId=BTC-USDT&bar=1H&limit=5", lambda p: (p.get("data", [None])[0], len(p.get("data", [])))),
        probe("okx_funding_history", "https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=5", lambda p: (p.get("data", [None])[0], len(p.get("data", [])))),
        probe("deribit_funding_history", deribit_url, lambda p: ((p.get("result") or [None])[0], len(p.get("result") or []))),
        probe("ethereum_network_snapshot", "https://api.blockchair.com/ethereum/stats", lambda p: (p.get("data"), 1 if p.get("data") else 0)),
    ]
    print(json.dumps({"probed_at": end.isoformat(), "probes": probes}, ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
