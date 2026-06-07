from __future__ import annotations

import os
import threading
import time


class AdaptivePoolManager:
    """Adaptive connection pool sizing based on load metrics."""

    def __init__(self, min_size: int = 5, max_size: int = 20):
        self._lock = threading.Lock()
        self._min = max(2, min_size)
        self._max = min(100, max_size)
        self._alpha = 0.1
        self._ema_wait = 0.0
        self._ema_idle = 0.0
        self._total_acquires = 0
        self._total_releases = 0
        self._queue_depth = 0

    def record_acquire(self, wait_ms: float) -> None:
        with self._lock:
            self._ema_wait = self._alpha * wait_ms + (1 - self._alpha) * self._ema_wait
            self._total_acquires += 1
            self._queue_depth += 1

    def record_release(self, idle_ms: float) -> None:
        with self._lock:
            self._ema_idle = self._alpha * idle_ms + (1 - self._alpha) * self._ema_idle
            self._total_releases += 1
            self._queue_depth = max(0, self._queue_depth - 1)

    def recommend_size(self) -> tuple[int, int]:
        with self._lock:
            new_min, new_max = self._min, self._max
            idle_ratio = self._ema_idle / (self._ema_idle + self._ema_wait + 1e-9)
            if self._ema_wait > 100.0:
                new_max = min(100, int(self._max * 1.1))
            if idle_ratio > 0.7:
                new_min = max(2, int(self._min * 0.9))
            self._min, self._max = new_min, new_max
            return (new_min, new_max)

    @property
    def metrics(self) -> dict:
        with self._lock:
            idle_ratio = self._ema_idle / (self._ema_idle + self._ema_wait + 1e-9)
            return {
                "avg_wait_ms": round(self._ema_wait, 2),
                "avg_idle_ms": round(self._ema_idle, 2),
                "idle_ratio": round(idle_ratio, 4),
                "queue_depth": self._queue_depth,
                "total_acquires": self._total_acquires,
                "total_releases": self._total_releases,
                "current_min": self._min,
                "current_max": self._max,
            }


adaptive_pool = AdaptivePoolManager()
