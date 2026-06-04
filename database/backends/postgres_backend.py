"""PostgresBackend — PostgreSQL 实现：psycopg2 + ThreadedConnectionPool。"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional, Sequence

from loguru import logger

from database.backends.base import DatabaseBackend


class _DictRow(dict):
    """兼容 sqlite3.Row 的字典行，支持 row["col"] 访问。"""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


class PostgresBackend(DatabaseBackend):
    """PostgreSQL 后端，使用 psycopg2 连接池。

    需要安装: psycopg2-binary
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "evoquant",
        user: str = "evoquant",
        password: str = "",
        schema: str = "public",
        pool_min: int = 5,
        pool_max: int = 20,
    ):
        self._dsn_params = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
        }
        self._schema = schema
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool: Any = None
        self._pool_lock = threading.Lock()
        self._local = threading.local()

    def _ensure_pool(self) -> Any:
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    try:
                        import psycopg2
                        from psycopg2 import pool as pg_pool
                    except ImportError:
                        raise ImportError(
                            "psycopg2-binary is required for PostgreSQL backend. "
                            "Install with: pip install psycopg2-binary==2.9.9"
                        )
                    self._pool = pg_pool.ThreadedConnectionPool(
                        self._pool_min,
                        self._pool_max,
                        **self._dsn_params,
                    )
                    logger.info(
                        "PostgreSQL pool created: {}@{}:{}/{} (min={}, max={})",
                        self._dsn_params["user"],
                        self._dsn_params["host"],
                        self._dsn_params["port"],
                        self._dsn_params["database"],
                        self._pool_min,
                        self._pool_max,
                    )
        return self._pool

    def _get_conn(self) -> Any:
        conn = getattr(self._local, "conn", None)
        if conn is None or conn.closed:
            pool = self._ensure_pool()
            conn = pool.getconn()
            conn.autocommit = False
            self._local.conn = conn
            # 设置 search_path：包含所有业务 schema 以支持跨域查询
            with conn.cursor() as cur:
                cur.execute(
                    f"SET search_path TO {self._schema}, exchange_data, market_data, analytics, public"
                )
        return conn

    def _rows_to_dicts(self, cursor: Any) -> list[_DictRow]:
        """将 psycopg2 cursor 结果转为 _DictRow 列表。"""
        if cursor.description is None:
            return []
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [_DictRow(zip(columns, row)) for row in rows]

    def execute(self, sql: str, params: Sequence = ()) -> Any:
        from database.backends.query_adapter import adapt_query
        adapted_sql = adapt_query(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(adapted_sql, params)
                return cur
        except Exception as exc:
            # 自动回滚以避免 InFailedSqlTransaction 级联错误
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def executemany(self, sql: str, params_list: Sequence[Sequence]) -> Any:
        from database.backends.query_adapter import adapt_query
        adapted_sql = adapt_query(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.executemany(adapted_sql, params_list)
                return cur
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def fetch_one(self, sql: str, params: Sequence = ()) -> Optional[_DictRow]:
        from database.backends.query_adapter import adapt_query
        adapted_sql = adapt_query(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(adapted_sql, params)
                if cur.description is None:
                    conn.commit()
                    return None
                columns = [desc[0] for desc in cur.description]
                row = cur.fetchone()
                conn.commit()
                if row is None:
                    return None
                return _DictRow(zip(columns, row))
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[_DictRow]:
        from database.backends.query_adapter import adapt_query
        adapted_sql = adapt_query(sql)
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(adapted_sql, params)
                result = self._rows_to_dicts(cur)
                conn.commit()
                return result
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def commit(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn and not conn.closed:
            conn.commit()

    def rollback(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn and not conn.closed:
            conn.rollback()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn and not conn.closed:
            pool = self._pool
            if pool:
                pool.putconn(conn)
            self._local.conn = None

    def close_pool(self) -> None:
        """关闭整个连接池。"""
        if self._pool:
            with self._pool_lock:
                if self._pool:
                    self._pool.closeall()
                    self._pool = None
                    logger.info("PostgreSQL pool closed")

    def health_check(self) -> dict[str, Any]:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                            (self._dsn_params["database"],))
                active_conns = cur.fetchone()[0]
            conn.commit()
            return {
                "backend": "postgres",
                "status": "healthy",
                "host": self._dsn_params["host"],
                "port": self._dsn_params["port"],
                "database": self._dsn_params["database"],
                "schema": self._schema,
                "pool_min": self._pool_min,
                "pool_max": self._pool_max,
                "active_connections": active_conns,
            }
        except Exception as exc:
            return {
                "backend": "postgres",
                "status": "unhealthy",
                "error": str(exc),
            }

    @property
    def is_connected(self) -> bool:
        try:
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
            return True
        except Exception:
            return False
