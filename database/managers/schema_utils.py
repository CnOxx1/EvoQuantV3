"""SchemaUtilsMixin — 表结构检测与补列工具方法。"""

from __future__ import annotations

import sqlite3

from loguru import logger


class SchemaUtilsMixin:
    """Schema 管理工具 Mixin — 字段检测、补列、列定义。"""

    def _existing_columns(self, table_name: str) -> set[str]:
        rows = self.fetch_all(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in rows}

    @staticmethod
    def _is_duplicate_column_error(error: sqlite3.OperationalError) -> bool:
        return "duplicate column name" in str(error).lower()

    def _ensure_columns(self, table_name: str, columns: dict[str, str]):
        existing_columns = self._existing_columns(table_name)
        for column_name, column_sql in columns.items():
            if column_name in existing_columns:
                continue
            try:
                self.conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
                )
            except sqlite3.OperationalError as exc:
                if not self._is_duplicate_column_error(exc):
                    raise
                existing_columns = self._existing_columns(table_name)
                if column_name not in existing_columns:
                    raise
                logger.info(
                    f"数据表 {table_name} 字段已被并发创建，跳过重复补列: {column_name}"
                )
                continue
            existing_columns.add(column_name)
            logger.info(f"已为数据表 {table_name} 添加字段: {column_name}")
