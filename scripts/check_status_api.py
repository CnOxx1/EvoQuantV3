"""Fetch and validate EvoQuant's live data-domain status endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_DISABLED = {
    "etf_flow",
    "whale_tracker",
    "whale_pnl",
    "social_sentiment",
    "nft_market",
    "dex_trade_flow",
    "regulatory",
    "onchain_address",
    "derivatives_sentiment",
    "onchain_holder",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    url = f"{args.base_url.rstrip('/')}/status/"

    try:
        with urlopen(url, timeout=15) as response:
            payload = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "url": url, "error": str(exc)}, ensure_ascii=False))
        return 1

    domains = payload.get("domains", {})
    checks = {
        "cross_asset_active": domains.get("cross_asset", {}).get("status") == "active",
        "stablecoin_no_table_error": domains.get("stablecoin_flow", {}).get("status") != "error",
        "commercial_domains_disabled": all(
            domains.get(domain, {}).get("status") == "disabled" for domain in DEFAULT_DISABLED
        ),
    }
    result = {
        "status": "passed" if all(checks.values()) else "failed",
        "url": url,
        "summary": payload.get("summary", {}),
        "checks": checks,
        "focus_domains": {
            name: domains.get(name)
            for name in ("cross_asset", "stablecoin_flow", *sorted(DEFAULT_DISABLED))
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
