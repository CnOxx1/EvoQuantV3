from __future__ import annotations

import os
import signal
import threading
import time
from typing import Callable

from loguru import logger

SHUTDOWN_TIMEOUT_SECONDS = float(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30"))


class ShutdownManager:
    def __init__(self) -> None:
        self._callbacks: list[tuple[int, str, Callable]] = []
        self._lock = threading.Lock()
        self._shutting_down = False
        signal.signal(signal.SIGTERM, lambda *_: self.shutdown())
        signal.signal(signal.SIGINT, lambda *_: self.shutdown())

    def register(self, name: str, cleanup_fn: Callable, priority: int = 50) -> None:
        with self._lock:
            self._callbacks.append((priority, name, cleanup_fn))

    def is_shutting_down(self) -> bool:
        return self._shutting_down

    def shutdown(self, timeout_seconds: float = SHUTDOWN_TIMEOUT_SECONDS) -> None:
        with self._lock:
            if self._shutting_down:
                return
            self._shutting_down = True
            callbacks = sorted(self._callbacks, key=lambda x: x[0])

        logger.info("Graceful shutdown started, timeout={}s", timeout_seconds)
        deadline = time.monotonic() + timeout_seconds
        for priority, name, fn in callbacks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Shutdown timeout reached, skipping remaining callbacks")
                break
            logger.info("Running cleanup [{}] (priority={})", name, priority)
            try:
                fn()
            except Exception as exc:
                logger.error("Cleanup [{}] failed: {}", name, exc)
        logger.info("Graceful shutdown complete")


shutdown_manager = ShutdownManager()
