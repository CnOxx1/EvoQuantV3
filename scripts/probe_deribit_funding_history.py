"""Print a compact availability summary for Deribit public funding history."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def main() -> int:
    end = datetime.now(timezone.utc); start = end - timedelta(days=1)
    url = "https://www.deribit.com/api/v2/public/get_funding_rate_history?" + urlencode({
        "instrument_name": "BTC-PERPETUAL", "start_timestamp": int(start.timestamp() * 1000), "end_timestamp": int(end.timestamp() * 1000)})
    try:
        with urlopen(Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0"}), timeout=30) as response: payload = json.load(response)
        rows = payload.get("result") or []
        print(json.dumps({"available": isinstance(rows, list), "rows": len(rows), "first": rows[0] if rows else None, "last": rows[-1] if rows else None, "source_url": url}, ensure_ascii=False))
        return 0 if isinstance(rows, list) else 1
    except Exception as exc:
        print(json.dumps({"available": False, "error": str(exc), "source_url": url}, ensure_ascii=False)); return 1
if __name__ == "__main__": raise SystemExit(main())
