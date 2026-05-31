"""轻量级 TTL 内存缓存 — 无外部依赖，基于 time.monotonic() + dict。

用于 API 层对高频只读端点做短期响应缓存，逻辑管道刷新后全量失效。
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TTLCache:
    """线程安全的 TTL 内存缓存。

    存储结构: {key: (value, expire_monotonic)}
    清理策略: 惰性清理（get 时检查） + 定期清理（后台线程）
    """

    def __init__(self, cleanup_interval: float = 60.0):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread: threading.Thread | None = None
        self._stopped = threading.Event()
        # 命中/未命中计数器
        self._hits: int = 0
        self._misses: int = 0

    def start(self) -> None:
        """启动后台清理线程。"""
        if self._cleanup_thread is not None:
            return
        self._stopped.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True, name="ttl-cache-cleanup"
        )
        self._cleanup_thread.start()

    def stop(self) -> None:
        """停止后台清理线程。"""
        self._stopped.set()
        if self._cleanup_thread is not None:
            self._cleanup_thread.join(timeout=5.0)
            self._cleanup_thread = None

    def get(self, key: str) -> Any | None:
        """获取缓存值，过期返回 None（惰性清理）。"""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expire_at = entry
            if time.monotonic() >= expire_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        """写入缓存，ttl 单位为秒。"""
        expire_at = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (value, expire_at)

    def invalidate(self, key: str) -> None:
        """删除指定 key。"""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """删除所有以 prefix 开头的 key，返回删除数量。"""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            return len(keys)

    def invalidate_all(self) -> int:
        """清空全部缓存，返回删除数量。"""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    @property
    def size(self) -> int:
        """当前缓存条目数（含可能已过期但未清理的）。"""
        return len(self._store)

    @property
    def metrics(self) -> dict[str, int]:
        """返回缓存命中/未命中统计。"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate_pct": round(self._hits * 100 / total, 1) if total else 0.0,
            "size": len(self._store),
        }

    def _cleanup_loop(self) -> None:
        """后台定期清理过期条目。"""
        while not self._stopped.wait(self._cleanup_interval):
            self._evict_expired()

    def _evict_expired(self) -> int:
        """清理所有过期条目，返回清理数量。"""
        now = time.monotonic()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
            return len(expired)


# 全局单例 — 由 app.py 的 lifespan 管理启停
cache = TTLCache(cleanup_interval=30.0)
