"""cefi_lending_rate HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class CefiLendingRateClient:
    """CeFi 借贷利率 API 客户端。

    数据源：
    - Binance Earn (活期/定期利率)
    - OKX Earn (借贷利率)
    - Bybit Earn (理财利率)
    """

    BASE_URLS = {
        "binance": "https://api.binance.com",
        "okx": "https://www.okx.com",
        "bybit": "https://api.bybit.com",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_binance_lending_rates(self, asset: str = "BTC") -> list[dict]:
        """获取 Binance 活期理财利率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['binance']}/sapi/v1/simple-earn/flexible/list",
                params={"asset": asset, "size": 20},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("rows", [])
        except Exception as e:
            logger.warning(f"Binance lending 请求失败 [{asset}]: {e}")
            return []

    def fetch_binance_margin_rates(self, asset: str = "BTC") -> dict:
        """获取 Binance 杠杆借贷利率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['binance']}/sapi/v1/margin/next-hourly-interest-rate",
                params={"assets": asset, "isIsolated": "FALSE"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else {}
        except Exception as e:
            logger.warning(f"Binance margin rate 请求失败 [{asset}]: {e}")
            return {}

    def fetch_okx_lending_rates(self) -> list[dict]:
        """获取 OKX 借贷利率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['okx']}/api/v5/finance/savings/lending-rate-history",
                params={"ccy": "BTC"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"OKX lending 请求失败: {e}")
            return []

    def fetch_bybit_lending_rates(self) -> list[dict]:
        """获取 Bybit 借贷利率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['bybit']}/v5/earn/lending/coin-info",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {}).get("list", [])
        except Exception as e:
            logger.warning(f"Bybit lending 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
