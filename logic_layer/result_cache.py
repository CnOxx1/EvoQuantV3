from __future__ import annotations
import time, os, threading, functools, hashlib
from collections import OrderedDict
from typing import Any


class ResultCache:
    def __init__(self):
        self._default_ttl = int(os.getenv("LOGIC_CACHE_TTL", "300"))
        self._max_entries = int(os.getenv("LOGIC_CACHE_MAX_ENTRIES", "500"))
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            if key in self._store:
                value, expires = self._store[key]
                if time.time() < expires:
                    self._store.move_to_end(key)
                    self._hits += 1
                    return value
                del self._store[key]
            self._misses += 1
            return None

    def put(self, key: str, value: Any, ttl: int | None = None) -> None:
        exp = time.time() + (ttl if ttl is not None else self._default_ttl)
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, exp)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def invalidate(self, prefix: str) -> None:
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    @property
    def metrics(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses}


def cached_result(prefix: str, ttl: int | None = None):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            raw = f"{prefix}:{args}:{sorted(kwargs.items())}"
            # v4.3.0: 短 key 直接用字符串，避免 SHA-256 开销
            if len(raw) <= 128:
                key = raw
            else:
                key = prefix + ":" + hashlib.sha256(raw.encode()).hexdigest()[:16]
            result = logic_cache.get(key)
            if result is not None:
                return result
            result = fn(*args, **kwargs)
            logic_cache.put(key, result, ttl)
            return result
        return wrapper
    return decorator


logic_cache = ResultCache()
