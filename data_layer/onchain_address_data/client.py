"""链上地址行为数据 HTTP 客户端。"""

import os

import httpx
from loguru import logger


class OnchainAddressClient:
    """链上地址数据 API 客户端。

    数据源：
    - Arkham Intelligence（地址画像、资金流向、巨鲸预警）
    - Etherscan（交易列表、代币转账）
    """

    BASE_URLS = {
        "arkham": "https://api.arkhamintelligence.com/v1",
        "etherscan": "https://api.etherscan.io/api",
    }

    def __init__(self, arkham_key: str = "", etherscan_key: str = ""):
        self.arkham_key = arkham_key or os.environ.get("ARKHAM_API_KEY", "")
        self.etherscan_key = etherscan_key or os.environ.get("ETHERSCAN_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_arkham_entity(self, address: str) -> dict:
        """从 Arkham 获取地址实体/标签信息。"""
        if not self.arkham_key:
            logger.debug("Arkham API key 未配置，跳过")
            return {}
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['arkham']}/intelligence/address/{address}",
                headers={"API-Key": self.arkham_key},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Arkham entity 请求失败: {e}")
            return {}

    def fetch_public_label(self, address: str, chain: str = "ethereum") -> dict:
        """获取可审计的公开地址标签，不要求 Arkham 等商业密钥。"""
        if chain not in {"bitcoin", "ethereum", "tron"}:
            logger.warning("CryptoLabel 不支持链: {}", chain)
            return {}
        try:
            resp = self._http.get(f"https://cryptolabel.io/api/v1/address/{chain}/{address}")
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning(f"CryptoLabel 标签请求失败: {e}")
            return {}

        entity = payload.get("entity") or {}
        labels = payload.get("labels") or []
        label = next((item.get("type", "") for item in labels if item.get("type")), "")
        entity_name = entity.get("name", "")
        category = entity.get("category", "")
        if not (label or entity_name or category):
            return {}
        return {
            "label": label,
            "entity": entity_name,
            "category": category,
            "first_seen": "",
            "last_active": "",
            "source": "cryptolabel_public",
        }

    def fetch_arkham_transfers(self, address: str, limit: int = 50) -> list[dict]:
        """从 Arkham 获取地址资金转账记录。"""
        if not self.arkham_key:
            logger.debug("Arkham API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['arkham']}/intelligence/transfers",
                params={"address": address, "limit": limit},
                headers={"API-Key": self.arkham_key},
            )
            resp.raise_for_status()
            return resp.json().get("transfers", [])
        except Exception as e:
            logger.warning(f"Arkham transfers 请求失败: {e}")
            return []

    def fetch_arkham_whale_alerts(self, min_usd: int = 1_000_000) -> list[dict]:
        """从 Arkham 获取巨鲸预警事件。"""
        if not self.arkham_key:
            logger.debug("Arkham API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['arkham']}/intelligence/alerts",
                params={"min_usd": min_usd},
                headers={"API-Key": self.arkham_key},
            )
            resp.raise_for_status()
            return resp.json().get("alerts", [])
        except Exception as e:
            logger.warning(f"Arkham whale alerts 请求失败: {e}")
            return []

    def fetch_etherscan_txlist(self, address: str, startblock: int = 0) -> list[dict]:
        """从 Etherscan 获取地址普通交易列表。"""
        if not self.etherscan_key:
            logger.debug("Etherscan API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                self.BASE_URLS["etherscan"],
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": startblock,
                    "endblock": 99999999,
                    "sort": "desc",
                    "apikey": self.etherscan_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "1":
                return data.get("result", [])
            return []
        except Exception as e:
            logger.warning(f"Etherscan txlist 请求失败: {e}")
            return []

    def fetch_etherscan_token_transfers(self, address: str) -> list[dict]:
        """从 Etherscan 获取地址 ERC-20 代币转账记录。"""
        if not self.etherscan_key:
            logger.debug("Etherscan API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                self.BASE_URLS["etherscan"],
                params={
                    "module": "account",
                    "action": "tokentx",
                    "address": address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "sort": "desc",
                    "apikey": self.etherscan_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "1":
                return data.get("result", [])
            return []
        except Exception as e:
            logger.warning(f"Etherscan token transfers 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
