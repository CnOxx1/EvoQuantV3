from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass, field


@dataclass
class AdaptiveBatchConfig:
    table_name: str
    current_batch_size: int = 500
    min_size: int = 50
    max_size: int = 2000
    target_latency_ms: float = float(os.environ.get("BATCH_TARGET_LATENCY_MS", "500"))


class AdaptiveBatchWriter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: dict[str, AdaptiveBatchConfig] = {}
        self._history: dict[str, deque[float]] = {}

    def _ensure_table(self, table_name: str) -> None:
        if table_name not in self._configs:
            self._configs[table_name] = AdaptiveBatchConfig(table_name=table_name)
            self._history[table_name] = deque(maxlen=10)

    def get_batch_size(self, table_name: str) -> int:
        with self._lock:
            self._ensure_table(table_name)
            return self._configs[table_name].current_batch_size

    def record_write(self, table_name: str, batch_size: int, latency_ms: float) -> None:
        with self._lock:
            self._ensure_table(table_name)
            self._history[table_name].append(latency_ms)
            cfg = self._configs[table_name]
            window = sorted(self._history[table_name])
            p50 = window[len(window) // 2]
            if p50 > cfg.target_latency_ms:
                new_size = int(cfg.current_batch_size * 0.8)
                cfg.current_batch_size = max(new_size, cfg.min_size)
            elif p50 < cfg.target_latency_ms * 0.5:
                new_size = int(cfg.current_batch_size * 1.1)
                cfg.current_batch_size = min(new_size, cfg.max_size)

    def metrics(self) -> dict:
        with self._lock:
            result = {}
            for name, cfg in self._configs.items():
                window = list(self._history[name])
                result[name] = {
                    "batch_size": cfg.current_batch_size,
                    "writes": len(window),
                    "p50_latency_ms": sorted(window)[len(window) // 2] if window else 0.0,
                }
            return result


adaptive_batch = AdaptiveBatchWriter()
