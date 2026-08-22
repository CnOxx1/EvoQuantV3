"""Probe CoinGecko's public project-category endpoint without credentials."""
from __future__ import annotations
import json
from urllib.request import Request, urlopen

URL = "https://api.coingecko.com/api/v3/coins/categories/list"
def main() -> int:
    try:
        request = Request(URL, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0"})
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
        first = body[0] if isinstance(body, list) and body else None
        print(json.dumps({"available": isinstance(body, list), "count": len(body) if isinstance(body, list) else 0, "sample": first, "source_url": URL}, ensure_ascii=False))
        return 0 if isinstance(body, list) else 2
    except Exception as exc:
        print(json.dumps({"available": False, "error": str(exc), "source_url": URL}, ensure_ascii=False))
        return 1
if __name__ == "__main__": raise SystemExit(main())
