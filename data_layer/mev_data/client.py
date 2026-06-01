"""mev_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class MevDataClient:
    """MEV 数据 API 客户端。

    数据源：
    - Flashbots API (MEV-Boost 数据)
    - EigenPhi (MEV 分析)
    """

    BASE_URLS = {
        "flashbots": "https://boost-relay.flashbots.net",
        "eigenphi": "https://api.eigenphi.io/v1",
    }

    def __init__(self, eigenphi_key: str = ""):
        self.eigenphi_key = eigenphi_key or os.environ.get("EIGENPHI_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_flashbots_blocks(self, limit: int = 100) -> list[dict]:
        """从 Flashbots 获取最近的 MEV 区块数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['flashbots']}/relay/v1/data/bidtraces/proposer_payload_delivered",
                params={"limit": limit},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Flashbots 请求失败: {e}")
            return []

    def fetch_eigenphi_mev_summary(self, timeframe: str = "1h") -> dict:
        """从 EigenPhi 获取 MEV 汇总数据。"""
        if not self.eigenphi_key:
            logger.debug("EigenPhi API key 未配置，跳过")
            return {}
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['eigenphi']}/mev/summary",
                params={"timeframe": timeframe},
                headers={"Authorization": f"Bearer {self.eigenphi_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as e:
            logger.warning(f"EigenPhi 请求失败: {e}")
            return {}

    def fetch_eigenphi_sandwich(self, limit: int = 50) -> list[dict]:
        """从 EigenPhi 获取三明治攻击数据。"""
        if not self.eigenphi_key:
            logger.debug("EigenPhi API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['eigenphi']}/mev/sandwich",
                params={"limit": limit},
                headers={"Authorization": f"Bearer {self.eigenphi_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"EigenPhi sandwich 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
