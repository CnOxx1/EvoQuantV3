"""prediction_market_data HTTP 客户端。"""

import httpx
from loguru import logger


class PredictionMarketClient:
    """Polymarket 预测市场 API 客户端。

    数据源：
    - Polymarket CLOB API (免费，无需 API Key)
    """

    BASE_URL = "https://clob.polymarket.com"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Active Markets ───────────────────────────────────────────────────

    def fetch_active_markets(self) -> list[dict]:
        """从 Polymarket 获取活跃预测市场列表。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/markets",
                params={"active": "true", "limit": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"Polymarket markets 请求失败: {e}")
            return []

    # ─── Market History ───────────────────────────────────────────────────

    def fetch_market_history(self, market_id: str) -> dict:
        """从 Polymarket 获取指定市场的详情与历史数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/markets/{market_id}",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Polymarket market detail 请求失败 ({market_id}): {e}")
            return {}

    def close(self):
        self._http.close()
