"""快照缓冲器 — 维护采集模块最近 N 次结果，用于崩溃恢复时填充数据空洞。"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Any


SNAPSHOT_BUFFER_ENABLED = os.environ.get("SNAPSHOT_BUFFER_ENABLED", "true").lower() in (
    "1", "true", "yes"
)
SNAPSHOT_BUFFER_SIZE = int(os.environ.get("SNAPSHOT_BUFFER_SIZE", "3"))


class SnapshotBuffer:
    """每个采集模块维护最近 N 次快照，崩溃恢复时可注入最近已知数据。

    用法:
        buffer = SnapshotBuffer()
        buffer.record("exchange_data", {"tickers": [...], "timestamp": ...})
        latest = buffer.get_latest("exchange_data")
    """

    def __init__(self, max_snapshots: int | None = None):
        self._max = max_snapshots or SNAPSHOT_BUFFER_SIZE
        self._buffer: dict[str, deque[tuple[float, dict[str, Any]]]] = defaultdict(
            lambda: deque(maxlen=self._max)
        )

    def record(self, module_name: str, snapshot: dict[str, Any]) -> None:
        """记录一次采集快照。"""
        if not SNAPSHOT_BUFFER_ENABLED:
            return
        self._buffer[module_name].append((time.time(), snapshot))

    def get_latest(self, module_name: str) -> tuple[float, dict[str, Any]] | None:
        """获取模块最近一次快照 (timestamp, data)。"""
        buf = self._buffer.get(module_name)
        if not buf:
            return None
        return buf[-1]

    def get_all(self, module_name: str) -> list[tuple[float, dict[str, Any]]]:
        """获取模块所有缓冲快照。"""
        buf = self._buffer.get(module_name)
        return list(buf) if buf else []

    def gap_seconds(self, module_name: str) -> float | None:
        """计算当前距离最后一次快照的秒数。"""
        latest = self.get_latest(module_name)
        if latest is None:
            return None
        return time.time() - latest[0]

    @property
    def modules(self) -> list[str]:
        return list(self._buffer.keys())


# 全局单例
snapshot_buffer = SnapshotBuffer()
