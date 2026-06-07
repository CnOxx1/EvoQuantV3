from __future__ import annotations

import os
import time
import threading

from loguru import logger

from core.data_retention import retention_service


class RetentionExecutor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_run: float | None = None
        self._batch_size = int(os.getenv("RETENTION_BATCH_SIZE", "1000"))
        self._dry_run_mode = os.getenv("RETENTION_DRY_RUN", "0") == "1"

    def dry_run(self, db, table_name: str) -> int:
        policy = retention_service.get_policy(table_name)
        sql = (
            f"SELECT COUNT(*) FROM {policy.table_name} "
            f"WHERE timestamp < NOW() - INTERVAL '{policy.archive_after_days} days'"
        )
        result = db.execute(sql)
        count = result.fetchone()[0]
        logger.info(f"[dry_run] {table_name}: {count} rows would be deleted")
        return count

    def run_cleanup(self, db, table_name: str) -> int:
        with self._lock:
            if self._dry_run_mode:
                return self.dry_run(db, table_name)
            policy = retention_service.get_policy(table_name)
            sql = (
                f"DELETE FROM {policy.table_name} "
                f"WHERE ctid IN (SELECT ctid FROM {policy.table_name} "
                f"WHERE timestamp < NOW() - INTERVAL '{policy.archive_after_days} days' "
                f"LIMIT {self._batch_size})"
            )
            total = 0
            while True:
                result = db.execute(sql)
                deleted = result.rowcount
                total += deleted
                if deleted < self._batch_size:
                    break
            self._last_run = time.time()
            logger.info(f"[cleanup] {table_name}: deleted {total} rows")
            return total

    def run_all_cleanups(self, db) -> dict[str, int]:
        results: dict[str, int] = {}
        for table_name in retention_service._policies:
            results[table_name] = self.run_cleanup(db, table_name)
        return results

    def last_run_at(self) -> float | None:
        return self._last_run


retention_executor = RetentionExecutor()
