"""Backfill free Bitcoin on-chain daily facts from Blockchain.com public charts."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "market_data.db"
METRICS = {"n-transactions": "confirmed_transactions", "n-unique-addresses": "active_addresses", "transaction-fees": "transaction_fees_btc"}

def main() -> int:
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS bitcoin_onchain_history (
        metric TEXT NOT NULL, observed_at TEXT NOT NULL, value REAL NOT NULL,
        unit TEXT, source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
        PRIMARY KEY(metric, observed_at))""")
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(); inserted = 0
    for endpoint, metric in METRICS.items():
        url = f"https://api.blockchain.info/charts/{endpoint}?" + urlencode({"timespan":"365days", "format":"json"})
        with urlopen(Request(url, headers={"User-Agent":"EvoQuant-FreeDataLayer/1.0"}), timeout=30) as response: payload = json.load(response)
        for point in payload["values"]:
            observed = datetime.fromtimestamp(point["x"], tz=timezone.utc).replace(tzinfo=None).isoformat()
            conn.execute("""INSERT INTO bitcoin_onchain_history VALUES (?,?,?,?,?,?)
                ON CONFLICT(metric, observed_at) DO UPDATE SET value=excluded.value, collected_at=excluded.collected_at""",
                (metric, observed, float(point["y"]), payload.get("unit"), url, now)); inserted += 1
    conn.commit(); conn.close(); print(json.dumps({"rows_seen": inserted, "collected_at": now}, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
