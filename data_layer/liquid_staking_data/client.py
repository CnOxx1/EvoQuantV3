"""liquid_staking_data HTTP 客户端。"""

import httpx
from loguru import logger


class LiquidStakingDataClient:
    """流动性质押数据 API 客户端。

    数据源：
    - DefiLlama (Lido / Rocket Pool TVL)
    - Beaconchain (验证者队列)
    - EigenLayer Explorer (再质押 TVL)
    """

    BASE_URLS = {
        "defillama": "https://api.llama.fi",
        "beaconchain": "https://beaconcha.in/api/v1",
        "eigenlayer": "https://api.eigenexplorer.com",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── DefiLlama - Lido ──────────────────────────────────────────────

    def fetch_lido_stats(self) -> dict:
        """从 DefiLlama 获取 Lido 协议统计数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['defillama']}/protocol/lido",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama Lido 请求失败: {e}")
            return {}

    # ─── DefiLlama - Rocket Pool ───────────────────────────────────────

    def fetch_rocketpool_stats(self) -> dict:
        """从 DefiLlama 获取 Rocket Pool 协议统计数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['defillama']}/protocol/rocket-pool",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama Rocket Pool 请求失败: {e}")
            return {}

    # ─── EigenLayer ────────────────────────────────────────────────────

    def fetch_eigenlayer_tvl(self) -> dict:
        """从 EigenExplorer 获取 EigenLayer 再质押 TVL 数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['eigenlayer']}/metrics/tvl",
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"EigenLayer TVL 请求失败: {e}")
            return {}

    # ─── Beaconchain ───────────────────────────────────────────────────

    def fetch_validator_queue(self) -> dict:
        """从 Beaconchain 获取验证者队列数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['beaconchain']}/validators/queue",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}) if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Beaconchain validator queue 请求失败: {e}")
            return {}

    def close(self):
        self._http.close()
