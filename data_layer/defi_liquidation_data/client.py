"""defi_liquidation_data HTTP 客户端。"""

import httpx
from loguru import logger


class DefiLiquidationClient:
    """DeFi 清算数据 API 客户端。

    数据源：
    - The Graph: Aave V3 Subgraph (链上清算事件)
    - The Graph: Compound V3 Subgraph (链上清算事件)
    """

    AAVE_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/aave/protocol-v3"
    COMPOUND_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/messari/compound-v3-ethereum"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_aave_liquidations(self, since_timestamp: int) -> list[dict]:
        """获取 Aave V3 清算事件。"""
        query = (
            "{ liquidationCalls(first: 100, orderBy: timestamp, "
            "orderDirection: desc, where: { timestamp_gte: %d }) { "
            "id timestamp liquidator user { id } "
            "collateralAsset { symbol } debtAsset { symbol } "
            "debtToCover liquidatedCollateralAmount "
            "transaction { id blockNumber } } }"
        ) % since_timestamp
        try:
            resp = self._http.post(
                self.AAVE_SUBGRAPH,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("liquidationCalls", [])
        except Exception as e:
            logger.warning(f"Aave V3 liquidations 请求失败: {e}")
            return []

    def fetch_compound_liquidations(self, since_timestamp: int) -> list[dict]:
        """获取 Compound V3 清算事件。"""
        query = (
            "{ liquidates(first: 100, orderBy: timestamp, "
            "orderDirection: desc, where: { timestamp_gte: %d }) { "
            "id timestamp liquidator { id } liquidatee { id } "
            "asset { symbol } market { inputToken { symbol } } "
            "amount amountUSD profitUSD "
            "transaction { id blockNumber } } }"
        ) % since_timestamp
        try:
            resp = self._http.post(
                self.COMPOUND_SUBGRAPH,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("liquidates", [])
        except Exception as e:
            logger.warning(f"Compound V3 liquidations 请求失败: {e}")
            return []

    def fetch_health_factors(self, protocol: str = "aave") -> list[dict]:
        """获取健康因子分布数据。"""
        if protocol == "aave":
            query = (
                "{ users(first: 500, "
                "where: { borrowedReservesCount_gt: 0 }, "
                "orderBy: totalCollateralUSD, orderDirection: desc) { "
                "id totalCollateralUSD totalDebtUSD healthFactor } }"
            )
            url = self.AAVE_SUBGRAPH
        else:
            query = (
                "{ accounts(first: 500, "
                "where: { openPositionCount_gt: 0 }, orderBy: id) { "
                "id openPositionCount positions { "
                "balance side asset { symbol } } } }"
            )
            url = self.COMPOUND_SUBGRAPH
        try:
            resp = self._http.post(url, json={"query": query})
            resp.raise_for_status()
            data = resp.json()
            if protocol == "aave":
                return data.get("data", {}).get("users", [])
            return data.get("data", {}).get("accounts", [])
        except Exception as e:
            logger.warning(f"Health factors 请求失败 [{protocol}]: {e}")
            return []

    def close(self):
        self._http.close()
