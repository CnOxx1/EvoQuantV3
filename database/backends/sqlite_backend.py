"""SQLiteBackend — SQLite 实现（从现有 DBManager 逻辑提取）。"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any, Optional, Sequence

from loguru import logger

from database.backends.base import DatabaseBackend


class SQLiteBackend(DatabaseBackend):
    """SQLite 后端实现，保留原 DBManager 的 WAL + thread-local 特性。"""

    def __init__(self, db_path: str, timeout: int = 30):
        self.db_path = db_path
        self._timeout = timeout
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._local = threading.local()
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.Lock()

    @property
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self._timeout,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
            with self._connections_lock:
                self._connections[threading.get_ident()] = conn
        return conn

    def execute(self, sql: str, params: Sequence = ()) -> Any:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: Sequence[Sequence]) -> Any:
        return self._conn.executemany(sql, params_list)

    def fetch_one(self, sql: str, params: Sequence = ()) -> Optional[Any]:
        cursor = self._conn.execute(sql, params)
        return cursor.fetchone()

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[Any]:
        cursor = self._conn.execute(sql, params)
        return cursor.fetchall()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        with self._connections_lock:
            for tid, conn in self._connections.items():
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
        self._local.conn = None

    def health_check(self) -> dict[str, Any]:
        try:
            self._conn.execute("SELECT 1")
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                "backend": "sqlite",
                "status": "healthy",
                "db_path": self.db_path,
                "db_size_bytes": db_size,
                "active_connections": len(self._connections),
                "wal_mode": True,
            }
        except Exception as exc:
            return {
                "backend": "sqlite",
                "status": "unhealthy",
                "error": str(exc),
            }

    @property
    def is_connected(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False
