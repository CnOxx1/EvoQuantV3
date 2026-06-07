"""查询预取器 — 管道完成后主动预热高频查询缓存。

v4.1.0 优化: prefetch_all() 现在真正执行 DB 查询并写入 query_cache，
而非只是 touch 空缓存键（原实现无法预热已过期的条目）。
"""

from __future__ import annotations

import os
import threading
from collections import Counter

from loguru import logger

from core.event_bus import TOPIC_PIPELINE_COMPLETE, event_bus

PREFETCH_ENABLED = os.getenv("PREFETCH_ENABLED", "1") == "1"
PREFETCH_TOP_N = int(os.getenv("PREFETCH_TOP_N", "20"))


class QueryPrefetcher:
    """Listens to pipeline events and pre-warms cache for hot queries."""

    def __init__(self) -> None:
        self._counter: Counter[str] = Counter()
        self._lock = threading.Lock()
        self._running = False

    def record_access(self, cache_key: str) -> None:
        with self._lock:
            self._counter[cache_key] += 1

    def get_hot_keys(self, top_n: int = PREFETCH_TOP_N) -> list[str]:
        with self._lock:
            return [k for k, _ in self._counter.most_common(top_n)]

    def prefetch_all(self) -> None:
        """真正预热高频缓存键 — 执行 DB 查询并写入 query_cache。"""
        if not PREFETCH_ENABLED:
            return
        keys = self.get_hot_keys()
        if not keys:
            return
        logger.debug(f"Prefetching {len(keys)} hot keys")

        from api.query_cache import query_cache

        warmed = 0
        for key in keys:
            try:
                fetcher = self._build_fetcher(key)
                if fetcher is not None:
                    query_cache.get_or_fetch(key, fetcher, ttl=30.0)
                    warmed += 1
            except Exception:
                pass  # 预热失败静默跳过

        if warmed:
            logger.debug(f"Prefetch warmed {warmed}/{len(keys)} keys")

    @staticmethod
    def _build_fetcher(key: str):
        """根据缓存键构建对应的 DB 查询 fetcher。"""
        from api.dependencies import get_exchange_db

        if key.startswith("latest_tickers:"):
            exchange = key.split(":", 1)[1] if ":" in key else "binance"
            def _fetch():
                db = get_exchange_db()
                return db.fetch_all(
                    "SELECT symbol, last_price, change_24h, quote_volume_24h "
                    "FROM latest_tickers WHERE exchange = ?", (exchange,)
                )
            return _fetch

        if key.startswith("latest_funding:"):
            exchange = key.split(":", 1)[1] if ":" in key else "binance"
            def _fetch():
                db = get_exchange_db()
                return db.fetch_all(
                    "SELECT symbol, funding_rate FROM latest_funding_rates "
                    "WHERE exchange = ?", (exchange,)
                )
            return _fetch

        # 未知 key 模式 — 无法构建 fetcher
        return None

    def _on_pipeline_complete(self, _event) -> None:  # noqa: ANN001
        thread = threading.Thread(
            target=self.prefetch_all, daemon=True, name="prefetch-worker"
        )
        thread.start()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        event_bus.subscribe(TOPIC_PIPELINE_COMPLETE, self._on_pipeline_complete)
        logger.info("QueryPrefetcher started")

    def stop(self) -> None:
        self._running = False
        logger.info("QueryPrefetcher stopped")


query_prefetcher = QueryPrefetcher()

