"""Deribit 公开 API 客户端 — 无需认证，覆盖 BTC/ETH 期权数据。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import wraps

from loguru import logger

from config.settings import MAX_RETRIES, RETRY_DELAY


def _retry(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (TimeoutError, OSError, urllib.error.URLError, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    f"[Deribit.{func.__name__}] 请求失败 "
                    f"(第{attempt}/{MAX_RETRIES}次): {exc}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        raise last_exc
    return wrapper


class DeribitClient:
    """Deribit 公开 API 客户端。

    Base URL: https://www.deribit.com/api/v2/public/
    限制: 20 requests/s (远超需求)
    覆盖: BTC, ETH 期权
    """

    BASE_URL = "https://www.deribit.com/api/v2/public"
    SUPPORTED_CURRENCIES = ["BTC", "ETH"]
    TIMEOUT = 15

    # entity_key → Deribit currency
    ENTITY_CURRENCY_MAP = {
        "BTC": "BTC",
        "ETH": "ETH",
    }

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """发送 GET 请求到 Deribit 公开 API。"""
        url = f"{self.BASE_URL}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "EvoQuant/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("result", data)

    @_retry
    def get_book_summary_by_currency(
        self, currency: str, kind: str = "option"
    ) -> list[dict]:
        """获取指定币种所有期权的 book summary（含 OI、IV 等）。"""
        result = self._request(
            "get_book_summary_by_currency",
            {"currency": currency, "kind": kind},
        )
        return result if isinstance(result, list) else []

    @_retry
    def get_index_price(self, currency: str) -> float:
        """获取指数价格。"""
        index_name = f"{currency.lower()}_usd"
        result = self._request("get_index_price", {"index_name": index_name})
        return float(result.get("index_price", 0))

    @_retry
    def get_historical_volatility(self, currency: str) -> list[list]:
        """获取历史波动率序列。"""
        result = self._request(
            "get_historical_volatility", {"currency": currency}
        )
        return result if isinstance(result, list) else []

    @_retry
    def get_instruments(self, currency: str, kind: str = "option") -> list[dict]:
        """获取所有活跃期权合约列表。"""
        result = self._request(
            "get_instruments",
            {"currency": currency, "kind": kind, "expired": "false"},
        )
        return result if isinstance(result, list) else []

    def get_options_snapshot(self, currency: str) -> dict:
        """获取完整的期权市场快照，供各 collector 使用。

        返回结构:
        {
            "currency": "BTC",
            "index_price": 67000.0,
            "instruments": [...],
            "book_summaries": [...],
            "historical_vol": [...],
        }
        """
        index_price = self.get_index_price(currency)
        book_summaries = self.get_book_summary_by_currency(currency)
        historical_vol = self.get_historical_volatility(currency)

        return {
            "currency": currency,
            "index_price": index_price,
            "book_summaries": book_summaries,
            "historical_vol": historical_vol,
        }

    def get_all_snapshots(
        self, entity_keys: list[str] | None = None
    ) -> dict[str, dict]:
        """获取所有支持币种的期权快照。"""
        results: dict[str, dict] = {}
        targets = self.SUPPORTED_CURRENCIES
        if entity_keys:
            targets = [
                c for c in targets
                if c in [k.upper() for k in entity_keys]
            ]
        for currency in targets:
            try:
                results[currency] = self.get_options_snapshot(currency)
            except Exception as exc:
                logger.warning(f"Deribit 快照获取失败 [{currency}]: {exc}")
        return results
