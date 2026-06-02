"""cross_chain_messaging HTTP 客户端。"""

import httpx
from loguru import logger


class CrossChainMessagingClient:
    """跨链消息协议数据 API 客户端。

    数据源：
    - LayerZero Scan API (跨链消息频率与延迟)
    - Wormhole Scan API (跨链消息统计)
    """

    LAYERZERO_URL = "https://scan.layerzero-api.com"
    WORMHOLE_URL = "https://api.wormholescan.io"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_layerzero_stats(self) -> dict:
        """获取 LayerZero 协议统计数据。"""
        try:
            resp = self._http.get(
                f"{self.LAYERZERO_URL}/v1/messages/stats",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"LayerZero stats 请求失败: {e}")
            return {}

    def fetch_wormhole_stats(self) -> dict:
        """获取 Wormhole 协议统计数据。"""
        try:
            resp = self._http.get(
                f"{self.WORMHOLE_URL}/api/v1/last-txs",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Wormhole stats 请求失败: {e}")
            return {}

    def fetch_messaging_volume(self) -> list[dict]:
        """获取跨链消息量数据。"""
        try:
            resp = self._http.get(
                f"{self.WORMHOLE_URL}/api/v1/scorecards",
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else [data]
        except Exception as e:
            logger.warning(f"Messaging volume 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
