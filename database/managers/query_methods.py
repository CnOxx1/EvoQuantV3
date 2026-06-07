"""QueryMethodsMixin — 通用查询方法（execute/fetch/close）。"""

from __future__ import annotations

import sqlite3
import time
import threading
from typing import Optional

from loguru import logger


class QueryMethodsMixin:
    """查询方法 Mixin — 封装 execute/fetch/close 及慢查询日志。"""

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        self._log_slow(sql, start)
        return cursor

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        start = time.monotonic()
        self.conn.executemany(sql, params_list)
        self._log_slow(sql, start, count=len(params_list))

    def execute_many_chunked(
        self, sql: str, params_list: list[tuple], chunk_size: int = 500
    ) -> int:
        """分块批量写入 — 防止 WAL 压力和内存峰值。"""
        total = 0
        for i in range(0, len(params_list), chunk_size):
            chunk = params_list[i : i + chunk_size]
            self.conn.executemany(sql, chunk)
            total += len(chunk)
        self.conn.commit()
        return total

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        row = cursor.fetchone()
        self._log_slow(sql, start)
        return row

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()
        self._log_slow(sql, start, count=len(rows))
        return rows

    def close(self) -> None:
        """关闭当前线程的数据库连接。"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
            with self._connections_lock:
                self._connections.pop(threading.get_ident(), None)

    def close_all(self) -> None:
        """关闭所有线程的数据库连接。"""
        with self._connections_lock:
            for conn in self._connections.values():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()

    def _log_slow(self, sql: str, start: float, count: int = 0) -> None:
        import os
        threshold_ms = float(os.environ.get("DB_SLOW_QUERY_MS", "100"))
        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > threshold_ms:
            logger.warning(
                "慢查询 ({:.1f}ms{}): {}",
                elapsed_ms,
                f", {count} rows" if count else "",
                sql[:200],
            )
