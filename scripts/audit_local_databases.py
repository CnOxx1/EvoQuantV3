"""只读审计 EvoQuant 本地 SQLite 数据库的表记录量与最新时间。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIME_COLUMNS = ("timestamp", "created_at", "updated_at", "open_time", "event_time", "observed_at", "reported_at")

def audit(path: Path):
    if not path.exists():
        return {"database": path.name, "exists": False, "tables": []}
    conn = sqlite3.connect(path)
    try:
        names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        tables = []
        for name in names:
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{name}")')}
            time_column = next((column for column in TIME_COLUMNS if column in columns), None)
            latest = conn.execute(f'SELECT MAX("{time_column}") FROM "{name}"').fetchone()[0] if time_column and count else None
            tables.append({"table": name, "rows": count, "time_column": time_column, "latest": latest})
        return {"database": path.name, "exists": True, "tables": tables}
    finally:
        conn.close()

if __name__ == "__main__":
    result = [audit(ROOT / "database" / name) for name in ("exchange_data.db", "market_data.db", "analytics.db")]
    print(json.dumps(result, ensure_ascii=False, indent=2))
