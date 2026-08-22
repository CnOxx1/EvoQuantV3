"""Incrementally hydrate CoinGecko public categories for locally tracked assets."""
from __future__ import annotations
import argparse, json, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "market_data.db"
BASE_URL = "https://api.coingecko.com/api/v3/coins/"

def get_json(url: str):
    req = Request(url, headers={"User-Agent": "EvoQuant-FreeDataLayer/1.0"})
    with urlopen(req, timeout=30) as resp: return json.load(resp)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Assets to hydrate in this rate-limited run")
    parser.add_argument("--pause-seconds", type=float, default=1.5)
    args = parser.parse_args()
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS asset_project_categories (
        coingecko_id TEXT NOT NULL, category_id TEXT NOT NULL, category_name TEXT,
        collected_at TEXT NOT NULL, source_url TEXT NOT NULL,
        PRIMARY KEY(coingecko_id, category_id))""")
    assets = conn.execute("""SELECT coingecko_id FROM asset_metadata_snapshots
        WHERE coingecko_id NOT IN (SELECT DISTINCT coingecko_id FROM asset_project_categories)
        ORDER BY market_cap_rank IS NULL, market_cap_rank ASC LIMIT ?""", (args.limit,)).fetchall()
    stored = failures = 0
    rate_limited = False
    for index, (asset_id,) in enumerate(assets, start=1):
        url = BASE_URL + asset_id
        try:
            data = get_json(url)
            now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            categories = data.get("categories") or []
            conn.executemany("INSERT OR REPLACE INTO asset_project_categories VALUES (?,?,?,?,?)", [
                (asset_id, str(category).lower().replace(" ", "-"), category, now, url)
                for category in categories
            ])
            conn.commit(); stored += len(categories)
            print(json.dumps({"index": index, "asset": asset_id, "categories": len(categories)}, ensure_ascii=False))
        except HTTPError as exc:
            failures += 1; print(json.dumps({"asset": asset_id, "status": exc.code, "error": str(exc)}, ensure_ascii=False))
            if exc.code == 429:
                rate_limited = True
                break
        except Exception as exc:
            failures += 1; print(json.dumps({"asset": asset_id, "error": str(exc)}, ensure_ascii=False))
        if index < len(assets): time.sleep(args.pause_seconds)
    conn.close()
    print(json.dumps({"assets_attempted": len(assets), "category_rows_stored": stored, "failures": failures,
                      "status": "partial_rate_limited" if rate_limited else ("complete" if failures == 0 else "partial_error")}, ensure_ascii=False))
    return 0 if failures == 0 or rate_limited else 1
if __name__ == "__main__": raise SystemExit(main())
