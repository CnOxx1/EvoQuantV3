"""内存监控工具 — 跟踪 DataFrame 和大对象的内存使用。

在关键计算节点（如技术指标、相关性矩阵）前后调用，
防止内存峰值导致 OOM。

使用方式：
    from core.memory_monitor import memory_monitor

    memory_monitor.check("技术指标计算开始")
    result = heavy_computation()
    memory_monitor.check("技术指标计算结束")
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    import pandas as pd

# 环境变量配置
MEMORY_WARN_THRESHOLD_MB = int(os.environ.get("MEMORY_WARN_MB", "2048"))
MEMORY_CRITICAL_THRESHOLD_MB = int(os.environ.get("MEMORY_CRITICAL_MB", "4096"))
DF_MAX_ROWS = int(os.environ.get("DF_MAX_ROWS", "500000"))
INDICATOR_MAX_HISTORY = int(os.environ.get("INDICATOR_MAX_HISTORY", "2000"))


class MemoryMonitor:
    """进程级内存监控 — 在关键操作前后检查内存使用。

    优雅降级：psutil 未安装时跳过检查，不影响正常运行。
    优化 #13: syscall 结果缓存 1 秒，减少 memory_info() 调用开销。
    v4.1.0: double-check locking 防止并发竞争导致多次 syscall。
    """

    def __init__(self):
        self._process = None
        self._available = False
        self._cached_rss: float = 0.0
        self._cache_time: float = 0.0
        # v4.4.0: 缓存 TTL 可配置，默认 5s 减少 80% syscall
        self._cache_ttl: float = float(os.environ.get("MEMORY_CACHE_TTL_SECONDS", "5.0"))
        self._cache_lock = None  # 延迟初始化避免 import 开销
        try:
            import psutil
            self._process = psutil.Process()
            self._available = True
        except ImportError:
            logger.debug("psutil 未安装，内存监控已禁用")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def rss_mb(self) -> float:
        """当前 RSS 内存使用（MB）— 带 1s 缓存 + double-check locking。"""
        if not self._available:
            return 0.0
        import time
        now = time.monotonic()
        if now - self._cache_time <= self._cache_ttl:
            return self._cached_rss
        # 需要刷新 — double-check locking 防止并发 syscall
        if self._cache_lock is None:
            import threading
            self._cache_lock = threading.Lock()
        with self._cache_lock:
            # 再次检查（另一个线程可能已经刷新）
            if now - self._cache_time > self._cache_ttl:
                self._cached_rss = self._process.memory_info().rss / 1048576
                self._cache_time = time.monotonic()
        return self._cached_rss

    def check(self, context: str = "") -> bool:
        """检查内存状态，超阈值时记录警告。返回 True 表示安全。"""
        if not self._available:
            return True
        current_mb = self.rss_mb
        if current_mb > MEMORY_CRITICAL_THRESHOLD_MB:
            logger.error(
                "内存使用超临界值 ({:.0f}MB > {}MB) [{}]",
                current_mb, MEMORY_CRITICAL_THRESHOLD_MB, context,
            )
            return False
        if current_mb > MEMORY_WARN_THRESHOLD_MB:
            logger.warning(
                "内存使用偏高 ({:.0f}MB > {}MB) [{}]",
                current_mb, MEMORY_WARN_THRESHOLD_MB, context,
            )
        return True

    @staticmethod
    def df_size_mb(df: "pd.DataFrame") -> float:
        """估算 DataFrame 内存占用（MB）。"""
        return df.memory_usage(deep=True).sum() / 1024 / 1024

    def check_df(self, df: "pd.DataFrame", context: str = "") -> bool:
        """检查 DataFrame 大小是否超过行数限制。"""
        row_count = len(df)
        if row_count > DF_MAX_ROWS:
            size_mb = self.df_size_mb(df)
            logger.warning(
                "DataFrame 行数超限 ({} > {}, {:.1f}MB) [{}]",
                row_count, DF_MAX_ROWS, size_mb, context,
            )
            return False
        return True


# 全局单例
memory_monitor = MemoryMonitor()
