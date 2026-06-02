"""exchange_reserve_data HTTP 客户端。"""

import httpx
from loguru import logger


class ExchangeReserveDataClient:
    """交易所储备数据 API 客户端。

    数据源：
    - DefiLlama (交易所 TVL / 储备数据)
    - Blockchain.com (BTC 交易所余额)
    """

    BASE_URLS = {
        "defillama": "https://api.llama.fi",
        "blockchain": "https://blockchain.info",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── BTC Reserves ─────────────────────────────────────────────────────

    def fetch_btc_reserves(self) -> list[dict]:
        """从 Blockchain.com 获取 BTC 交易所储备数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['blockchain']}/balance",
                params={"active": "1d", "cors": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            if isinstance(data, dict):
                for address, info in data.items():
                    results.append({
                        "address": address,
                        "balance": info.get("final_balance", 0),
                    })
            return results
        except Exception as e:
            logger.warning(f"Blockchain.com BTC reserves 请求失败: {e}")
            return []

    # ─── ETH Reserves ─────────────────────────────────────────────────────

    def fetch_eth_reserves(self) -> list[dict]:
        """从 DefiLlama 获取 ETH 交易所储备数据（通过 protocols 接口）。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['defillama']}/protocols",
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            if isinstance(data, list):
                for protocol in data:
                    category = protocol.get("category", "")
                    if category and "exchange" in category.lower():
                        chains = protocol.get("chainTvls", {})
                        eth_tvl = chains.get("Ethereum", 0)
                        if eth_tvl and eth_tvl > 0:
                            results.append({
                                "exchange": protocol.get("name", "unknown"),
                                "asset": "ETH",
                                "reserve_balance": float(eth_tvl),
                            })
            return results
        except Exception as e:
            logger.warning(f"DefiLlama ETH reserves 请求失败: {e}")
            return []

    # ─── Stablecoin Reserves ──────────────────────────────────────────────

    def fetch_stablecoin_reserves(self) -> list[dict]:
        """从 DefiLlama 获取稳定币交易所储备数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['defillama']}/protocols",
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            if isinstance(data, list):
                for protocol in data:
                    category = protocol.get("category", "")
                    if category and "exchange" in category.lower():
                        # 使用总 TVL 近似稳定币储备
                        stables = protocol.get("stablesTvl", 0) or 0
                        if stables > 0:
                            results.append({
                                "exchange": protocol.get("name", "unknown"),
                                "asset": "USDT",
                                "reserve_balance": float(stables),
                            })
            return results
        except Exception as e:
            logger.warning(f"DefiLlama stablecoin reserves 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
