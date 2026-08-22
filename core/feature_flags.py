from __future__ import annotations

import os
import threading

from loguru import logger


# Domains whose current integrations require a commercial licence, rely on a
# retired endpoint, lack verified entity attribution, or have no implemented
# public-source collector. They must not appear as runtime errors merely because
# their storage tables are intentionally absent. Operators can explicitly opt
# in with FF_*_ENABLED=1 after obtaining a licence or deploying a compatible
# collector.
DEFAULT_DISABLED_DOMAINS = frozenset({
    "etf_flow",
    "whale_tracker",
    "whale_pnl",
    "social_sentiment",
    "nft_market",
    "dex_trade_flow",
    "exchange_reserve",
    "liquidity_regime",
    "sentiment_composite",
    "regulatory",
    "onchain_address",
    "derivatives_sentiment",
    "onchain_holder",
    "token_unlock",
})


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
        default = "0" if module_name in DEFAULT_DISABLED_DOMAINS else "1"
        return os.environ.get(env_key, default) == "1"

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
