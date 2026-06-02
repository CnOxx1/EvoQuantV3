"""BaseAnalyticsRepository — 逻辑层 Repository 基类。

封装分析结果的存储/加载，子类只需声明表结构。

示例：
    class MyRepository(BaseAnalyticsRepository):
        TABLE_NAME = "my_analysis_state"
        COLUMNS = "symbol TEXT, score REAL, updated_at TEXT"

        def save(self, symbol, score, ts):
            self._upsert(symbol=symbol, score=score, updated_at=ts)

        def load_latest(self, symbol):
            return self._fetch_latest("symbol = ?", (symbol,))
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from loguru import logger


class BaseAnalyticsRepository(ABC):
    """逻辑层分析结果持久化基类。"""

    TABLE_NAME: str = ""
    COLUMNS: str = ""  # e.g. "symbol TEXT, score REAL, updated_at TEXT"
    PRIMARY_KEY: str = ""  # e.g. "symbol, updated_at"

    def __init__(self, db: Any):
        self.db = db
        self._table_ensured = False

    def ensure_table(self) -> None:
        """确保表存在（幂等）。"""
        if self._table_ensured:
            return
        if not self.TABLE_NAME or not self.COLUMNS:
            raise NotImplementedError("TABLE_NAME and COLUMNS must be set")
        pk_clause = ""
        if self.PRIMARY_KEY:
            pk_clause = f", PRIMARY KEY ({self.PRIMARY_KEY})"
        sql = (
            f"CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} "
            f"({self.COLUMNS}{pk_clause})"
        )
        self.db.execute(sql)
        self.db.commit()
        self._table_ensured = True

    def save_state(self, **row: Any) -> None:
        """INSERT OR REPLACE 一行数据。"""
        self.ensure_table()
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = (
            f"INSERT OR REPLACE INTO {self.TABLE_NAME} ({columns}) "
            f"VALUES ({placeholders})"
        )
        self.db.execute(sql, tuple(row.values()))
        self.db.commit()

    def load_latest(
        self,
        where: str = "1=1",
        params: tuple = (),
        order_by: str = "rowid DESC",
        limit: int = 1,
    ) -> Optional[Any]:
        """加载最新一条记录。"""
        self.ensure_table()
        sql = (
            f"SELECT * FROM {self.TABLE_NAME} "
            f"WHERE {where} ORDER BY {order_by} LIMIT ?"
        )
        rows = self.db.fetch_all(sql, (*params, limit))
        if not rows:
            return None
        return dict(rows[0]) if limit == 1 else [dict(r) for r in rows]

    def load_history(
        self,
        where: str = "1=1",
        params: tuple = (),
        order_by: str = "rowid DESC",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """加载历史记录列表。"""
        self.ensure_table()
        sql = (
            f"SELECT * FROM {self.TABLE_NAME} "
            f"WHERE {where} ORDER BY {order_by} LIMIT ?"
        )
        rows = self.db.fetch_all(sql, (*params, limit))
        return [dict(r) for r in rows]

    def count(self, where: str = "1=1", params: tuple = ()) -> int:
        """统计行数。"""
        self.ensure_table()
        sql = f"SELECT COUNT(*) as cnt FROM {self.TABLE_NAME} WHERE {where}"
        row = self.db.fetch_one(sql, params)
        return row["cnt"] if row else 0
