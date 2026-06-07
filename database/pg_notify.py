from __future__ import annotations

import json
import os
import threading
import time
from typing import Callable

from loguru import logger

CHANNEL = "evoquant_cache_invalidation"
PG_NOTIFY_ENABLED = os.getenv("PG_NOTIFY_ENABLED", "0") == "1"


class PgNotifyBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def publish_invalidation(self, prefix: str) -> None:
        if not PG_NOTIFY_ENABLED:
            return
        try:
            import psycopg2
            from database.pool_config import get_pg_dsn
            conn = psycopg2.connect(get_pg_dsn())
            conn.set_isolation_level(0)
            payload = json.dumps({"prefix": prefix, "timestamp": time.time()})
            with conn.cursor() as cur:
                cur.execute(f"NOTIFY {CHANNEL}, %s", (payload,))
            conn.close()
        except Exception as e:
            logger.debug(f"pg_notify publish skipped: {e}")

    def start_listener(self, on_invalidate: Callable[[str], None]) -> None:
        if not PG_NOTIFY_ENABLED:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, args=(on_invalidate,), daemon=True
        )
        self._thread.start()

    def _listen_loop(self, on_invalidate: Callable[[str], None]) -> None:
        try:
            import psycopg2
            import select
            from database.pool_config import get_pg_dsn
            conn = psycopg2.connect(get_pg_dsn())
            conn.set_isolation_level(0)
            with conn.cursor() as cur:
                cur.execute(f"LISTEN {CHANNEL}")
            while self._running:
                if select.select([conn], [], [], 1.0) == ([], [], []):
                    continue
                conn.poll()
                while conn.notifies:
                    n = conn.notifies.pop(0)
                    data = json.loads(n.payload)
                    on_invalidate(data["prefix"])
            conn.close()
        except Exception as e:
            logger.debug(f"pg_notify listener stopped: {e}")

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=2)


pg_notify_bridge = PgNotifyBridge()
