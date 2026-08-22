"""Audit row counts and latest timestamps for all active EvoQuant domains."""

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
TIME_COLUMNS = ("collected_at", "timestamp", "created_at", "snapshot_time", "open_time", "as_of", "ts")


def load_registry() -> dict[str, dict[str, str]]:
    tree = ast.parse(REGISTRY_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "DOMAIN_REGISTRY" and node.value is not None:
                return ast.literal_eval(node.value)
    raise RuntimeError("DOMAIN_REGISTRY was not found")


def table_freshness(database: Path, table: str) -> dict[str, object]:
    connection = sqlite3.connect(database)
    try:
        columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
        count = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        time_column = next((name for name in TIME_COLUMNS if name in columns), None)
        latest = None
        if count and time_column:
            latest = connection.execute(f'SELECT MAX("{time_column}") FROM "{table}"').fetchone()[0]
        return {"row_count": count, "time_column": time_column, "latest": latest}
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "active_domain_freshness.json")
    args = parser.parse_args()
    try:
        with urlopen(f"{args.base_url.rstrip('/')}/status/", timeout=15) as response:
            api = json.load(response)
    except (URLError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, ensure_ascii=False))
        return 1

    registry = load_registry()
    active = {}
    for domain, config in registry.items():
        if api["domains"].get(domain, {}).get("status") != "active":
            continue
        active[domain] = {
            "database": config["db"],
            "table": config["table"],
            **table_freshness(DATABASES[config["db"]], config["table"]),
        }

    result = {
        "status": "passed" if api["summary"].get("error") == 0 and active else "failed",
        "api_summary": api["summary"],
        "active_domains": active,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
