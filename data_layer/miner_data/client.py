"""miner_data HTTP 客户端。"""

import httpx
from loguru import logger


class MinerDataClient:
    """矿工数据 API 客户端。

    数据源：
    - mempool.space (Mining API)
    - Blockchain.com (Query API)
    """

    BASE_URLS = {
        "mempool": "https://mempool.space/api",
        "blockchain": "https://blockchain.info",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Mining Stats ──────────────────────────────────────────────────────

    def fetch_mining_stats(self) -> dict:
        """获取当前挖矿统计数据（算力、难度、区块奖励、收入）。"""
        stats = {}

        # mempool.space: 3天算力与难度
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            stats["hashrate_3d"] = data
        except Exception as e:
            logger.warning(f"mempool hashrate/3d 请求失败: {e}")
            stats["hashrate_3d"] = {}

        # mempool.space: 难度调整
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/difficulty-adjustments",
            )
            resp.raise_for_status()
            data = resp.json()
            stats["difficulty_adjustments"] = data
        except Exception as e:
            logger.warning(f"mempool difficulty-adjustments 请求失败: {e}")
            stats["difficulty_adjustments"] = []

        # blockchain.info: 算力
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/q/hashrate",
            )
            resp.raise_for_status()
            stats["hashrate"] = float(resp.text.strip())
        except Exception as e:
            logger.warning(f"blockchain hashrate 请求失败: {e}")
            stats["hashrate"] = 0.0

        # blockchain.info: 区块奖励
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/q/bcperblock",
            )
            resp.raise_for_status()
            # 返回值单位为 satoshi，转换为 BTC
            stats["block_reward"] = float(resp.text.strip()) / 1e8
        except Exception as e:
            logger.warning(f"blockchain bcperblock 请求失败: {e}")
            stats["block_reward"] = 0.0

        # blockchain.info: 矿工收入
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/q/miners-revenue",
            )
            resp.raise_for_status()
            stats["miners_revenue"] = float(resp.text.strip())
        except Exception as e:
            logger.warning(f"blockchain miners-revenue 请求失败: {e}")
            stats["miners_revenue"] = 0.0

        # blockchain.info: 难度
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/q/getdifficulty",
            )
            resp.raise_for_status()
            stats["difficulty"] = float(resp.text.strip())
        except Exception as e:
            logger.warning(f"blockchain getdifficulty 请求失败: {e}")
            stats["difficulty"] = 0.0

        return stats

    # ─── Miner Outflows ───────────────────────────────────────────────────

    def fetch_miner_outflows(self) -> dict:
        """获取矿工流出数据（通过 mempool.space 矿池统计推算）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            # 使用算力变化作为矿工压力代理指标
            return data
        except Exception as e:
            logger.warning(f"mempool miner outflows 请求失败: {e}")
            return {}

    # ─── Hashrate History ─────────────────────────────────────────────────

    def fetch_hashrate_history(self) -> list[dict]:
        """获取算力历史数据（mempool.space 3天数据）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/3d",
            )
            resp.raise_for_status()
            data = resp.json()
            hashrates = data.get("hashrates", [])
            return hashrates if isinstance(hashrates, list) else []
        except Exception as e:
            logger.warning(f"mempool hashrate history 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
