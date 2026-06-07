from __future__ import annotations

import os
import threading

from loguru import logger

_DEFAULT_LAZY = "search_trend_data,nft_market_data,prediction_market_data,governance_data"


class LazyModuleStarter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        env = os.getenv("LAZY_MODULES", _DEFAULT_LAZY)
        self._lazy: set[str] = {m.strip() for m in env.split(",") if m.strip()}
        self._pending: list[str] = []
        self._started: set[str] = set()
        logger.debug(f"LazyModuleStarter initialized, lazy modules: {self._lazy}")

    def mark_lazy(self, module_name: str) -> None:
        with self._lock:
            self._lazy.add(module_name)

    def is_lazy(self, module_name: str) -> bool:
        with self._lock:
            return module_name in self._lazy

    def request_start(self, module_name: str) -> None:
        with self._lock:
            if module_name not in self._started and module_name not in self._pending:
                self._pending.append(module_name)
                logger.info(f"Lazy start requested for: {module_name}")

    def get_pending_starts(self) -> list[str]:
        with self._lock:
            return list(self._pending)

    def mark_started(self, module_name: str) -> None:
        with self._lock:
            if module_name in self._pending:
                self._pending.remove(module_name)
            self._started.add(module_name)
            logger.info(f"Module marked as started: {module_name}")


lazy_starter = LazyModuleStarter()
