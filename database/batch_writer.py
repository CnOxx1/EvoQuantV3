"""批量写入器 — 确保所有数据库写入走批量路径并自动分块。"""

from __future__ import annotations

import os
from typing import Any, Sequence

from loguru import logger


BATCH_WRITER_CHUNK_SIZE = int(os.environ.get("BATCH_WRITER_CHUNK_SIZE", "500"))


class BatchWriter:
    """保护性批量写入包装，自动将大批量 INSERT 分块执行。

    使用方式:
        writer = BatchWriter(db)
        writer.upsert_many(sql, params_list)
    """

    def __init__(self, db, chunk_size: int | None = None):
        self._db = db
        self._chunk_size = chunk_size or BATCH_WRITER_CHUNK_SIZE

    def upsert_many(
        self, sql: str, params_list: Sequence[tuple[Any, ...]]
    ) -> int:
        """分块执行批量 upsert，返回总处理行数。"""
        if not params_list:
            return 0

        total = len(params_list)
        processed = 0

        for i in range(0, total, self._chunk_size):
            chunk = params_list[i : i + self._chunk_size]
            self._db.execute_many(sql, chunk)
            processed += len(chunk)

        if total > self._chunk_size:
            logger.debug(
                "BatchWriter: {} 行分 {} 批写入完成",
                total,
                (total + self._chunk_size - 1) // self._chunk_size,
            )

        return processed

    def insert_many(
        self, sql: str, params_list: Sequence[tuple[Any, ...]]
    ) -> int:
        """insert_many 的别名，与 upsert_many 行为一致。"""
        return self.upsert_many(sql, params_list)
