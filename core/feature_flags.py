from __future__ import annotations

import os
import threading

from loguru import logger


class FeatureFlags:
    """Thread-safe runtime feature flags read from environment variables."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._overrides: dict[str, bool] = {}

    def is_enabled(self, module_name: str) -> bool:
        with self._lock:
            if module_name in self._overrides:
                return self._overrides[module_name]
        env_key = f"FF_{module_name.upper()}_ENABLED"
        return os.environ.get(env_key, "1") == "1"

    def disable(self, module_name: str) -> None:
        with self._lock:
            self._overrides[module_name] = False
        logger.warning("Feature flag toggled: {} DISABLED", module_name)

    def enable(self, module_name: str) -> None:
        with self._lock:
            self._overrides[module_name] = True
        logger.info("Feature flag toggled: {} ENABLED", module_name)

    def list_disabled(self) -> list[str]:
        with self._lock:
            return [m for m, enabled in self._overrides.items() if not enabled]


feature_flags = FeatureFlags()
