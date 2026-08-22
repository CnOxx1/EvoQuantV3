"""Report the entity keys and sample counts in analytics merged_klines."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "database" / "analytics.db"


def main() -> int:
    connection = sqlite3.connect(DATABASE)
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(merged_klines)")]
        key_column = next((name for name in ("entity_key", "symbol", "asset") if name in columns), None)
        time_column = next((name for name in ("open_time", "timestamp", "created_at") if name in columns), None)
        if key_column is None or time_column is None:
            raise RuntimeError(f"merged_klines schema lacks a usable key/time column: {columns}")
        rows = connection.execute(
            """
            SELECT {key}, COUNT(*) AS samples, MIN({time}), MAX({time})
            FROM merged_klines
            GROUP BY {key}
            ORDER BY samples DESC, {key}
            """.format(key=key_column, time=time_column)
        ).fetchall()
    finally:
        connection.close()
    print(
        json.dumps(
            {
                "database": str(DATABASE),
                "columns": columns,
                "key_column": key_column,
                "time_column": time_column,
                "entities": [
                    {"entity_key": key, "samples": samples, "first": first, "last": last}
                    for key, samples, first, last in rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
