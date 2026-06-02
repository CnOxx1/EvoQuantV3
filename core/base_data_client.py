"""BaseDataClient — HTTP 客户端基类：retry + circuit breaker + rate limit。

子类示例：
    class MyClient(BaseDataClient):
        BASE_URL = "https://api.example.com"

        def fetch_data(self, symbol: str):
            return self.get(f"/v1/data/{symbol}")
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import httpx
from loguru import logger


class CircuitBreaker:
    """简易熔断器：连续失败 N 次后拒绝请求一段时间。"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "closed"  # closed / open / half_open
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = "half_open"
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self.failure_threshold:
                self._state = "open"

    def allow_request(self) -> bool:
        return self.state != "open"


class RateLimiter:
    """令牌桶限流器。"""

    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate  # tokens per second
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self._last_refill
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            if time.time() >= deadline:
                return False
            time.sleep(0.05)


class BaseDataClient:
    """HTTP 客户端基类，封装 httpx + 熔断 + 限流 + 指数退避重试。

    子类设置类属性：
        BASE_URL: str — API 基础 URL
        TIMEOUT: float — 请求超时秒数（默认 20）
        MAX_RETRIES: int — 最大重试次数（默认 3）
        RATE_LIMIT: float — 每秒请求数（默认 10）
        RATE_BURST: int — 突发令牌数（默认 20）
        USER_AGENT: str — User-Agent 头
    """

    BASE_URL: str = ""
    TIMEOUT: float = 20.0
    MAX_RETRIES: int = 3
    RATE_LIMIT: float = 10.0
    RATE_BURST: int = 20
    USER_AGENT: str = "EvoQuant/1.0"

    def __init__(self, base_url: Optional[str] = None, **kwargs: Any):
        self._base_url = (base_url or self.BASE_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=kwargs.get("timeout", self.TIMEOUT),
            headers={"User-Agent": kwargs.get("user_agent", self.USER_AGENT)},
        )
        self._breaker = CircuitBreaker(
            failure_threshold=kwargs.get("breaker_threshold", 5),
            recovery_timeout=kwargs.get("breaker_recovery", 60.0),
        )
        self._limiter = RateLimiter(
            rate=kwargs.get("rate_limit", self.RATE_LIMIT),
            burst=kwargs.get("rate_burst", self.RATE_BURST),
        )
        self._max_retries = kwargs.get("max_retries", self.MAX_RETRIES)

    def get(self, path: str, params: Optional[dict] = None, **kwargs: Any) -> Any:
        return self._request("GET", path, params=params, **kwargs)

    def post(self, path: str, json: Optional[dict] = None, **kwargs: Any) -> Any:
        return self._request("POST", path, json=json, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._breaker.allow_request():
            raise ConnectionError(
                f"Circuit breaker OPEN for {self._base_url}, "
                f"recovery in {self._breaker.recovery_timeout}s"
            )

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            self._limiter.acquire()
            try:
                resp = self._client.request(method, path, **kwargs)
                resp.raise_for_status()
                self._breaker.record_success()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                self._breaker.record_failure()
                if attempt < self._max_retries:
                    backoff = min(2 ** (attempt - 1), 16)
                    logger.warning(
                        "[{}] {} {} attempt {}/{} failed: {} — retry in {}s",
                        self.__class__.__name__, method, path,
                        attempt, self._max_retries, exc, backoff,
                    )
                    time.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BaseDataClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
