from __future__ import annotations
import time
import threading
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AlertGroup:
    category: str
    severity: str
    count: int
    first_seen: float
    last_seen: float
    sample_message: str


class AlertAggregator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: dict[tuple[str, str], AlertGroup] = {}

    def ingest(self, category: str, severity: str, message: str) -> None:
        key = (category, severity)
        now = time.time()
        with self._lock:
            if key in self._groups:
                g = self._groups[key]
                g.count += 1
                g.last_seen = now
            else:
                self._groups[key] = AlertGroup(
                    category=category, severity=severity, count=1,
                    first_seen=now, last_seen=now, sample_message=message,
                )

    def flush(self, window_seconds: int = 60) -> list[AlertGroup]:
        now = time.time()
        with self._lock:
            ready = [g for g in self._groups.values() if now - g.first_seen >= window_seconds]
            for g in ready:
                del self._groups[(g.category, g.severity)]
        return ready

    def pending_count(self) -> int:
        with self._lock:
            return sum(g.count for g in self._groups.values())


alert_aggregator = AlertAggregator()
