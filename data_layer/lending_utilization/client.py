"""lending_utilization HTTP 客户端。"""

import httpx
from loguru import logger


class LendingUtilizationClient:
    """借贷协议利用率数据客户端。

    数据源：
    - Aave V3 Subgraph (池利用率与利率)
    - Compound V3 Subgraph (市场利用率)
    - Morpho (市场利用率)
    """

    AAVE_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/aave/protocol-v3"
    COMPOUND_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/messari/compound-v3-ethereum"
    MORPHO_API = "https://api.morpho.org/graphql"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_aave_pools(self) -> list[dict]:
        """获取 Aave V3 池利用率数据。"""
        query = """
        {
            reserves(first: 50, orderBy: totalLiquidityAsCollateral, orderDirection: desc) {
                symbol
                name
                totalATokenSupply
                totalCurrentVariableDebt
                utilizationRate
                liquidityRate
                variableBorrowRate
                optimalUtilisationRate
                variableRateSlope1
                variableRateSlope2
            }
        }
        """
        try:
            resp = self._http.post(
                self.AAVE_SUBGRAPH,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("reserves", [])
        except Exception as e:
            logger.warning(f"Aave pools 请求失败: {e}")
            return []

    def fetch_compound_markets(self) -> list[dict]:
        """获取 Compound V3 市场利用率数据。"""
        query = """
        {
            markets(first: 30, orderBy: totalValueLockedUSD, orderDirection: desc) {
                name
                inputToken { symbol }
                totalValueLockedUSD
                totalBorrowBalanceUSD
                rates {
                    rate
                    side
                    type
                }
            }
        }
        """
        try:
            resp = self._http.post(
                self.COMPOUND_SUBGRAPH,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("markets", [])
        except Exception as e:
            logger.warning(f"Compound markets 请求失败: {e}")
            return []

    def fetch_morpho_markets(self) -> list[dict]:
        """获取 Morpho 市场利用率数据。"""
        query = """
        {
            markets(first: 30, orderBy: "totalSupplyUsd", orderDirection: "desc") {
                uniqueKey
                loanAsset { symbol }
                collateralAsset { symbol }
                state {
                    totalSupplyUsd
                    totalBorrowUsd
                    utilization
                    supplyApy
                    borrowApy
                }
            }
        }
        """
        try:
            resp = self._http.post(
                self.MORPHO_API,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("markets", [])
        except Exception as e:
            logger.warning(f"Morpho markets 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
