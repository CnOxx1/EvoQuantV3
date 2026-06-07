from __future__ import annotations

import os
import random
import threading
import time
from dataclasses import dataclass, field

from loguru import logger

from core.exceptions import TransientDataError


@dataclass(frozen=True)
class ChaosConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("CHAOS_ENABLED", "").lower() == "true")
    latency_ms: int = field(default_factory=lambda: int(os.getenv("CHAOS_LATENCY_MS", "0")))
    error_rate: float = field(default_factory=lambda: float(os.getenv("CHAOS_ERROR_RATE", "0")))
    target_modules: list[str] = field(default_factory=lambda: [m for m in os.getenv("CHAOS_TARGET_MODULES", "").split(",") if m])


class ChaosMonkey:
    def __init__(self) -> None:
        self._config = ChaosConfig()
        self._lock = threading.Lock()
        logger.debug("ChaosMonkey initialized | enabled={}", self._config.enabled)

    def maybe_inject_latency(self) -> None:
        if not self._config.enabled or self._config.latency_ms <= 0:
            return
        with self._lock:
            delay = random.randint(0, self._config.latency_ms) / 1000.0
        logger.warning("ChaosMonkey injecting latency: {:.3f}s", delay)
        time.sleep(delay)

    def maybe_raise_error(self) -> None:
        if not self._config.enabled or self._config.error_rate <= 0:
            return
        with self._lock:
            roll = random.random()
        if roll < self._config.error_rate:
            logger.warning("ChaosMonkey injecting TransientDataError")
            raise TransientDataError("ChaosMonkey: synthetic transient failure")

    def should_target(self, module_name: str) -> bool:
        if not self._config.enabled:
            return False
        return not self._config.target_modules or module_name in self._config.target_modules

    def inject(self, module_name: str) -> None:
        if not self.should_target(module_name):
            return
        self.maybe_inject_latency()
        self.maybe_raise_error()


chaos_monkey = ChaosMonkey()
