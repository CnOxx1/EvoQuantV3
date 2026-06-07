from __future__ import annotations
import collections
import dataclasses
import os
import threading
import time
from contextlib import contextmanager

try:
    import psutil
    _PROCESS = psutil.Process(os.getpid())
    def _rss_mb() -> float:
        return _PROCESS.memory_info().rss / (1024 * 1024)
except ImportError:
    def _rss_mb() -> float:
        return 0.0


@dataclasses.dataclass
class ProfileResult:
    module_name: str
    duration_s: float
    peak_rss_mb: float
    cpu_percent: float
    timestamp: float


class RuntimeProfiler:
    def __init__(self, window: int = 100):
        self._window = window
        self._results: dict[str, collections.deque[ProfileResult]] = {}
        self._lock = threading.Lock()

    @contextmanager
    def profile(self, module_name: str):
        rss_before = _rss_mb()
        t0 = time.time()
        cpu0 = time.process_time()
        yield
        duration = time.time() - t0
        cpu_time = time.process_time() - cpu0
        rss_after = _rss_mb()
        cpu_pct = (cpu_time / duration * 100) if duration > 0 else 0.0
        result = ProfileResult(module_name, duration, max(rss_before, rss_after), cpu_pct, t0)
        with self._lock:
            dq = self._results.setdefault(module_name, collections.deque(maxlen=self._window))
            dq.append(result)

    def get_results(self, top_n: int = 10) -> list[ProfileResult]:
        with self._lock:
            all_r = [r for dq in self._results.values() for r in dq]
        all_r.sort(key=lambda r: r.duration_s, reverse=True)
        return all_r[:top_n]

    def get_module_stats(self, module_name: str) -> dict | None:
        with self._lock:
            dq = self._results.get(module_name)
            if not dq:
                return None
            durations = [r.duration_s for r in dq]
        return {"avg": sum(durations) / len(durations), "max": max(durations), "min": min(durations)}

    def clear(self) -> None:
        with self._lock:
            self._results.clear()


runtime_profiler = RuntimeProfiler()
