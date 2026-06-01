"""DEX 流动性数据 HTTP 客户端。"""

import os

import httpx
from loguru import logger


class DexLiquidityClient:
    """DEX 流动性池数据客户端。

    数据源：
    - Uniswap V3 (The Graph 子图)
    - Curve Finance (The Graph 子图)
    """

    SUBGRAPH_URLS = {
        "uniswap_v3": "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3",
        "curve": "https://api.thegraph.com/subgraphs/name/curvefi/curve",
    }

    def __init__(self, graph_api_key: str = ""):
        self.graph_api_key = graph_api_key or os.environ.get("GRAPH_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_uniswap_pools(self, first: int = 50, order_by: str = "totalValueLockedUSD") -> list[dict]:
        """获取 Uniswap V3 流动性池列表（按 TVL 排序）。"""
        query = """
        query($first: Int!, $orderBy: String!) {
            pools(first: $first, orderBy: $orderBy, orderDirection: desc) {
                id
                token0 { symbol }
                token1 { symbol }
                totalValueLockedUSD
                volumeUSD
                feeTier
                createdAtTimestamp
            }
        }
        """
        variables = {"first": first, "orderBy": order_by}
        try:
            data = self._query_subgraph(self.SUBGRAPH_URLS["uniswap_v3"], query, variables)
            return data.get("data", {}).get("pools", [])
        except Exception as e:
            logger.warning(f"Uniswap V3 pools 请求失败: {e}")
            return []

    def fetch_uniswap_pool_ticks(self, pool_id: str, first: int = 100) -> list[dict]:
        """获取 Uniswap V3 池的 Tick 级别流动性分布。"""
        query = """
        query($poolId: String!, $first: Int!) {
            ticks(first: $first, where: { pool: $poolId }, orderBy: tickIdx) {
                tickIdx
                liquidityGross
                liquidityNet
                price0
                price1
            }
        }
        """
        variables = {"poolId": pool_id, "first": first}
        try:
            data = self._query_subgraph(self.SUBGRAPH_URLS["uniswap_v3"], query, variables)
            return data.get("data", {}).get("ticks", [])
        except Exception as e:
            logger.warning(f"Uniswap V3 ticks 请求失败 (pool={pool_id}): {e}")
            return []

    def fetch_uniswap_mints_burns(self, pool_id: str, first: int = 50) -> list[dict]:
        """获取 Uniswap V3 池的最近流动性添加/移除事件。"""
        query = """
        query($poolId: String!, $first: Int!) {
            mints(first: $first, where: { pool: $poolId }, orderBy: timestamp, orderDirection: desc) {
                id
                timestamp
                sender
                amountUSD
                tickLower
                tickUpper
                transaction { id }
            }
            burns(first: $first, where: { pool: $poolId }, orderBy: timestamp, orderDirection: desc) {
                id
                timestamp
                owner
                amountUSD
                tickLower
                tickUpper
                transaction { id }
            }
        }
        """
        variables = {"poolId": pool_id, "first": first}
        try:
            data = self._query_subgraph(self.SUBGRAPH_URLS["uniswap_v3"], query, variables)
            result = data.get("data", {})
            return {
                "mints": result.get("mints", []),
                "burns": result.get("burns", []),
            }
        except Exception as e:
            logger.warning(f"Uniswap V3 mints/burns 请求失败 (pool={pool_id}): {e}")
            return {"mints": [], "burns": []}

    def fetch_curve_pools(self, first: int = 50) -> list[dict]:
        """获取 Curve 流动性池列表。"""
        query = """
        query($first: Int!) {
            pools(first: $first, orderBy: totalValueLockedUSD, orderDirection: desc) {
                id
                name
                coins
                totalValueLockedUSD
                volumeUSD
                createdAtTimestamp
            }
        }
        """
        variables = {"first": first}
        try:
            data = self._query_subgraph(self.SUBGRAPH_URLS["curve"], query, variables)
            return data.get("data", {}).get("pools", [])
        except Exception as e:
            logger.warning(f"Curve pools 请求失败: {e}")
            return []

    def fetch_curve_exchanges(self, pool_id: str, first: int = 50) -> list[dict]:
        """获取 Curve 池的最近交换事件。"""
        query = """
        query($poolId: String!, $first: Int!) {
            exchanges(first: $first, where: { pool: $poolId }, orderBy: timestamp, orderDirection: desc) {
                id
                timestamp
                buyer
                tokenBought
                tokenSold
                amountBought
                amountSold
                transaction { id }
            }
        }
        """
        variables = {"poolId": pool_id, "first": first}
        try:
            data = self._query_subgraph(self.SUBGRAPH_URLS["curve"], query, variables)
            return data.get("data", {}).get("exchanges", [])
        except Exception as e:
            logger.warning(f"Curve exchanges 请求失败 (pool={pool_id}): {e}")
            return []

    def _query_subgraph(self, url: str, query: str, variables: dict = None) -> dict:
        """通用 GraphQL 子图查询辅助方法。"""
        headers = {"Content-Type": "application/json"}
        if self.graph_api_key:
            headers["Authorization"] = f"Bearer {self.graph_api_key}"

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = self._http.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def close(self):
        """关闭 HTTP 客户端。"""
        self._http.close()
