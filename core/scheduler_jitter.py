from __future__ import annotations

import os
import random
import threading
import time
from collections import deque
from typing import Callable

SCHEDULER_JITTER_PCT = float(os.getenv("SCHEDULER_JITTER_PCT", "0.15"))
BACKPRESSURE_MAX_CONCURRENT = int(os.getenv("BACKPRESSURE_MAX_CONCURRENT", "6"))

_PRIORITY_ORDER = {"hot": 0, "normal": 1, "cold": 2}


def jitter(interval_seconds: int, pct: float = SCHEDULER_JITTER_PCT) -> float:
    delta = interval_seconds * pct
    return interval_seconds + random.uniform(-delta, delta)


class BackpressureQueue:
    def __init__(self, max_concurrent: int = BACKPRESSURE_MAX_CONCURRENT):
        self._max_concurrent = max_concurrent
        self._queue: deque[tuple[int, Callable]] = deque()
        self._lock = threading.Lock()
        self._executed = 0
        self._total_submitted = 0

    def submit(self, task_fn: Callable, priority: str = "normal") -> None:
        with self._lock:
            self._queue.append((_PRIORITY_ORDER.get(priority, 1), task_fn))
            self._total_submitted += 1

    def drain(self, max_concurrent: int | None = None) -> int:
        limit = max_concurrent or self._max_concurrent
        with self._lock:
            sorted_tasks = sorted(self._queue, key=lambda t: t[0])
            self._queue.clear()
        batch = sorted_tasks[:limit]
        remainder = sorted_tasks[limit:]
        for _, fn in batch:
            fn()
        with self._lock:
            self._executed += len(batch)
            self._queue.extendleft(reversed(remainder))
        return len(batch)

    def pending(self) -> int:
        with self._lock:
            return len(self._queue)

    def stats(self) -> dict:
        with self._lock:
            return {
                "executed": self._executed,
                "pending": len(self._queue),
                "total_submitted": self._total_submitted,
            }


backpressure_queue = BackpressureQueue()
