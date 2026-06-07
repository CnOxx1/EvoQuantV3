from __future__ import annotations

import threading
from collections import defaultdict


class EventBusMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriber_count: dict[str, int] = defaultdict(int)
        self._published: dict[str, int] = defaultdict(int)
        self._processed: dict[str, int] = defaultdict(int)
        self._dropped: dict[str, int] = defaultdict(int)
        self._duration_ms: dict[str, float] = defaultdict(float)

    def record_publish(self, topic: str) -> None:
        with self._lock:
            self._published[topic] += 1

    def record_handled(self, topic: str, duration_ms: float) -> None:
        with self._lock:
            self._processed[topic] += 1
            self._duration_ms[topic] += duration_ms

    def record_dropped(self, topic: str) -> None:
        with self._lock:
            self._dropped[topic] += 1

    def set_subscriber_count(self, topic: str, count: int) -> None:
        with self._lock:
            self._subscriber_count[topic] = count

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            topics = set(self._subscriber_count) | set(self._published) | set(self._processed) | set(self._dropped)
            return {t: {
                "subscriber_count": self._subscriber_count[t],
                "events_published": self._published[t],
                "events_processed": self._processed[t],
                "events_dropped": self._dropped[t],
                "total_handler_duration_ms": self._duration_ms[t],
            } for t in sorted(topics)}


event_bus_metrics = EventBusMetrics()
