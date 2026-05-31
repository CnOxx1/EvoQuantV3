"""服务层查询缓存 — 缓存 DB 查询结果，多端点共享。

与 api/cache.py 的区别：
- api/cache.py 缓存最终 HTTP 响应（per-endpoint）
- 本模块缓存 DB 查询结果（per-query），多个端点查同一张表时共享

使用方式：
    from api.query_cache import query_cache

    # 在 router 中
    rows = query_cache.get_or_fetch(
        "latest_tickers:binance",
        lambda: exchange_db.fetch_all("SELECT * FROM latest_tickers WHERE exchange = 'binance'"),
        ttl=30.0,
    )
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class QueryCache:
    """线程安全的服务层查询结果缓存。

    特点：
    - 按 key 缓存任意查询结果
    - 支持 TTL 过期
    - 请求合并：同一 key 并发请求时只执行一次查询
    - 容量上限防止内存泄漏
    """

    def __init__(self, max_size: int = 500, cleanup_interval: float = 60.0):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_results: dict[str, Any] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._dedup_hits = 0
        self._cleanup_interval = cleanup_interval
        self._stopped = threading.Event()
        self._cleanup_thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台清理线程。"""
        if self._cleanup_thread is not None:
            return
        self._stopped.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="query-cache-cleanup"
        )
        self._cleanup_thread.start()

    def stop(self) -> None:
        """停止后台清理线程。"""
        self._stopped.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=5.0)
            self._cleanup_thread = None

    def get_or_fetch(
        self, key: str, fetcher: Callable[[], Any], ttl: float = 30.0
    ) -> Any:
        """获取缓存结果，未命中则执行 fetcher 并缓存。

        支持请求合并：同一 key 并发调用时只执行一次 fetcher。
        """
        # 快速路径：缓存命中
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                value, expire_at = entry
                if time.monotonic() < expire_at:
                    self._hits += 1
                    return value
                del self._store[key]

        # 请求合并：检查是否有 inflight 请求
        with self._lock:
            event = self._inflight.get(key)
            if event is not None:
                self._dedup_hits += 1

        if event is not None:
            event.wait(timeout=30.0)
            with self._lock:
                result = self._inflight_results.pop(key, None)
            if result is not None:
                return result

        # 执行查询
        event = threading.Event()
        with self._lock:
            self._inflight[key] = event
            self._misses += 1

        try:
            result = fetcher()
            # 存入缓存
            with self._lock:
                if len(self._store) >= self._max_size:
                    self._evict_oldest()
                self._store[key] = (result, time.monotonic() + ttl)
                self._inflight_results[key] = result
            return result
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            event.set()

    def invalidate_all(self) -> int:
        """清空全部缓存。"""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def _evict_oldest(self) -> None:
        """淘汰最早过期的条目（在 _lock 内调用）。"""
        if not self._store:
            return
        oldest_key = min(self._store, key=lambda k: self._store[k][1])
        del self._store[oldest_key]

    def _cleanup_loop(self) -> None:
        while not self._stopped.wait(self._cleanup_interval):
            now = time.monotonic()
            with self._lock:
                expired = [k for k, (_, exp) in self._store.items() if now >= exp]
                for k in expired:
                    del self._store[k]

    @property
    def metrics(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "dedup_hits": self._dedup_hits,
            "total_requests": total,
            "hit_rate_pct": round(self._hits * 100 / total, 1) if total else 0.0,
            "size": len(self._store),
            "max_size": self._max_size,
        }


# 全局单例 — 由 app.py 的 lifespan 管理启停
query_cache = QueryCache(max_size=500, cleanup_interval=30.0)