from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class QueryPattern:
    table_name: str
    columns_used: list[str]
    frequency: int = 0
    avg_latency_ms: float = 0.0


class IndexRecommender:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._patterns: dict[tuple[str, tuple[str, ...]], QueryPattern] = {}
        self._latencies: dict[tuple[str, tuple[str, ...]], list[float]] = defaultdict(list)

    def record_query(self, table: str, columns: list[str], latency_ms: float) -> None:
        key = (table, tuple(sorted(columns)))
        with self._lock:
            self._latencies[key].append(latency_ms)
            lats = self._latencies[key]
            self._patterns[key] = QueryPattern(
                table_name=table,
                columns_used=sorted(columns),
                frequency=len(lats),
                avg_latency_ms=sum(lats) / len(lats),
            )

    def get_recommendations(self, min_frequency: int = 5) -> list[str]:
        with self._lock:
            results = []
            for key, pattern in self._patterns.items():
                if pattern.frequency >= min_frequency and pattern.avg_latency_ms > 100:
                    cols = "_".join(pattern.columns_used)
                    col_list = ", ".join(pattern.columns_used)
                    sql = f"CREATE INDEX IF NOT EXISTS idx_{pattern.table_name}_{cols} ON {pattern.table_name} ({col_list})"
                    results.append(sql)
            return results

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_patterns": len(self._patterns),
                "patterns": [
                    {"table": p.table_name, "columns": p.columns_used,
                     "frequency": p.frequency, "avg_latency_ms": round(p.avg_latency_ms, 2)}
                    for p in self._patterns.values()
                ],
            }


index_recommender = IndexRecommender()
