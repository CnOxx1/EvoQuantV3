"""derivatives_sentiment_data HTTP 客户端。"""

import httpx
from loguru import logger


class DerivativesSentimentDataClient:
    """衍生品情绪数据 API 客户端。

    数据源：
    - Alternative.me (Fear & Greed Index)
    - Coinglass (Long/Short, OI, Put/Call)
    """

    BASE_URLS = {
        "fear_greed": "https://api.alternative.me/fng/",
        "coinglass": "https://open-api.coinglass.com/public/v2",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Alternative.me ────────────────────────────────────────────────

    def fetch_fear_greed(self) -> dict:
        """从 Alternative.me 获取当前恐惧与贪婪指数。"""
        try:
            resp = self._http.get(
                self.BASE_URLS["fear_greed"],
                params={"limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
            if items:
                return items[0]
            return {}
        except Exception as e:
            logger.warning(f"Alternative.me Fear & Greed 请求失败: {e}")
            return {}

    # ─── Coinglass ─────────────────────────────────────────────────────

    def fetch_long_short_ratios(self) -> dict:
        """从 Coinglass 获取 BTC/ETH 多空比。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['coinglass']}/long_short",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}) if data.get("success") else {}
        except Exception as e:
            logger.warning(f"Coinglass long_short 请求失败: {e}")
            return {}

    def fetch_open_interest_global(self) -> dict:
        """从 Coinglass 获取全网未平仓合约数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['coinglass']}/open_interest",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}) if data.get("success") else {}
        except Exception as e:
            logger.warning(f"Coinglass open_interest 请求失败: {e}")
            return {}

    def fetch_put_call_ratio(self) -> dict:
        """从 Coinglass 获取看跌/看涨比率。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['coinglass']}/option/put_call_ratio",
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}) if data.get("success") else {}
        except Exception as e:
            logger.warning(f"Coinglass put_call_ratio 请求失败: {e}")
            return {}

    def close(self):
        self._http.close()
