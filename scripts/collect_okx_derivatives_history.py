"""Collect free raw OKX derivatives facts without invoking research or strategy code."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"
BASE = "https://www.okx.com/api/v5"
SYMBOLS = ("BTC-USDT", "ETH-USDT")

def get(path: str, **params):
    req = Request(f"{BASE}{path}?{urlencode(params)}", headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0"})
    with urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if payload.get("code") != "0": raise RuntimeError(payload)
    return payload["data"]

def main() -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS okx_derivatives_raw (
        kind TEXT NOT NULL, instrument TEXT NOT NULL, observed_at TEXT NOT NULL,
        payload_json TEXT NOT NULL, source_url TEXT NOT NULL,
        PRIMARY KEY(kind, instrument, observed_at, payload_json))""")
    total = 0
    for uly in SYMBOLS:
        swap = f"{uly}-SWAP"
        batches = [
            ("open_interest", swap, get("/public/open-interest", instType="SWAP", instId=swap)),
            ("funding_history", swap, get("/public/funding-rate-history", instId=swap, limit=100)),
            ("liquidations", uly, get("/public/liquidation-orders", instType="SWAP", uly=uly, state="filled", limit=100)),
        ]
        spot = get("/market/ticker", instId=uly)[0]
        perp = get("/market/ticker", instId=swap)[0]
        basis = {"spot_last": spot.get("last"), "perp_last": perp.get("last"), "basis": float(perp["last"])-float(spot["last"]), "ts": now}
        batches.append(("basis_snapshot", swap, [basis]))
        for kind, instrument, rows in batches:
            for row in rows:
                ts = str(row.get("fundingTime") or row.get("ts") or row.get("time") or now)
                conn.execute("INSERT OR IGNORE INTO okx_derivatives_raw VALUES (?,?,?,?,?)", (kind, instrument, ts, json.dumps(row, ensure_ascii=False, sort_keys=True), f"{BASE}"))
                total += 1
    conn.commit(); conn.close()
    print(json.dumps({"rows_seen": total, "symbols": list(SYMBOLS), "collected_at": now}, ensure_ascii=False)); return 0

if __name__ == "__main__": raise SystemExit(main())
