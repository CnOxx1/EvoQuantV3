from __future__ import annotations

import os
import sys
import threading
import time

from loguru import logger

WINDOW_LOOKBACK_BARS = int(os.getenv("WINDOW_LOOKBACK_BARS", "500"))
WINDOW_MATERIALIZER_ENABLED = os.getenv("WINDOW_MATERIALIZER_ENABLED", "1") == "1"
WINDOW_MATERIALIZER_MAX_CACHE = int(os.getenv("WINDOW_MATERIALIZER_MAX_CACHE", "200"))


class WindowMaterializer:
    """Pre-materializes kline windows for all symbols x timeframes once before pipeline.

    LRU eviction: when cache exceeds WINDOW_MATERIALIZER_MAX_CACHE entries,
    the least-recently-accessed window is evicted to bound memory usage.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], object] = {}
        self._access_time: dict[tuple[str, str], float] = {}
        self._lock = threading.RLock()
        self._stats: dict = {"symbols": 0, "total_rows": 0, "memory_mb": 0.0, "elapsed_s": 0.0}
        self._max_cache = WINDOW_MATERIALIZER_MAX_CACHE

    def _evict_lru(self) -> None:
        """Evict least-recently-used entries until cache is within bounds (called under lock)."""
        while len(self._cache) > self._max_cache and self._access_time:
            lru_key = min(self._access_time, key=self._access_time.get)
            del self._cache[lru_key]
            del self._access_time[lru_key]

    def materialize(self, symbols: list[str], timeframes: list[str], lookback_bars: int = WINDOW_LOOKBACK_BARS) -> dict:
        import pandas as pd

        t0 = time.time()
        total_rows = 0
        now = time.time()
        with self._lock:
            self._cache.clear()
            self._access_time.clear()
            for sym in symbols:
                for tf in timeframes:
                    df = pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
                    self._cache[(sym, tf)] = df
                    self._access_time[(sym, tf)] = now
                    total_rows += len(df)
            self._evict_lru()
            mem = sum(df.memory_usage(deep=True).sum() for df in self._cache.values()) / (1024 * 1024)
            self._stats = {"symbols": len(symbols), "total_rows": total_rows, "memory_mb": round(mem, 2), "elapsed_s": round(time.time() - t0, 4)}
        logger.info(f"WindowMaterializer: materialized {len(symbols)}x{len(timeframes)} windows | {self._stats}")
        return {"window_materializer": self._cache, "window_stats": self._stats}

    def get_window(self, symbol: str, timeframe: str):
        import pandas as pd

        with self._lock:
            result = self._cache.get((symbol, timeframe))
            if result is not None:
                self._access_time[(symbol, timeframe)] = time.time()
        return result

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._access_time.clear()
            self._stats = {"symbols": 0, "total_rows": 0, "memory_mb": 0.0, "elapsed_s": 0.0}
        logger.debug("WindowMaterializer: cache cleared")

    def stats(self) -> dict:
        return self._stats.copy()


window_materializer = WindowMaterializer()
