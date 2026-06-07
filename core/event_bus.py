"""事件总线 — 轻量级进程内发布/订阅。

v4.2.0 优化:
- handler list 缓存（subscribe 时失效），避免每次 dispatch 做 list() 拷贝
- 轮询间隔从 100ms 降至 10ms，减少事件延迟
- f-string 日志改为 loguru 延迟格式化
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from queue import Queue
from typing import Callable

from loguru import logger

TOPIC_DATA_COLLECTED = "data.collected"
TOPIC_INDICATOR_COMPUTED = "indicator.computed"
TOPIC_ANOMALY_DETECTED = "anomaly.detected"
TOPIC_PIPELINE_COMPLETE = "pipeline.complete"


@dataclass
class Event:
    topic: str
    payload: dict
    timestamp: float = field(default_factory=time.time)
    source: str = ""


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()
        self._queue: Queue[Event] = Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        # v4.2.0: 缓存 handler list，避免每次 dispatch 做 list() 拷贝
        self._handler_cache: dict[str, tuple[Callable[[Event], None], ...]] = {}

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subs.setdefault(topic, []).append(handler)
            # 失效对应 topic 的缓存
            self._handler_cache.pop(topic, None)

    def _dispatch(self, event: Event) -> None:
        # v4.2.0: 使用缓存的 handler tuple，避免每次 list() 拷贝
        topic = event.topic
        handlers = self._handler_cache.get(topic)
        if handlers is None:
            with self._lock:
                handlers = tuple(self._subs.get(topic, ()))
                self._handler_cache[topic] = handlers
        for h in handlers:
            try:
                h(event)
            except Exception as e:
                logger.error("EventBus handler error: {}", e)

    def publish(self, topic: str, payload: dict, source: str = "") -> None:
        self._dispatch(Event(topic=topic, payload=payload, source=source))

    def publish_async(self, topic: str, payload: dict, source: str = "") -> None:
        self._queue.put(Event(topic=topic, payload=payload, source=source))

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._consume, daemon=True)
        self._thread.start()
        logger.debug("EventBus started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.debug("EventBus stopped")

    def _consume(self) -> None:
        while self._running:
            try:
                # v4.2.0: 轮询间隔从 100ms 降至 10ms，减少事件延迟
                event = self._queue.get(timeout=0.01)
            except Exception:
                continue
            self._dispatch(event)


event_bus = EventBus()