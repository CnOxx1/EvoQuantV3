from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field


@dataclass
class LineageRecord:
    source_module: str
    target_table: str
    operation: str  # insert/update/transform
    row_count: int
    timestamp: float
    parent_records: list[str] = field(default_factory=list)
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class DataLineageTracker:
    def __init__(self) -> None:
        cap = int(os.environ.get("LINEAGE_BUFFER_SIZE", "1000"))
        self._buffer: deque[LineageRecord] = deque(maxlen=cap)
        self._lock = threading.Lock()

    def record(
        self,
        source: str,
        target: str,
        operation: str,
        row_count: int,
        parents: list[str] | None = None,
    ) -> str:
        rec = LineageRecord(
            source_module=source,
            target_table=target,
            operation=operation,
            row_count=row_count,
            timestamp=time.time(),
            parent_records=parents or [],
        )
        with self._lock:
            self._buffer.append(rec)
        return rec.record_id

    def trace(self, table_name: str) -> list[LineageRecord]:
        with self._lock:
            return [r for r in self._buffer if r.target_table == table_name]


lineage_tracker = DataLineageTracker()
