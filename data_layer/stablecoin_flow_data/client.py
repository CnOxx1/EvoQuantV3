"""stablecoin_flow_data HTTP 客户端。"""

import httpx
from loguru import logger


class StablecoinFlowClient:
    """稳定币流动数据 API 客户端。

    数据源：
    - DefiLlama Stablecoins API (免费，无需 API Key)
    """

    BASE_URL = "https://stablecoins.llama.fi"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Stablecoin List ──────────────────────────────────────────────────

    def fetch_stablecoin_list(self) -> list[dict]:
        """获取所有稳定币列表及基本信息。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/stablecoins",
                params={"includePrices": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("peggedAssets", [])
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"稳定币列表请求失败: {e}")
            return []

    # ─── Stablecoin History ───────────────────────────────────────────────

    def fetch_stablecoin_history(self, stablecoin_id: int) -> dict:
        """获取指定稳定币的历史 mint/burn 及供应量数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/stablecoin/{stablecoin_id}",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"稳定币历史数据请求失败 (id={stablecoin_id}): {e}")
            return {}

    # ─── Chain Distribution ───────────────────────────────────────────────

    def fetch_chain_distribution(self) -> list[dict]:
        """获取稳定币在各链上的分布数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/stablecoinchains",
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"稳定币链分布请求失败: {e}")
            return []

    def close(self):
        self._http.close()
