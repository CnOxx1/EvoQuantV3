from __future__ import annotations

from enum import IntEnum
from threading import Lock
from time import time

from loguru import logger


class DegradationLevel(IntEnum):
    NORMAL = 0
    REDUCED = 1
    MINIMAL = 2
    EMERGENCY = 3


_FEATURES_BY_LEVEL: dict[DegradationLevel, set[str]] = {
    DegradationLevel.NORMAL: set(),  # all allowed
    DegradationLevel.REDUCED: {"sentiment", "prediction_market", "nft_market"},
    DegradationLevel.MINIMAL: {"sentiment", "prediction_market", "nft_market",
                                "portfolio_rebalance", "social_signals", "order_execution"},
    DegradationLevel.EMERGENCY: set(),  # block everything except reads
}

_MINIMAL_ALLOWED = {"exchange_data", "technical_indicators"}


class DegradationManager:
    def __init__(self) -> None:
        self._level = DegradationLevel.NORMAL
        self._lock = Lock()
        self._last_change = time()
        self._reason: str | None = None

    def current_level(self) -> DegradationLevel:
        with self._lock:
            return self._level

    def escalate(self, reason: str) -> DegradationLevel:
        with self._lock:
            if self._level < DegradationLevel.EMERGENCY:
                prev = self._level
                self._level = DegradationLevel(self._level + 1)
                self._reason = reason
                self._last_change = time()
                logger.warning(f"Degradation escalated {prev.name} -> {self._level.name}: {reason}")
            return self._level

    def deescalate(self) -> DegradationLevel:
        with self._lock:
            if self._level > DegradationLevel.NORMAL:
                prev = self._level
                self._level = DegradationLevel(self._level - 1)
                self._last_change = time()
                logger.info(f"Degradation de-escalated {prev.name} -> {self._level.name}")
            return self._level

    def should_run(self, module_name: str) -> bool:
        with self._lock:
            if self._level == DegradationLevel.NORMAL:
                return True
            if self._level == DegradationLevel.EMERGENCY:
                return False
            if self._level == DegradationLevel.MINIMAL:
                return module_name in _MINIMAL_ALLOWED
            # REDUCED
            return module_name not in _FEATURES_BY_LEVEL[DegradationLevel.REDUCED]


degradation_manager = DegradationManager()
