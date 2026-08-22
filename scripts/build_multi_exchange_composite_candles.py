"""Build quality-gated composite OHLCV without overwriting exchange raw candles."""
from __future__ import annotations
import argparse, json, math, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "exchange_data.db"

def is_valid_ohlc(row: dict) -> bool:
    values = (row["open"], row["high"], row["low"], row["close"], row["volume"])
    if not all(value is not None and math.isfinite(float(value)) for value in values): return False
    op, high, low, close, volume = (float(value) for value in values)
    return op > 0 and high >= max(op, close) and low <= min(op, close) and low > 0 and volume >= 0

def evaluate_bucket(candidates: list[dict], min_sources: int, max_deviation_bps: float) -> dict:
    valid = [item for item in candidates if is_valid_ohlc(item)]
    invalid = [{"exchange": item["exchange"], "reason": "invalid_ohlc"} for item in candidates if not is_valid_ohlc(item)]
    if len(valid) < min_sources:
        return {"accepted": False, "reason": "insufficient_valid_sources", "included": [], "excluded": invalid, "median_close": None, "max_deviation_bps": None}
    center = float(median([float(item["close"]) for item in valid]))
    included, excluded = [], invalid[:]
    for item in valid:
        deviation_bps = abs(float(item["close"]) - center) / center * 10_000
        if deviation_bps <= max_deviation_bps:
            included.append({**item, "deviation_bps": deviation_bps})
        else:
            excluded.append({"exchange": item["exchange"], "reason": "close_deviation", "deviation_bps": deviation_bps})
    if len(included) < min_sources:
        return {"accepted": False, "reason": "insufficient_consistent_sources", "included": included, "excluded": excluded, "median_close": center, "max_deviation_bps": max((item["deviation_bps"] for item in included), default=None)}
    return {"accepted": True, "reason": "accepted", "included": included, "excluded": excluded, "median_close": center, "max_deviation_bps": max(item["deviation_bps"] for item in included)}

def weighted(items: list[dict], field: str) -> float:
    total_volume = sum(float(item["volume"]) for item in items)
    if total_volume <= 0: return float(median([float(item[field]) for item in items]))
    return sum(float(item[field]) * float(item["volume"]) for item in items) / total_volume

def create_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS multi_exchange_composite_candles (
        pair TEXT NOT NULL, bar TEXT NOT NULL, open_time_ms INTEGER NOT NULL,
        open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL,
        median_close REAL NOT NULL, source_count INTEGER NOT NULL, candidate_source_count INTEGER NOT NULL,
        max_deviation_bps REAL NOT NULL, excluded_sources_json TEXT NOT NULL, source_records_json TEXT NOT NULL,
        quality_status TEXT NOT NULL, built_at TEXT NOT NULL,
        PRIMARY KEY(pair, bar, open_time_ms))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS multi_exchange_candle_quality_events (
        pair TEXT NOT NULL, bar TEXT NOT NULL, open_time_ms INTEGER NOT NULL, exchange TEXT NOT NULL,
        status TEXT NOT NULL, reason TEXT, deviation_bps REAL, close REAL, source_payload_json TEXT,
        assessed_at TEXT NOT NULL, PRIMARY KEY(pair, bar, open_time_ms, exchange))""")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-sources", type=int, default=2)
    parser.add_argument("--max-deviation-bps", type=float, default=100.0)
    args = parser.parse_args()
    if args.min_sources < 2: raise ValueError("min-sources must be at least 2 to avoid single-venue composites")
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row; create_tables(conn)
    raw_rows = [dict(row) for row in conn.execute("SELECT exchange,pair,bar,open_time_ms,open,high,low,close,volume,payload_json FROM public_exchange_candle_history_raw WHERE bar='1H' ORDER BY pair,open_time_ms,exchange")]
    buckets: dict[tuple[str, str, int], list[dict]] = {}
    for row in raw_rows: buckets.setdefault((row["pair"], row["bar"], row["open_time_ms"]), []).append(row)
    built_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(); accepted = rejected = events = 0
    for (pair, bar, open_time_ms), candidates in buckets.items():
        assessment = evaluate_bucket(candidates, args.min_sources, args.max_deviation_bps)
        for item in candidates:
            included = next((candidate for candidate in assessment["included"] if candidate["exchange"] == item["exchange"]), None)
            excluded = next((candidate for candidate in assessment["excluded"] if candidate["exchange"] == item["exchange"]), None)
            event_reason = None if included else ((excluded or {}).get("reason") or assessment["reason"])
            conn.execute("INSERT OR REPLACE INTO multi_exchange_candle_quality_events VALUES (?,?,?,?,?,?,?,?,?,?)", (
                pair, bar, open_time_ms, item["exchange"], "accepted" if included else "excluded", event_reason,
                included["deviation_bps"] if included else (excluded or {}).get("deviation_bps"), item["close"], item["payload_json"], built_at)); events += 1
        if not assessment["accepted"]:
            rejected += 1; continue
        included = assessment["included"]
        conn.execute("INSERT OR REPLACE INTO multi_exchange_composite_candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            pair, bar, open_time_ms, weighted(included, "open"), max(float(item["high"]) for item in included), min(float(item["low"]) for item in included),
            weighted(included, "close"), sum(float(item["volume"]) for item in included), assessment["median_close"], len(included), len(candidates), assessment["max_deviation_bps"],
            json.dumps(assessment["excluded"], ensure_ascii=False), json.dumps([{key: item[key] for key in ("exchange", "open", "high", "low", "close", "volume", "payload_json")} for item in included], ensure_ascii=False), "accepted", built_at)); accepted += 1
    conn.commit(); conn.close()
    print(json.dumps({"buckets": len(buckets), "accepted_composites": accepted, "rejected_buckets": rejected, "quality_events": events, "min_sources": args.min_sources, "max_deviation_bps": args.max_deviation_bps, "built_at": built_at}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
