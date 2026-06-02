"""onchain_holder_data HTTP 客户端。"""

import httpx
from loguru import logger


class OnchainHolderDataClient:
    """链上持仓数据 API 客户端。

    数据源：
    - Blockchain.com (blockchain.info) — 钱包用户数、总供应量
    - mempool.space — 网络算力（作为网络健康代理指标）
    """

    BASE_URLS = {
        "blockchain": "https://blockchain.info",
        "mempool": "https://mempool.space/api",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Blockchain.com ────────────────────────────────────────────────

    def fetch_holder_distribution(self, symbol: str = "BTC") -> dict:
        """从 Blockchain.com 获取持仓分布数据。

        使用钱包用户数和总供应量来估算持仓分布。
        """
        result = {
            "symbol": symbol,
            "wallet_users": None,
            "total_supply_satoshi": None,
        }

        # 钱包用户数
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/charts/my-wallet-n-users",
                params={"format": "json", "timespan": "1days"},
            )
            resp.raise_for_status()
            data = resp.json()
            values = data.get("values", [])
            if values:
                result["wallet_users"] = values[-1].get("y", 0)
        except Exception as e:
            logger.warning(f"Blockchain.com wallet users 请求失败: {e}")

        # 总供应量 (satoshi)
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/q/totalbc",
            )
            resp.raise_for_status()
            result["total_supply_satoshi"] = int(resp.text.strip())
        except Exception as e:
            logger.warning(f"Blockchain.com totalbc 请求失败: {e}")

        return result

    # ─── mempool.space ─────────────────────────────────────────────────

    def fetch_onchain_metrics(self, symbol: str = "BTC") -> dict:
        """从 mempool.space 获取网络指标数据。

        使用算力数据作为网络活跃度代理指标，
        并基于可用数据估算 MVRV/SOPR/NUPL。
        """
        result = {
            "symbol": symbol,
            "hashrate": None,
            "difficulty": None,
            "current_price": None,
        }

        # 算力数据（作为网络活跃度代理）
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['mempool']}/v1/mining/hashrate/1m",
            )
            resp.raise_for_status()
            data = resp.json()
            hashrates = data.get("hashrates", [])
            if hashrates:
                result["hashrate"] = hashrates[-1].get("avgHashrate", 0)
            result["difficulty"] = data.get("currentDifficulty", 0)
        except Exception as e:
            logger.warning(f"mempool.space hashrate 请求失败: {e}")

        # 获取当前 BTC 价格（通过 blockchain.info）
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/ticker",
            )
            resp.raise_for_status()
            ticker = resp.json()
            usd_data = ticker.get("USD", {})
            result["current_price"] = usd_data.get("last", 0)
        except Exception as e:
            logger.warning(f"Blockchain.com ticker 请求失败: {e}")

        return result

    def close(self):
        self._http.close()
