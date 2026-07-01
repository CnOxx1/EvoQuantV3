"""服务层查询缓存 — 缓存 DB 查询结果，多端点共享。

与 api/cache.py 的区别：
- api/cache.py 缓存最终 HTTP 响应（per-endpoint）
- 本模块缓存 DB 查询结果（per-query），多个端点查同一张表时共享

增强特性（v3.4.0）：
- invalidate_prefix：按前缀清空缓存（与 TTLCache 对称）
- invalidate_group：按依赖分组清空
- stale-while-revalidate：过期后返回陈旧数据 + 后台刷新
- per-key TTL：支持不同 key 使用不同过期时间

v4.1.0 增强：
- invalidate_downstream：基于依赖拓扑级联失效下游缓存
- 注册 upstream → downstream 依赖关系

使用方式：
    from api.query_cache import query_cache

    rows = query_cache.get_or_fetch(
        "latest_tickers:binance",
        lambda: exchange_db.fetch_all("SELECT * FROM latest_tickers WHERE exchange = 'binance'"),
        ttl=30.0,
        stale_ttl=60.0,
        group="exchange",
    )
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from loguru import logger

# 环境变量配置
_DEFAULT_TTL = float(os.environ.get("QUERY_CACHE_DEFAULT_TTL", "30.0"))
_DEFAULT_STALE_TTL = float(os.environ.get("QUERY_CACHE_STALE_TTL", "60.0"))
_SWR_ENABLED = os.environ.get("CACHE_STALE_WHILE_REVALIDATE", "1") == "1"


class QueryCache:
    """线程安全的服务层查询结果缓存。

    特点：
    - 按 key 缓存任意查询结果
    - 支持 per-key TTL 过期
    - 请求合并：同一 key 并发请求时只执行一次查询
    - 容量上限防止内存泄漏
    - 前缀失效：invalidate_prefix 按前缀批量清除
    - 依赖分组：invalidate_group 按逻辑分组清除
    - Stale-While-Revalidate：过期后仍返回陈旧数据 + 后台异步刷新
    - v4.1.0: 依赖拓扑级联失效（invalidate_downstream）
    """

    def __init__(self, max_size: int = 500, cleanup_interval: float = 60.0):
        # store: key -> (value, expire_at, stale_until)
        self._store: dict[str, tuple[Any, float, float]] = {}
        self._lock = threading.Lock()
        # v4.2.0: inflight 独立锁，减少缓存读取被 inflight 写入阻塞
        self._inflight_lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._inflight_results: dict[str, Any] = {}
        self._groups: dict[str, set[str]] = {}  # group -> {keys}
        # v4.1.0: 依赖拓扑 — upstream_prefix -> {downstream_prefixes}
        self._deps: dict[str, set[str]] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        self._dedup_hits = 0
        self._stale_hits = 0
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
        self,
        key: str,
        fetcher: Callable[[], Any],
        ttl: float | None = None,
        stale_ttl: float | None = None,
        group: str | None = None,
    ) -> Any:
        """获取缓存结果，未命中则执行 fetcher 并缓存。

        Parameters
        ----------
        key : str
            缓存键
        fetcher : callable
            数据获取函数
        ttl : float | None
            缓存有效期（秒），None 使用默认值
        stale_ttl : float | None
            过期后仍可返回陈旧数据的额外时间（stale-while-revalidate）
        group : str | None
            依赖分组名，用于 invalidate_group 批量失效
        """
        actual_ttl = ttl if ttl is not None else _DEFAULT_TTL
        actual_stale = stale_ttl if stale_ttl is not None else (
            _DEFAULT_STALE_TTL if _SWR_ENABLED else 0.0
        )

        # 快速路径：缓存命中
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                value, expire_at, stale_until = entry
                now = time.monotonic()
                if now < expire_at:
                    self._hits += 1
                    return value
                # stale-while-revalidate：过期但仍在 stale 窗口内
                if _SWR_ENABLED and now < stale_until:
                    self._stale_hits += 1
                    self._trigger_background_refresh(
                        key, fetcher, actual_ttl, actual_stale, group
                    )
                    return value
                del self._store[key]

        # 请求合并：检查是否有 inflight 请求（v4.2.0: 独立锁）
        with self._inflight_lock:
            event = self._inflight.get(key)
            if event is not None:
                self._dedup_hits += 1

        if event is not None:
            event.wait(timeout=30.0)
            with self._inflight_lock:
                result = self._inflight_results.pop(key, None)
            if result is not None:
                return result

        # 执行查询
        event = threading.Event()
        with self._inflight_lock:
            self._inflight[key] = event
            self._misses += 1

        try:
            result = fetcher()
            now = time.monotonic()
            expire_at = now + actual_ttl
            stale_until = expire_at + actual_stale
            with self._lock:
                if len(self._store) >= self._max_size:
                    self._evict_oldest()
                self._store[key] = (result, expire_at, stale_until)
                # 注册分组关系
                if group:
                    self._groups.setdefault(group, set()).add(key)
            with self._inflight_lock:
                self._inflight_results[key] = result
            return result
        finally:
            with self._inflight_lock:
                self._inflight.pop(key, None)
            event.set()

    def invalidate_prefix(self, prefix: str) -> int:
        """删除所有以 prefix 开头的 key，返回删除数量。"""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            # 同步清理分组引用
            for group_keys in self._groups.values():
                group_keys -= set(keys)
            return len(keys)

    def invalidate_group(self, group: str) -> int:
        """按依赖分组清空 — 更精准的缓存失效。"""
        with self._lock:
            keys = self._groups.pop(group, set())
            count = 0
            for k in keys:
                if k in self._store:
                    del self._store[k]
                    count += 1
            return count

    def invalidate_all(self) -> int:
        """清空全部缓存。"""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            self._groups.clear()
            return count

    def register_dependency(self, upstream_prefix: str, downstream_prefix: str) -> None:
        """注册依赖关系：upstream 失效时自动级联失效 downstream。

        v4.1.0: 支持缓存依赖拓扑，避免手动多次 invalidate_prefix。
        """
        with self._lock:
            self._deps.setdefault(upstream_prefix, set()).add(downstream_prefix)

    def invalidate_downstream(self, upstream_prefix: str) -> int:
        """级联失效：清空 upstream 自身 + 所有注册的 downstream 前缀。"""
        total = self.invalidate_prefix(upstream_prefix)
        with self._lock:
            downstream_set = self._deps.get(upstream_prefix, set()).copy()
        for ds_prefix in downstream_set:
            total += self.invalidate_prefix(ds_prefix)
        return total

    def _trigger_background_refresh(
        self,
        key: str,
        fetcher: Callable[[], Any],
        ttl: float,
        stale_ttl: float,
        group: str | None,
    ) -> None:
        """后台线程异步刷新过期缓存 — stale-while-revalidate 模式。"""
        # 避免重复刷新：如果已有 inflight 请求则跳过（v4.2.0: 独立锁）
        with self._inflight_lock:
            if key in self._inflight:
                return

        def _refresh():
            try:
                result = fetcher()
                now = time.monotonic()
                expire_at = now + ttl
                stale_until = expire_at + stale_ttl
                with self._lock:
                    self._store[key] = (result, expire_at, stale_until)
                    if group:
                        self._groups.setdefault(group, set()).add(key)
            except Exception as exc:
                logger.debug("后台缓存刷新失败 [{}]: {}", key, exc)

        t = threading.Thread(
            target=_refresh, daemon=True, name=f"swr-{key[:20]}"
        )
        t.start()

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
                # 清理超过 stale 窗口的条目（彻底过期）
                expired = [
                    k for k, (_, _, stale_until) in self._store.items()
                    if now >= stale_until
                ]
                for k in expired:
                    del self._store[k]

    @property
    def metrics(self) -> dict[str, Any]:
        total = self._hits + self._misses + self._stale_hits
        return {
            "hits": self._hits,
            "misses": self._misses,
            "dedup_hits": self._dedup_hits,
            "stale_hits": self._stale_hits,
            "total_requests": total,
            "hit_rate_pct": round(
                (self._hits + self._stale_hits) * 100 / total, 1
            ) if total else 0.0,
            "size": len(self._store),
            "max_size": self._max_size,
            "groups": len(self._groups),
        }


# 全局单例 — 由 app.py 的 lifespan 管理启停
query_cache = QueryCache(max_size=1000, cleanup_interval=30.0)
