"""whale_tracker_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class WhaleTrackerClient:
    """巨鲸追踪 API 客户端。

    支持数据源：
    - Whale Alert API (大额转账实时追踪)
    - Arkham Intelligence (标记地址行为)
    - Nansen (Smart Money 追踪)
    """

    BASE_URLS = {
        "whale_alert": "https://api.whale-alert.io/v1",
        "arkham": "https://api.arkhamintelligence.com/v1",
        "nansen": "https://api.nansen.ai/v1",
    }

    def __init__(self, whale_alert_key: str = "", arkham_key: str = "", nansen_key: str = ""):
        self.whale_alert_key = whale_alert_key or os.environ.get("WHALE_ALERT_API_KEY", "")
        self.arkham_key = arkham_key or os.environ.get("ARKHAM_API_KEY", "")
        self.nansen_key = nansen_key or os.environ.get("NANSEN_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_whale_alert_transactions(self, min_value_usd: int = 1000000, limit: int = 100) -> list[dict]:
        """从 Whale Alert 获取大额转账。"""
        if not self.whale_alert_key:
            logger.debug("Whale Alert API key 未配置，跳过")
            return []
        try:
            import time
            cursor = int(time.time()) - 3600  # 最近 1 小时
            resp = self._http.get(
                f"{self.BASE_URLS['whale_alert']}/transactions",
                params={
                    "api_key": self.whale_alert_key,
                    "min_value": min_value_usd,
                    "start": cursor,
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("transactions", [])
        except Exception as e:
            logger.warning(f"Whale Alert 请求失败: {e}")
            return []

    def fetch_arkham_transfers(self, entity: str, limit: int = 50) -> list[dict]:
        """从 Arkham 获取标记地址转账。"""
        if not self.arkham_key:
            logger.debug("Arkham API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['arkham']}/transfers",
                params={"entity": entity, "limit": limit},
                headers={"API-Key": self.arkham_key},
            )
            resp.raise_for_status()
            return resp.json().get("transfers", [])
        except Exception as e:
            logger.warning(f"Arkham 请求失败 [{entity}]: {e}")
            return []

    def fetch_nansen_smart_money(self, token: str, timeframe: str = "24h") -> list[dict]:
        """从 Nansen 获取 Smart Money 流向。"""
        if not self.nansen_key:
            logger.debug("Nansen API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['nansen']}/smart-money/token-flows",
                params={"token": token, "timeframe": timeframe},
                headers={"Authorization": f"Bearer {self.nansen_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"Nansen 请求失败 [{token}]: {e}")
            return []

    def close(self):
        self._http.close()
