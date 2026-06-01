"""perpetual_dex_data HTTP 客户端。"""

import httpx
from loguru import logger


class PerpDexDataClient:
    """永续合约 DEX 数据 API 客户端。

    数据源：
    - dYdX v4 (Indexer API)
    - Hyperliquid (Info API)
    - GMX (公开 API)
    """

    BASE_URLS = {
        "dydx": "https://indexer.dydx.trade/v4",
        "hyperliquid": "https://api.hyperliquid.xyz",
        "gmx": "https://api.gmx.io",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── dYdX ────────────────────────────────────────────────────────────

    def fetch_dydx_markets(self) -> list[dict]:
        """从 dYdX 获取永续合约市场数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['dydx']}/perpetualMarkets",
            )
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", {})
            return list(markets.values()) if isinstance(markets, dict) else []
        except Exception as e:
            logger.warning(f"dYdX perpetualMarkets 请求失败: {e}")
            return []

    def fetch_dydx_funding(self, symbol: str) -> list[dict]:
        """从 dYdX 获取指定交易对的历史资金费率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['dydx']}/historicalFunding/{symbol}",
            )
            resp.raise_for_status()
            return resp.json().get("historicalFunding", [])
        except Exception as e:
            logger.warning(f"dYdX historicalFunding 请求失败 ({symbol}): {e}")
            return []

    # ─── Hyperliquid ─────────────────────────────────────────────────────

    def fetch_hyperliquid_meta(self) -> dict:
        """从 Hyperliquid 获取永续合约元数据。"""
        try:
            resp = self._http.post(
                f"{self.BASE_URLS['hyperliquid']}/info",
                json={"type": "meta"},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Hyperliquid meta 请求失败: {e}")
            return {}

    def fetch_hyperliquid_funding(self) -> list[dict]:
        """从 Hyperliquid 获取资金费率历史。"""
        try:
            resp = self._http.post(
                f"{self.BASE_URLS['hyperliquid']}/info",
                json={"type": "fundingHistory"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Hyperliquid fundingHistory 请求失败: {e}")
            return []

    def fetch_hyperliquid_open_interest(self) -> list[dict]:
        """从 Hyperliquid 获取未平仓合约与资产上下文。"""
        try:
            resp = self._http.post(
                f"{self.BASE_URLS['hyperliquid']}/info",
                json={"type": "metaAndAssetCtxs"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"Hyperliquid metaAndAssetCtxs 请求失败: {e}")
            return []

    # ─── GMX ─────────────────────────────────────────────────────────────

    def fetch_gmx_positions(self) -> list[dict]:
        """从 GMX 获取持仓数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['gmx']}/positions",
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"GMX positions 请求失败: {e}")
            return []

    def fetch_gmx_funding(self) -> list[dict]:
        """从 GMX 获取资金费率数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['gmx']}/funding_rates",
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"GMX funding_rates 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
