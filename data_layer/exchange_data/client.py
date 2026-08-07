import time
import threading

import ccxt
import requests as _requests
from loguru import logger

from config.settings import (
    API_KEYS,
    BINANCE_LOAD_SPOT_MARKETS_ONLY,
    BINANCE_PUBLIC_API_BASE,
    EXCHANGE_CONFIG,
    MAX_RETRIES,
    PROXY_URL,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
)
from data_layer.exchange_data.circuit_breaker import circuit_registry, CircuitOpenError


def is_geo_restricted_error(exc: BaseException) -> bool:
    """Detect venue geo/eligibility blocks that should not be retried."""
    msg = str(exc).lower()
    if "restricted location" in msg or "eligibility" in msg:
        return True
    if "block access from your country" in msg:
        return True
    if "cloudfront" in msg and "403" in msg:
        return True
    # Bare HTTP status markers commonly present in ccxt error strings.
    if " 451 " in f" {msg} " or msg.rstrip().endswith(" 451"):
        return True
    return False


class ExchangeClientManager:
    """交易所客户端统一管理器，基于 ccxt 封装"""

    def __init__(self):
        self._local = threading.local()

    def _thread_clients(self) -> dict[str, ccxt.Exchange]:
        clients = getattr(self._local, "clients", None)
        if clients is None:
            clients = {}
            self._local.clients = clients
        return clients

    @staticmethod
    def _normalize_market_type(market_type: str | None) -> str:
        normalized = str(market_type or "spot").strip().lower()
        if normalized in {"swap", "linear_swap", "perp", "perpetual"}:
            return "swap"
        return "spot"

    def _client_cache_key(self, exchange_name: str, market_type: str | None) -> str:
        normalized_market_type = self._normalize_market_type(market_type)
        return f"{exchange_name}:{normalized_market_type}"

    @staticmethod
    def _apply_binance_public_data_host(
        client: ccxt.Exchange,
        *,
        market_type: str,
    ) -> None:
        """Point Binance spot public REST at the geo-friendly data host when configured."""
        if not BINANCE_PUBLIC_API_BASE:
            return
        api_urls = client.urls.get("api")
        if not isinstance(api_urls, dict):
            return
        # Spot public market data only — futures remain on fapi (often still geo-blocked).
        if market_type == "spot":
            api_urls["public"] = f"{BINANCE_PUBLIC_API_BASE}/api/v3"
            api_urls["v1"] = f"{BINANCE_PUBLIC_API_BASE}/api/v1"
            logger.info(
                f"[binance] spot public API → {BINANCE_PUBLIC_API_BASE} "
                "(geo-friendly market data host)"
            )
        if market_type == "spot" and BINANCE_LOAD_SPOT_MARKETS_ONLY:
            # Prevent load_markets() from calling fapi/dapi (HTTP 451 in restricted regions).
            client.options["fetchMarkets"] = ["spot"]

    def _create_client(
        self,
        exchange_name: str,
        market_type: str | None = "spot",
    ) -> ccxt.Exchange:
        """创建单个交易所客户端实例"""
        if exchange_name not in EXCHANGE_CONFIG:
            raise ValueError(f"不支持的交易所: {exchange_name}")

        config = EXCHANGE_CONFIG[exchange_name]
        if not config.get("enabled", False):
            raise ValueError(f"交易所 {exchange_name} 未启用")

        exchange_class = getattr(ccxt, exchange_name, None)
        if exchange_class is None:
            raise ValueError(f"ccxt 不支持交易所: {exchange_name}")

        normalized_market_type = self._normalize_market_type(market_type)
        # 构建初始化参数
        options = dict(config.get("options", {}))
        if normalized_market_type == "swap":
            options["defaultType"] = "swap"
            options.setdefault("defaultSubType", "linear")
        init_params = {
            "enableRateLimit": config.get("rate_limit", True),
            "timeout": REQUEST_TIMEOUT,
            "options": options,
        }

        # 注入 API Key（如果配置了非空值）
        api_key_config = API_KEYS.get(exchange_name, {})
        if api_key_config.get("apiKey"):
            init_params.update(api_key_config)

        client = exchange_class(init_params)

        # HTTP keep-alive: reuse TCP connections across requests to reduce
        # handshake overhead on high-frequency collection cycles.
        client.session = _requests.Session()

        if exchange_name == "binance":
            self._apply_binance_public_data_host(
                client,
                market_type=normalized_market_type,
            )

        # 配置代理
        if PROXY_URL:
            client.proxies = {
                "http": PROXY_URL,
                "https": PROXY_URL,
            }
            if "socks" in PROXY_URL:
                client.aiohttp_proxy = PROXY_URL
            logger.debug(f"[{exchange_name}] 已配置代理: {PROXY_URL}")
        logger.info(f"已创建交易所客户端: {exchange_name} [{normalized_market_type}]")
        return client

    def get_client(
        self,
        exchange_name: str,
        market_type: str | None = "spot",
    ) -> ccxt.Exchange:
        """获取交易所客户端（懒加载单例）"""
        clients = self._thread_clients()
        cache_key = self._client_cache_key(exchange_name, market_type)
        if cache_key not in clients:
            clients[cache_key] = self._create_client(
                exchange_name,
                market_type=market_type,
            )
        return clients[cache_key]

    def get_all_clients(
        self,
        market_type: str | None = "spot",
    ) -> dict[str, ccxt.Exchange]:
        """获取所有已启用交易所的客户端"""
        clients = self._thread_clients()
        for name, config in EXCHANGE_CONFIG.items():
            cache_key = self._client_cache_key(name, market_type)
            if config.get("enabled", False) and cache_key not in clients:
                try:
                    clients[cache_key] = self._create_client(
                        name,
                        market_type=market_type,
                    )
                except Exception as e:
                    logger.error(f"创建交易所客户端失败 [{name}]: {e}")
        return clients

    def close_all(self):
        """关闭所有客户端连接"""
        clients = self._thread_clients()
        for name in list(clients.keys()):
            logger.info(f"已释放交易所客户端: {name}")
        clients.clear()


