"""governance_data HTTP 客户端。"""

import os

import httpx
from loguru import logger


class GovernanceDataClient:
    """DAO 治理数据 API 客户端。

    数据源：
    - Snapshot (链下治理投票)
    - Tally (链上治理投票)
    """

    BASE_URLS = {
        "snapshot": "https://hub.snapshot.org/graphql",
        "tally": "https://api.tally.xyz/query",
    }

    TRACKED_SPACES = [
        "aave.eth",
        "uniswapgovernance.eth",
        "lido-snapshot.eth",
        "compound-governance.eth",
        "arbitrumfoundation.eth",
    ]

    def __init__(self, tally_key: str = ""):
        self.tally_key = tally_key or os.environ.get("TALLY_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_snapshot_proposals(self, space: str, state: str = "active", first: int = 10) -> list[dict]:
        """从 Snapshot 获取指定空间的提案列表。"""
        query = """
        query Proposals($space: String!, $state: String!, $first: Int!) {
            proposals(
                where: { space: $space, state: $state }
                first: $first
                orderBy: "created"
                orderDirection: desc
            ) {
                id
                title
                state
                scores_total
                scores
                quorum
                start
                end
            }
        }
        """
        variables = {"space": space, "state": state, "first": first}
        try:
            data = self._query_graphql(
                self.BASE_URLS["snapshot"], query, variables=variables
            )
            return data.get("proposals", [])
        except Exception as e:
            logger.warning(f"Snapshot proposals 请求失败 ({space}): {e}")
            return []

    def fetch_snapshot_votes(self, proposal_id: str, first: int = 100) -> list[dict]:
        """从 Snapshot 获取指定提案的投票记录。"""
        query = """
        query Votes($proposal: String!, $first: Int!) {
            votes(
                where: { proposal: $proposal }
                first: $first
                orderBy: "vp"
                orderDirection: desc
            ) {
                voter
                vp
                choice
                created
            }
        }
        """
        variables = {"proposal": proposal_id, "first": first}
        try:
            data = self._query_graphql(
                self.BASE_URLS["snapshot"], query, variables=variables
            )
            return data.get("votes", [])
        except Exception as e:
            logger.warning(f"Snapshot votes 请求失败 ({proposal_id}): {e}")
            return []

    def fetch_tally_proposals(self, governor_id: str, first: int = 10) -> list[dict]:
        """从 Tally 获取链上治理提案。"""
        if not self.tally_key:
            logger.debug("Tally API key 未配置，跳过")
            return []
        query = """
        query Proposals($governorId: AccountID!, $first: Int!) {
            proposals(
                governorId: $governorId
                pagination: { limit: $first, offset: 0 }
            ) {
                id
                title
                statusChanges { type }
                voteStats { votesCount support }
                start { timestamp }
                end { timestamp }
            }
        }
        """
        variables = {"governorId": governor_id, "first": first}
        headers = {"Api-Key": self.tally_key}
        try:
            data = self._query_graphql(
                self.BASE_URLS["tally"], query, variables=variables, headers=headers
            )
            return data.get("proposals", [])
        except Exception as e:
            logger.warning(f"Tally proposals 请求失败 ({governor_id}): {e}")
            return []

    def fetch_tally_votes(self, proposal_id: str, first: int = 100) -> list[dict]:
        """从 Tally 获取链上投票记录。"""
        if not self.tally_key:
            logger.debug("Tally API key 未配置，跳过")
            return []
        query = """
        query Votes($proposalId: ID!, $first: Int!) {
            votes(
                proposalId: $proposalId
                pagination: { limit: $first, offset: 0 }
            ) {
                voter { address }
                weight
                support
                block { timestamp }
            }
        }
        """
        variables = {"proposalId": proposal_id, "first": first}
        headers = {"Api-Key": self.tally_key}
        try:
            data = self._query_graphql(
                self.BASE_URLS["tally"], query, variables=variables, headers=headers
            )
            return data.get("votes", [])
        except Exception as e:
            logger.warning(f"Tally votes 请求失败 ({proposal_id}): {e}")
            return []

    def _query_graphql(self, url: str, query: str, variables: dict = None, headers: dict = None) -> dict:
        """通用 GraphQL 查询辅助方法。"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        resp = self._http.post(url, json=payload, headers=req_headers)
        resp.raise_for_status()
        result = resp.json()
        if "errors" in result:
            logger.warning(f"GraphQL 错误: {result['errors']}")
            return {}
        return result.get("data", {})

    def close(self):
        self._http.close()
