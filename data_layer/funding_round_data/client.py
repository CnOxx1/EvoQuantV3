"""funding_round_data HTTP 客户端。"""

import httpx
from loguru import logger


class FundingRoundDataClient:
    """融资轮次数据 API 客户端。

    数据源：DefiLlama raises endpoint (免费)
    """

    BASE_URL = "https://api.llama.fi"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_recent_rounds(self, days: int = 30) -> list[dict]:
        """获取最近的融资轮次数据。"""
        try:
            resp = self._http.get(f"{self.BASE_URL}/raises")
            resp.raise_for_status()
            data = resp.json()
            raises = data.get("raises", [])
            if not isinstance(raises, list):
                return []
            # 按时间过滤最近 N 天
            from datetime import datetime, timezone, timedelta
            cutoff_ts = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).timestamp()
            recent = [
                r for r in raises
                if (r.get("date") or 0) >= cutoff_ts
            ]
            return recent
        except Exception as e:
            logger.warning(f"DefiLlama raises 请求失败: {e}")
            return []

    def fetch_investor_activity(self) -> list[dict]:
        """获取所有融资数据用于聚合投资者活动。"""
        try:
            resp = self._http.get(f"{self.BASE_URL}/raises")
            resp.raise_for_status()
            data = resp.json()
            raises = data.get("raises", [])
            return raises if isinstance(raises, list) else []
        except Exception as e:
            logger.warning(f"DefiLlama raises (investor) 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
