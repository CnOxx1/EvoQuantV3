"""Verify EvoQuant's final public-data coverage without PowerShell wrappers."""

from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "api" / "routers" / "status.py"
DATABASES = {
    "exchange": ROOT / "database" / "exchange_data.db",
    "market": ROOT / "database" / "market_data.db",
    "analytics": ROOT / "database" / "analytics.db",
}
EXPECTED_ACTIVE = {
    "exchange", "derivatives", "orderflow", "orderbook_depth",
    "technical_indicators", "feature_standardization", "cross_asset",
    "portfolio_risk", "macro", "news", "onchain", "options", "defi",
    "governance", "gas_network", "mev", "mempool", "miner",
    "stablecoin_flow", "regime_detection",
}
EXPECTED_EMPTY = {
    "anomaly_detection",
}


def load_registry() -> dict[str, dict[str, str]]:
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "DOMAIN_REGISTRY" and node.value is not None:
                return ast.literal_eval(node.value)
    raise RuntimeError("DOMAIN_REGISTRY was not found")


def row_count(database: Path, table: str) -> int | None:
    connection = sqlite3.connect(database)
    try:
        present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not present:
            return None
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports" / "public_data_coverage_final.json"
    )
    args = parser.parse_args()

    try:
        with urlopen(f"{args.base_url.rstrip('/')}/status/", timeout=15) as response:
            api = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 1

    registry = load_registry()
    domains = api["domains"]
    evidence = {
        domain: {
            "api_status": domains[domain]["status"],
            "database": config["db"],
            "table": config["table"],
            "row_count": row_count(DATABASES[config["db"]], config["table"]),
        }
        for domain, config in registry.items()
    }
    checks = {
        "no_error_domains": api["summary"].get("error") == 0,
        "all_expected_public_domains_active": all(
            evidence[domain]["api_status"] == "active" and (evidence[domain]["row_count"] or 0) > 0
            for domain in EXPECTED_ACTIVE
        ),
        "expected_internal_domains_are_empty_not_error": all(
            evidence[domain]["api_status"] == "empty" for domain in EXPECTED_EMPTY
        ),
        "unavailable_domains_are_explicitly_disabled": api["summary"].get("disabled") == 14,
    }
    result = {
        "status": "passed" if all(checks.values()) else "failed",
        "api_summary": api["summary"],
        "checks": checks,
        "domains": evidence,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n已写入最终覆盖验证: {args.output}")
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
