"""etf_flow_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class EtfFlowClient:
    """ETF 资金流 API 客户端。

    数据源：
    - SoSoValue API (BTC/ETH ETF 每日净流入)
    """

    BASE_URL = "https://api.sosovalue.com/v1"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("SOSOVALUE_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_etf_flows(self, asset: str = "BTC", days: int = 7) -> list[dict]:
        """获取 ETF 每日资金流数据。"""
        if not self.api_key:
            logger.debug("SoSoValue API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/etf/flows",
                params={"asset": asset, "days": days},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"SoSoValue ETF flows 请求失败 [{asset}]: {e}")
            return []

    def fetch_etf_aum(self, asset: str = "BTC") -> list[dict]:
        """获取 ETF AUM 快照。"""
        if not self.api_key:
            logger.debug("SoSoValue API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/etf/aum",
                params={"asset": asset},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"SoSoValue ETF AUM 请求失败 [{asset}]: {e}")
            return []

    def close(self):
        self._http.close()
