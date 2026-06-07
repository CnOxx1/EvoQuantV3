"""查询性能分析工具 — EXPLAIN QUERY PLAN + 执行时间统计。

提供 SQLite 查询计划分析、慢查询检测、索引使用率统计，
以及自动 ANALYZE 调度功能。

使用方式：
    from database.query_profiler import QueryProfiler

    profiler = QueryProfiler(conn)
    plan = profiler.explain("SELECT * FROM klines WHERE symbol = ?", ("BTC/USDT",))
    profiler.run_analyze()  # 更新查询优化器统计
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Optional

from loguru import logger

# 环境变量配置
DB_QUERY_PROFILER_ENABLED = os.environ.get("DB_QUERY_PROFILER", "0") == "1"
DB_SLOW_QUERY_MS = float(os.environ.get("DB_SLOW_QUERY_MS", "100"))
DB_AUTO_ANALYZE = os.environ.get("DB_AUTO_ANALYZE", "1") == "1"
_ANALYZE_COOLDOWN_SECONDS = 600  # 10 分钟限频


class QueryProfiler:
    """SQL 查询性能分析器。

    功能：
    - EXPLAIN QUERY PLAN 分析（SQLite）
    - 查询执行时间记录与慢查询检测
    - 索引使用率统计
    - 自动 ANALYZE 调度（限频防止过于频繁）
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        slow_threshold_ms: float = DB_SLOW_QUERY_MS,
        enabled: bool = DB_QUERY_PROFILER_ENABLED,
    ):
        self._conn = conn
        self._slow_threshold_ms = slow_threshold_ms
        self._enabled = enabled
        self._stats: list[dict] = []
        self._last_analyze_time: float = 0.0
        self._total_queries = 0
        self._slow_queries = 0
        self._index_hits = 0
        self._full_scans = 0

    def explain(self, sql: str, params: tuple = ()) -> list[dict]:
        """执行 EXPLAIN QUERY PLAN，返回查询计划。"""
        plan_rows = self._conn.execute(
            f"EXPLAIN QUERY PLAN {sql}", params
        ).fetchall()
        return [
            {"id": row[0], "parent": row[1], "detail": row[3]}
            for row in plan_rows
        ]

    def profile(self, sql: str, params: tuple = ()) -> dict:
        """执行查询并返回耗时 + 查询计划 + 是否使用索引。"""
        if not self._enabled:
            return {}

        plan = self.explain(sql, params)
        start = time.perf_counter()
        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()
        elapsed_ms = (time.perf_counter() - start) * 1000

        uses_index = any("USING INDEX" in p.get("detail", "") for p in plan)
        is_scan = any(
            "SCAN" in p.get("detail", "") and "USING INDEX" not in p.get("detail", "")
            for p in plan
        )

        self._total_queries += 1
        if uses_index:
            self._index_hits += 1
        if is_scan:
            self._full_scans += 1

        entry = {
            "sql": sql[:200],
            "elapsed_ms": round(elapsed_ms, 2),
            "row_count": len(rows),
            "plan": plan,
            "uses_index": uses_index,
            "is_full_scan": is_scan,
        }

        if elapsed_ms > self._slow_threshold_ms:
            self._slow_queries += 1
            logger.warning(
                "慢查询 ({:.1f}ms, {} rows): {} — plan: {}",
                elapsed_ms, len(rows), sql[:100], plan,
            )
            self._stats.append(entry)

        return entry

    def run_analyze(self) -> None:
        """执行 ANALYZE 更新查询优化器统计信息（限频：10 分钟最多一次）。"""
        now = time.time()
        if now - self._last_analyze_time < _ANALYZE_COOLDOWN_SECONDS:
            logger.debug(
                "ANALYZE 跳过（冷却中，距上次 {:.0f}s）",
                now - self._last_analyze_time,
            )
            return
        self._conn.execute("ANALYZE")
        self._last_analyze_time = now
        logger.info("ANALYZE 执行完成 — 查询优化器统计已更新")

    def maybe_analyze_after_write(self, rows_written: int) -> None:
        """大批量写入后有条件地执行 ANALYZE。"""
        if not DB_AUTO_ANALYZE:
            return
        if rows_written >= 10000:
            self.run_analyze()

    def get_stats(self) -> dict:
        """返回查询性能统计摘要。"""
        return {
            "total_queries": self._total_queries,
            "slow_queries": self._slow_queries,
            "index_hits": self._index_hits,
            "full_scans": self._full_scans,
            "index_hit_rate_pct": round(
                self._index_hits * 100 / self._total_queries, 1
            ) if self._total_queries else 0.0,
            "recent_slow": self._stats[-10:],  # 最近 10 条慢查询
        }

    def suggest_missing_indexes(self) -> list[str]:
        """基于收集的慢查询统计建议可能缺失的索引。"""
        suggestions = []
        for entry in self._stats:
            if entry.get("is_full_scan") and entry.get("elapsed_ms", 0) > 200:
                suggestions.append(
                    f"慢全表扫描 ({entry['elapsed_ms']:.0f}ms): {entry['sql']}"
                )
        return suggestions
