from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from loguru import logger

SNAPSHOT_INTERVAL_HOURS = int(os.getenv("SNAPSHOT_INTERVAL_HOURS", "1"))
SNAPSHOT_MAX_AGE_HOURS = int(os.getenv("SNAPSHOT_MAX_AGE_HOURS", "24"))


@dataclass
class SnapshotVersion:
    version_id: str
    created_at: float
    tables_included: list[str]
    row_counts: dict[str, int] = field(default_factory=dict)


class SnapshotVersioningService:
    def __init__(self) -> None:
        self._snapshots: list[SnapshotVersion] = []

    def create_snapshot(self, db, tables: list[str]) -> SnapshotVersion:
        ts = int(time.time())
        version_id = f"v_{ts}"
        row_counts: dict[str, int] = {}
        for table in tables:
            dest = f"{table}_{version_id}"
            try:
                db.execute(f"CREATE TABLE {dest} AS SELECT * FROM {table}")
                count = db.execute(f"SELECT COUNT(*) FROM {dest}").fetchone()[0]
                row_counts[table] = count
            except Exception as e:
                logger.error(f"Snapshot copy failed for {table}: {e}")
                row_counts[table] = 0
        snap = SnapshotVersion(version_id=version_id, created_at=time.time(),
                               tables_included=tables, row_counts=row_counts)
        self._snapshots.append(snap)
        logger.info(f"Created snapshot {version_id} with {len(tables)} tables")
        return snap

    def list_snapshots(self) -> list[SnapshotVersion]:
        return list(self._snapshots)

    def get_snapshot_table(self, table_name: str, version_id: str) -> str:
        return f"{table_name}_{version_id}"

    def cleanup_old_snapshots(self, max_age_hours: int = SNAPSHOT_MAX_AGE_HOURS) -> None:
        cutoff = time.time() - (max_age_hours * 3600)
        kept = [s for s in self._snapshots if s.created_at >= cutoff]
        removed = len(self._snapshots) - len(kept)
        self._snapshots = kept
        if removed:
            logger.info(f"Cleaned up {removed} old snapshots")


snapshot_service = SnapshotVersioningService()
