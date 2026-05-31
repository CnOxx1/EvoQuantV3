"""轻量级熔断器 — 无外部依赖，保护交易所 API 调用。

状态机：CLOSED → OPEN → HALF_OPEN → CLOSED
- CLOSED: 正常通行，记录失败次数
- OPEN: 快速失败，不发起请求
- HALF_OPEN: 允许一次探测请求，成功则关闭，失败则重新打开
"""

from __future__ import annotations

import os
import threading
import time
from enum import Enum

from loguru import logger


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# 默认配置（可通过环境变量覆盖）
_DEFAULT_FAILURE_THRESHOLD = int(os.environ.get("CB_FAILURE_THRESHOLD", "5"))
_DEFAULT_RECOVERY_TIMEOUT = float(os.environ.get("CB_RECOVERY_TIMEOUT", "60.0"))
_DEFAULT_HALF_OPEN_MAX_CALLS = int(os.environ.get("CB_HALF_OPEN_MAX_CALLS", "1"))


class CircuitBreaker:
    """单个服务/端点的熔断器实例。"""

    def __init__(
        self,
        name: str,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = _DEFAULT_RECOVERY_TIMEOUT,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
            return self._state

    def allow_request(self) -> bool:
        """判断当前是否允许发起请求。"""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < _DEFAULT_HALF_OPEN_MAX_CALLS:
                    self._half_open_calls += 1
                    return True
            return False
        return False  # OPEN

    def record_success(self) -> None:
        """记录一次成功调用。"""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                logger.info("熔断器 [{}] 恢复: HALF_OPEN → CLOSED", self.name)

    def record_failure(self) -> None:
        """记录一次失败调用。"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "熔断器 [{}] 探测失败: HALF_OPEN → OPEN (冷却 {:.0f}s)",
                    self.name, self.recovery_timeout,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "熔断器 [{}] 触发: CLOSED → OPEN (连续失败 {} 次, 冷却 {:.0f}s)",
                    self.name, self._failure_count, self.recovery_timeout,
                )

    @property
    def metrics(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
        }


class CircuitBreakerRegistry:
    """全局熔断器注册表 — 按名称管理多个熔断器实例。"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> CircuitBreaker:
        """获取或创建指定名称的熔断器。"""
        if name not in self._breakers:
            with self._lock:
                if name not in self._breakers:
                    self._breakers[name] = CircuitBreaker(name)
        return self._breakers[name]

    @property
    def all_metrics(self) -> list[dict[str, object]]:
        return [cb.metrics for cb in self._breakers.values()]


# 全局单例
circuit_registry = CircuitBreakerRegistry()


class CircuitOpenError(Exception):
    """熔断器处于 OPEN 状态时抛出，调用方应快速失败。"""

    def __init__(self, breaker_name: str):
        self.breaker_name = breaker_name
        super().__init__(f"Circuit breaker [{breaker_name}] is OPEN")
