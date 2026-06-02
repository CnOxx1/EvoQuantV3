"""nft_market_data HTTP 客户端。"""

import httpx
from loguru import logger


class NftMarketClient:
    """NFT 市场数据 API 客户端。

    数据源：
    - Reservoir (蓝筹地板价、交易量、wash trading 检测)
    """

    BASE_URL = "https://api.reservoir.tools"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_top_collections(self, limit: int = 50) -> list[dict]:
        """获取 Top NFT 集合数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/collections/v7",
                params={"limit": limit, "sortBy": "allTimeVolume"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("collections", [])
        except Exception as e:
            logger.warning(f"NFT top collections 请求失败: {e}")
            return []

    def fetch_collection_stats(self, slug: str) -> dict:
        """获取单个集合的详细统计。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/collections/{slug}/v1",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"NFT collection stats 请求失败 [{slug}]: {e}")
            return {}

    def fetch_market_overview(self) -> dict:
        """获取 NFT 市场整体概览。"""
        try:
            resp = self._http.get(f"{self.BASE_URL}/collections/daily-volumes/v1")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"NFT market overview 请求失败: {e}")
            return {}

    def close(self):
        self._http.close()
