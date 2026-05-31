"""bridge_flow_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class BridgeFlowClient:
    """跨链桥数据 API 客户端。

    数据源：
    - DefiLlama Bridges (跨链桥交易量和流向)
    """

    BASE_URLS = {
        "bridges": "https://bridges.llama.fi",
    }

    # 追踪的主要链
    TRACKED_CHAINS = [
        "Ethereum", "Arbitrum", "Optimism", "Base", "Polygon",
        "BSC", "Avalanche", "Solana", "Sui", "Aptos",
    ]

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_bridges_overview(self) -> list[dict]:
        """获取所有桥的概览数据。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['bridges']}/bridges?includeChains=true")
            resp.raise_for_status()
            data = resp.json()
            return data.get("bridges", [])
        except Exception as e:
            logger.warning(f"Bridges overview 请求失败: {e}")
            return []

    def fetch_bridge_volume(self, bridge_id: int) -> dict:
        """获取单个桥的交易量数据。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['bridges']}/bridge/{bridge_id}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Bridge volume 请求失败 [id={bridge_id}]: {e}")
            return {}

    def fetch_chain_flows(self, chain: str) -> dict:
        """获取某链的跨链资金流向。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['bridges']}/bridgevolume/{chain}",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Chain flows 请求失败 [{chain}]: {e}")
            return {}

    def fetch_chain_transactions(self, chain: str, limit: int = 50) -> list[dict]:
        """获取某链的近期跨链交易。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['bridges']}/transactions/{chain}",
                params={"limit": limit},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Chain transactions 请求失败 [{chain}]: {e}")
            return []

    def close(self):
        self._http.close()
