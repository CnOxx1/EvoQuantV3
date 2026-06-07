from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable

from loguru import logger


class ConfigWatcher:
    def __init__(self) -> None:
        self._watch_file = Path(os.getenv("CONFIG_WATCH_FILE", ".env"))
        self._callbacks: list[Callable[[dict[str, str]], None]] = []
        self._lock = threading.Lock()
        self._last_mtime: float = 0.0
        self._last_reload: float | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def on_change(self, callback: Callable[[dict[str, str]], None]) -> None:
        with self._lock:
            self._callbacks.append(callback)

    def start(self, poll_interval: float = 5.0) -> None:
        if os.getenv("CONFIG_HOT_RELOAD_ENABLED", "0") != "1":
            logger.debug("Config hot-reload disabled")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, args=(poll_interval,), daemon=True
        )
        self._thread.start()
        logger.info("ConfigWatcher started, polling every {}s", poll_interval)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

    def reload_now(self) -> None:
        self._check_and_reload(force=True)

    def last_reload_at(self) -> float | None:
        return self._last_reload

    def _poll_loop(self, interval: float) -> None:
        while self._running:
            self._check_and_reload()
            time.sleep(interval)

    def _check_and_reload(self, force: bool = False) -> None:
        if not self._watch_file.exists():
            return
        mtime = self._watch_file.stat().st_mtime
        if not force and mtime == self._last_mtime:
            return
        self._last_mtime = mtime
        changed = self._apply_env()
        if changed:
            self._last_reload = time.time()
            logger.info("Config reloaded, changed keys: {}", list(changed.keys()))
            with self._lock:
                for cb in self._callbacks:
                    cb(changed)

    def _apply_env(self) -> dict[str, str]:
        changed: dict[str, str] = {}
        for line in self._watch_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if os.environ.get(key) != value:
                os.environ[key] = value
                changed[key] = value
        return changed


config_watcher = ConfigWatcher()
