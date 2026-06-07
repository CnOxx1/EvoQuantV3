"""请求合并器 — 合并同一 key 的并发查询，避免重复执行。

v4.1.0 优化: 移除首次请求的无条件 sleep，改为事件驱动合并。
只有后续请求到达时才被合并到已有 inflight 请求，首次请求立即执行。
"""

from __future__ import annotations

import threading
from typing import Any, Callable


class RequestCoalescer:
    """Deduplicates identical concurrent queries — zero artificial latency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, Any, BaseException | None]] = {}

    def get_or_fetch(self, key: str, fetcher: Callable[[], Any], window_ms: float = 100) -> Any:
        """获取结果，如果已有 inflight 请求则等待复用，否则立即执行。

        v4.1.0: 移除 time.sleep(window_ms)，首次请求零延迟直接执行。
        后续并发请求通过 event.wait() 自动合并到首次结果。
        """
        with self._lock:
            if key in self._pending:
                event, _, _ = self._pending[key]
                wait = True
            else:
                event = threading.Event()
                self._pending[key] = (event, None, None)
                wait = False

        if wait:
            event.wait()
            with self._lock:
                _, result, exc = self._pending.get(key, (None, None, None))
            if exc:
                raise exc
            return result

        # 首次请求：立即执行，不再 sleep
        try:
            result = fetcher()
            with self._lock:
                self._pending[key] = (event, result, None)
        except BaseException as exc:
            with self._lock:
                self._pending[key] = (event, None, exc)
            event.set()
            raise
        finally:
            event.set()

        with self._lock:
            del self._pending[key]
        return result

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


request_coalescer = RequestCoalescer()