def retry_on_failure(func):
    """装饰器：对交易所API调用进行自动重试，集成熔断器保护。"""
    def wrapper(*args, **kwargs):
        # 从参数中推断交易所名称作为熔断器 key
        breaker_name = _infer_breaker_name(func, args, kwargs)
        breaker = circuit_registry.get(breaker_name)

        if not breaker.allow_request():
            raise CircuitOpenError(breaker_name)

        last_exception = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                last_exception = e
                breaker.record_failure()
                if is_geo_restricted_error(e):
                    logger.warning(
                        f"[{func.__name__}] 交易所地域限制，跳过重试: {e}"
                    )
                    raise
                logger.warning(
                    f"[{func.__name__}] 网络错误 (第{attempt}/{MAX_RETRIES}次): {e}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
            except ccxt.RateLimitExceeded as e:
                last_exception = e
                breaker.record_failure()
                # Bybit geo-blocks often surface as 403 RateLimitExceeded in ccxt.
                if is_geo_restricted_error(e):
                    logger.warning(
                        f"[{func.__name__}] 交易所地域限制，跳过重试: {e}"
                    )
                    raise
                wait_time = RETRY_DELAY * attempt * 2
                logger.warning(
                    f"[{func.__name__}] 频率限制 (第{attempt}/{MAX_RETRIES}次), "
                    f"等待{wait_time}秒: {e}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait_time)
            except ccxt.ExchangeError as e:
                logger.error(f"[{func.__name__}] 交易所错误: {e}")
                breaker.record_failure()
                raise
        raise last_exception
    return wrapper


def _infer_breaker_name(func, args, kwargs) -> str:
    """从函数参数推断熔断器名称（exchange_name 或 self.manager 上下文）。"""
    # 尝试从 kwargs 获取
    if "exchange_name" in kwargs:
        return f"exchange:{kwargs['exchange_name']}"
    # 尝试从位置参数获取（跳过 self）
    # 常见模式: self, exchange_name, symbol, ...
    for arg in args:
        if isinstance(arg, str) and arg in ("binance", "okx", "bybit"):
            return f"exchange:{arg}"
    return f"exchange:{getattr(func, '__name__', 'unknown')}"
