from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass, field
from collections import defaultdict

from loguru import logger

ZSCORE_THRESHOLD = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "3.0"))
NULL_SPIKE_RATIO = 0.50
VOLUME_DROP_RATIO = 0.80


@dataclass
class AnomalyReport:
    key: str
    anomaly_type: str
    severity: str  # "warning" | "critical"
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class _RollingStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    @property
    def std(self) -> float:
        return (self.m2 / self.count) ** 0.5 if self.count > 1 else 0.0

    def update(self, values: list[float]) -> None:
        for x in values:
            self.count += 1
            delta = x - self.mean
            self.mean += delta / self.count
            self.m2 += delta * (x - self.mean)


class DataAnomalyDetector:
    def __init__(self, zscore_threshold: float = ZSCORE_THRESHOLD) -> None:
        self._threshold = zscore_threshold
        self._stats: dict[str, _RollingStats] = defaultdict(_RollingStats)
        self._volume: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, key: str, values: list[float]) -> list[AnomalyReport]:
        reports: list[AnomalyReport] = []
        with self._lock:
            stats = self._stats[key]
            # Z-score anomalies
            if stats.count > 10 and stats.std > 0:
                for v in values:
                    z = abs(v - stats.mean) / stats.std
                    if z >= self._threshold:
                        sev = "critical" if z >= self._threshold * 1.5 else "warning"
                        reports.append(AnomalyReport(
                            key=key, anomaly_type="zscore", severity=sev,
                            message=f"z={z:.2f} val={v:.4g}",
                        ))
            # Volume drop detection
            n = float(len(values))
            prev = self._volume.get(key)
            if prev and prev > 0 and n < prev * (1 - VOLUME_DROP_RATIO):
                reports.append(AnomalyReport(
                    key=key, anomaly_type="volume_drop", severity="critical",
                    message=f"volume {int(n)} vs rolling {prev:.0f}",
                ))
            self._volume[key] = n if prev is None else prev * 0.9 + n * 0.1
            stats.update(values)
        if reports:
            logger.warning(f"Anomalies on '{key}': {len(reports)} detected")
        return reports

    def check_nulls(self, key: str, total: int, null_count: int) -> AnomalyReport | None:
        if total == 0:
            return None
        ratio = null_count / total
        if ratio > NULL_SPIKE_RATIO:
            sev = "critical" if ratio > 0.8 else "warning"
            r = AnomalyReport(
                key=key, anomaly_type="null_spike", severity=sev,
                message=f"{null_count}/{total} nulls ({ratio:.0%})",
            )
            logger.warning(f"Null spike on '{key}': {r.message}")
            return r
        return None


data_anomaly_detector = DataAnomalyDetector()
