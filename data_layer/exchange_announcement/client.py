"""exchange_announcement HTTP 客户端。"""

import httpx
from loguru import logger


class ExchangeAnnouncementClient:
    """交易所公告数据客户端。

    数据源：
    - Binance 公告 API
    - OKX 公告 API
    - Bybit 公告 API
    """

    BINANCE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    OKX_URL = "https://www.okx.com/api/v5/support/announcements"
    BYBIT_URL = "https://api.bybit.com/v5/announcements/index"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_binance_announcements(self) -> list[dict]:
        """获取 Binance 最新公告。"""
        try:
            resp = self._http.post(
                self.BINANCE_URL,
                json={
                    "type": 1,
                    "pageNo": 1,
                    "pageSize": 30,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            catalogs = data.get("data", {}).get("catalogs", [])
            articles = []
            for catalog in catalogs:
                for article in catalog.get("articles", []):
                    article["_catalog"] = catalog.get("catalogName", "")
                    articles.append(article)
            return articles
        except Exception as e:
            logger.warning(f"Binance announcements 请求失败: {e}")
            return []

    def fetch_okx_announcements(self) -> list[dict]:
        """获取 OKX 最新公告。"""
        try:
            resp = self._http.get(
                self.OKX_URL,
                params={"page": "1", "limit": "30"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"OKX announcements 请求失败: {e}")
            return []

    def fetch_bybit_announcements(self) -> list[dict]:
        """获取 Bybit 最新公告。"""
        try:
            resp = self._http.get(
                self.BYBIT_URL,
                params={"locale": "en-US", "limit": "30"},
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", {})
            return result.get("list", [])
        except Exception as e:
            logger.warning(f"Bybit announcements 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
