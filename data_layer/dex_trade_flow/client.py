"""dex_trade_flow HTTP 客户端。"""

import httpx
from loguru import logger


class DexTradeFlowClient:
    """DEX 大额交易流 API 客户端。

    数据源：
    - 0x API (路由交易数据)
    - 1inch API (路由交易数据)
    """

    BASE_URL_0X = "https://api.0x.org"
    BASE_URL_1INCH = "https://api.1inch.dev"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_recent_trades(self, min_usd: int = 50000) -> list[dict]:
        """获取近期大额 DEX 交易。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL_0X}/swap/v1/trades",
                params={"minAmountUSD": min_usd, "limit": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("trades", [])
        except Exception as e:
            logger.warning(f"DEX recent trades 请求失败: {e}")
            return []

    def fetch_router_volume(self) -> list[dict]:
        """获取路由器交易量统计。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL_0X}/swap/v1/sources",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("sources", [])
        except Exception as e:
            logger.warning(f"DEX router volume 请求失败: {e}")
            return []

    def fetch_mev_victims(self) -> list[dict]:
        """获取 MEV 受害交易数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL_0X}/swap/v1/mev-victims",
                params={"limit": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("victims", [])
        except Exception as e:
            logger.warning(f"MEV victims 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
