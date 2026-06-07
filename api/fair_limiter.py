from __future__ import annotations
import threading, time, os, random
from collections import defaultdict, deque

FAIR_LIMITER_MAX_QUEUE = int(os.getenv("FAIR_LIMITER_MAX_QUEUE", "10"))
FAIR_LIMITER_TOKENS_PER_SECOND = float(os.getenv("FAIR_LIMITER_TOKENS_PER_SECOND", "5"))


class FairShareLimiter:
    def __init__(self, max_queue: int = FAIR_LIMITER_MAX_QUEUE, tps: float = FAIR_LIMITER_TOKENS_PER_SECOND):
        self._max_queue = max_queue
        self._tps = tps
        self._lock = threading.Lock()
        self._buckets: dict[str, float] = defaultdict(lambda: tps)
        self._last_refill: dict[str, float] = defaultdict(time.time)
        self._queues: dict[str, deque] = defaultdict(deque)

    def _refill(self, ip: str) -> None:
        now = time.time()
        elapsed = now - self._last_refill[ip]
        self._buckets[ip] = min(self._tps, self._buckets[ip] + elapsed * self._tps)
        self._last_refill[ip] = now

    def acquire(self, client_ip: str, weight: int = 1) -> tuple[bool, float]:
        with self._lock:
            self._refill(client_ip)
            if self._buckets[client_ip] >= weight:
                self._buckets[client_ip] -= weight
                return True, 0.0
            if len(self._queues[client_ip]) >= self._max_queue:
                return False, 0.0
            wait = (weight - self._buckets[client_ip]) / self._tps + random.uniform(0.01, 0.05)
            self._queues[client_ip].append((weight, time.time()))
            return False, wait

    def drain_queue(self, client_ip: str) -> bool:
        with self._lock:
            self._refill(client_ip)
            q = self._queues.get(client_ip)
            if not q:
                return False
            weight, _ = q[0]
            if self._buckets[client_ip] >= weight:
                self._buckets[client_ip] -= weight
                q.popleft()
                return True
            return False

    def metrics(self) -> dict:
        with self._lock:
            # v4.5.0: dict keys() 视图直接做并集，避免 list() + set() 开销
            return {
                ip: {"queue_size": len(self._queues[ip]), "tokens": round(self._buckets[ip], 2)}
                for ip in (self._buckets.keys() | self._queues.keys())
            }


fair_limiter = FairShareLimiter()
