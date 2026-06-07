"""ConnectionMixin — 数据库连接管理（线程本地存储）。"""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

from loguru import logger


class ConnectionMixin:
    """数据库连接管理 Mixin — 提供线程安全的连接池。"""

    def __init__(self, db_path: Optional[str] = None):
        from config.settings import DATABASE_PATH

        self.db_path = db_path or DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30,
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
