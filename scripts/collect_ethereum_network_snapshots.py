"""Collect free Ethereum network facts from a verified public stats endpoint."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "market_data.db"
SOURCE_URL = "https://api.blockchair.com/ethereum/stats"

def main() -> int:
    request = Request(SOURCE_URL, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response: payload = json.load(response)
    data = payload.get("data")
    if not isinstance(data, dict): raise RuntimeError("Blockchair Ethereum stats response has no data object")
    observed_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS ethereum_network_snapshots (
        observed_at TEXT PRIMARY KEY, blocks_24h INTEGER, transactions_24h INTEGER,
        average_transaction_fee_usd_24h REAL, median_transaction_fee_usd_24h REAL,
        average_simple_transaction_fee_usd_24h REAL, median_simple_transaction_fee_usd_24h REAL,
        market_price_usd REAL, payload_json TEXT NOT NULL, source_url TEXT NOT NULL)""")
    conn.execute("INSERT INTO ethereum_network_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", (
        observed_at, data.get("blocks_24h"), data.get("transactions_24h"), data.get("average_transaction_fee_usd_24h"),
        data.get("median_transaction_fee_usd_24h"), data.get("average_simple_transaction_fee_usd_24h"),
        data.get("median_simple_transaction_fee_usd_24h"), data.get("market_price_usd"),
        json.dumps(data, ensure_ascii=False, sort_keys=True), SOURCE_URL))
    conn.commit(); conn.close()
    print(json.dumps({"observed_at": observed_at, "transactions_24h": data.get("transactions_24h"), "blocks_24h": data.get("blocks_24h"), "source_url": SOURCE_URL}, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
