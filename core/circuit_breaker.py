from __future__ import annotations

import enum
import functools
import os
import threading
import time
from typing import Any, Callable, Optional

from loguru import logger


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
        recovery_timeout: float = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "30")),
        half_open_max_calls: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
            return self._state

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("Circuit breaker recovered, now CLOSED")
            self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker test failed, back to OPEN")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker OPEN after {self._failure_count} failures"
                )

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.OPEN:
            return False
        with self._lock:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
        return False


def circuit_protected(
    fallback: Optional[Callable[..., Any]] = None,
    breaker: Optional[CircuitBreaker] = None,
):
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = breaker or db_circuit_breaker
            if not cb.allow_request():
                if fallback:
                    return fallback(*args, **kwargs)
                raise RuntimeError(
                    f"Circuit breaker OPEN: {func.__name__} rejected"
                )
            try:
                result = func(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as exc:
                cb.record_failure()
                raise
        return wrapper
    return decorator


db_circuit_breaker = CircuitBreaker()
