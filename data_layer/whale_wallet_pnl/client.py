"""whale_wallet_pnl HTTP 客户端。"""

import httpx
from loguru import logger


class WhaleWalletPnlClient:
    """巨鲸钱包 PnL 追踪 API 客户端。

    数据源：
    - DeBank Pro OpenAPI (需要 API Key)
    """

    BASE_URL = "https://pro-openapi.debank.com"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        headers = {}
        if api_key:
            headers["AccessKey"] = api_key
        self._http = httpx.Client(timeout=30, follow_redirects=True, headers=headers)

    # ─── Whale Portfolio ──────────────────────────────────────────────────

    def fetch_whale_portfolio(self, address: str) -> dict:
        """获取指定巨鲸钱包的投资组合数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/v1/user/total_balance",
                params={"id": address},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"巨鲸钱包组合请求失败 ({address[:10]}...): {e}")
            return {}

    # ─── Tracked Wallets ──────────────────────────────────────────────────

    def fetch_tracked_wallets(self) -> list[dict]:
        """获取追踪的巨鲸钱包列表。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/v1/user/list",
                params={"limit": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"巨鲸钱包列表请求失败: {e}")
            return []

    # ─── PnL History ──────────────────────────────────────────────────────

    def fetch_pnl_history(self, address: str) -> list[dict]:
        """获取指定巨鲸钱包的 PnL 历史数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/v1/user/total_net_curve",
                params={"id": address},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"巨鲸钱包 PnL 历史请求失败 ({address[:10]}...): {e}")
            return []

    def close(self):
        self._http.close()
