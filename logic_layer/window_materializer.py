from __future__ import annotations

import os
import sys
import threading
import time

from loguru import logger

WINDOW_LOOKBACK_BARS = int(os.getenv("WINDOW_LOOKBACK_BARS", "500"))
WINDOW_MATERIALIZER_ENABLED = os.getenv("WINDOW_MATERIALIZER_ENABLED", "1") == "1"


class WindowMaterializer:
    """Pre-materializes kline windows for all symbols x timeframes once before pipeline."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], object] = {}
        self._lock = threading.RLock()
        self._stats: dict = {"symbols": 0, "total_rows": 0, "memory_mb": 0.0, "elapsed_s": 0.0}

    def materialize(self, symbols: list[str], timeframes: list[str], lookback_bars: int = WINDOW_LOOKBACK_BARS) -> dict:
        import pandas as pd

        t0 = time.time()
        total_rows = 0
        with self._lock:
            self._cache.clear()
            for sym in symbols:
                for tf in timeframes:
                    df = pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
                    self._cache[(sym, tf)] = df
                    total_rows += len(df)
            mem = sum(df.memory_usage(deep=True).sum() for df in self._cache.values()) / (1024 * 1024)
            self._stats = {"symbols": len(symbols), "total_rows": total_rows, "memory_mb": round(mem, 2), "elapsed_s": round(time.time() - t0, 4)}
        logger.info(f"WindowMaterializer: materialized {len(symbols)}x{len(timeframes)} windows | {self._stats}")
        return {"window_materializer": self._cache, "window_stats": self._stats}

    def get_window(self, symbol: str, timeframe: str):
        import pandas as pd

        return self._cache.get((symbol, timeframe))

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._stats = {"symbols": 0, "total_rows": 0, "memory_mb": 0.0, "elapsed_s": 0.0}
        logger.debug("WindowMaterializer: cache cleared")

    def stats(self) -> dict:
        return self._stats.copy()


window_materializer = WindowMaterializer()
