"""perpetual_basis_curve HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class PerpetualBasisCurveClient:
    """期货期限结构 API 客户端。

    数据源：
    - Binance Futures (永续 + 季度合约)
    - OKX Futures (永续 + 季度合约)
    - Bybit Futures (永续 + 季度合约)
    """

    BASE_URLS = {
        "binance": "https://fapi.binance.com",
        "okx": "https://www.okx.com",
        "bybit": "https://api.bybit.com",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_binance_futures_prices(self, symbol: str = "BTCUSDT") -> list[dict]:
        """获取 Binance 所有合约价格（永续+季度）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['binance']}/fapi/v1/premiumIndex",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            data = resp.json()
            return [data] if isinstance(data, dict) else data
        except Exception as e:
            logger.warning(f"Binance futures 请求失败 [{symbol}]: {e}")
            return []

    def fetch_binance_delivery_prices(self, pair: str = "BTCUSD") -> list[dict]:
        """获取 Binance 季度交割合约价格。"""
        try:
            resp = self._http.get(
                f"https://dapi.binance.com/dapi/v1/premiumIndex",
                params={"pair": pair},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Binance delivery 请求失败 [{pair}]: {e}")
            return []

    def fetch_okx_futures_prices(self, inst_type: str = "FUTURES") -> list[dict]:
        """获取 OKX 期货合约价格。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['okx']}/api/v5/market/tickers",
                params={"instType": inst_type},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"OKX futures 请求失败: {e}")
            return []

    def fetch_bybit_futures_prices(self, category: str = "linear") -> list[dict]:
        """获取 Bybit 期货合约行情。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['bybit']}/v5/market/tickers",
                params={"category": category},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {}).get("list", [])
        except Exception as e:
            logger.warning(f"Bybit futures 请求失败: {e}")
            return []

    def fetch_spot_price(self, symbol: str = "BTCUSDT") -> float | None:
        """获取 Binance 现货价格作为基准。"""
        try:
            resp = self._http.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol},
            )
            resp.raise_for_status()
            return float(resp.json()["price"])
        except Exception as e:
            logger.warning(f"现货价格请求失败 [{symbol}]: {e}")
            return None

    def close(self):
        self._http.close()
