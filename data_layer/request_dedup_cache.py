"""请求级去重缓存 — 防止同一采集周期内重复请求相同外部数据。"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable


class RequestDedupCache:
    """短 TTL 去重缓存，同一分钟内对相同 key 的重复请求直接返回缓存值。

    典型用法:
        cache = RequestDedupCache(default_ttl=60)
        result = cache.get_or_fetch(
            key=f"binance:BTC/USDT:ticker",
            fetcher=lambda: client.fetch_ticker("BTC/USDT"),
        )
    """

    def __init__(self, default_ttl: int = 60):
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get_or_fetch(
        self, key: str, fetcher: Callable[[], Any], ttl: int | None = None
    ) -> Any:
        """获取缓存值，未命中时调用 fetcher 并缓存结果。"""
        now = time.time()
        with self._lock:
            cached = self._store.get(key)
            if cached is not None and now < cached[1]:
                self._hits += 1
                return cached[0]

        # 缓存未命中，执行 fetcher（不持锁）
        result = fetcher()
        expire_at = now + (ttl if ttl is not None else self._default_ttl)

        with self._lock:
            self._store[key] = (result, expire_at)
            self._misses += 1

        return result

    def clear_expired(self) -> int:
        """清理过期条目，返回清理数量。"""
        now = time.time()
        with self._lock:
            expired_keys = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    def invalidate(self, key: str) -> bool:
        """手动失效指定 key。"""
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear_all(self) -> int:
        """清空全部缓存。"""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}


# 全局单例
request_cache = RequestDedupCache(default_ttl=60)
