"""token_unlock_realtime HTTP 客户端。"""

import httpx
from loguru import logger


class TokenUnlockClient:
    """TokenUnlocks API 客户端。

    数据源：
    - TokenUnlocks API (代币解锁时间表)
    """

    BASE_URL = "https://api.tokenunlocks.app"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Upcoming Unlocks ─────────────────────────────────────────────────

    def fetch_upcoming_unlocks(self, days: int = 30) -> list[dict]:
        """获取未来 N 天内即将发生的代币解锁事件。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/api/v1/unlocks/upcoming",
                params={"days": days, "limit": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"TokenUnlocks upcoming 请求失败: {e}")
            return []

    # ─── Unlock History ───────────────────────────────────────────────────

    def fetch_unlock_history(self, token: str) -> list[dict]:
        """获取指定代币的历史解锁事件。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URL}/api/v1/unlocks/history",
                params={"token": token, "limit": 50},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("data", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"TokenUnlocks history 请求失败 ({token}): {e}")
            return []

    def close(self):
        self._http.close()
