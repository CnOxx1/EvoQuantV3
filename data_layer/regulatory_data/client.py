"""regulatory_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class RegulatoryDataClient:
    """监管数据 API 客户端。

    数据源：
    - CryptoCompare News API (监管类新闻过滤)
    - SEC EDGAR RSS (美国 SEC 公告)
    - 自定义 RSS 聚合 (各国监管机构公告)
    """

    BASE_URLS = {
        "cryptocompare": "https://min-api.cryptocompare.com/data/v2/news/",
        "sec_rss": "https://www.sec.gov/cgi-bin/browse-edgar",
        "sec_submissions": "https://efts.sec.gov/LATEST/search-index",
    }

    # 监管关键词
    REGULATORY_KEYWORDS = [
        "SEC", "CFTC", "regulation", "enforcement", "ETF",
        "compliance", "ban", "license", "framework", "legislation",
        "MiCA", "stablecoin regulation", "crypto regulation",
        "sanctions", "AML", "KYC",
    ]

    def __init__(self, cryptocompare_key: str = ""):
        self.cryptocompare_key = cryptocompare_key or os.environ.get("CRYPTOCOMPARE_API_KEY", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_regulatory_news(self, categories: str = "Regulation") -> list[dict]:
        """从 CryptoCompare 获取监管类新闻。"""
        try:
            params = {"categories": categories, "lang": "EN"}
            if self.cryptocompare_key:
                params["api_key"] = self.cryptocompare_key
            resp = self._http.get(self.BASE_URLS["cryptocompare"], params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Data", [])
        except Exception as e:
            logger.warning(f"CryptoCompare regulatory news 请求失败: {e}")
            return []

    def fetch_sec_filings(self, search_term: str = "crypto", form_type: str = "") -> list[dict]:
        """从 SEC EDGAR 搜索相关文件。"""
        try:
            params = {
                "q": search_term,
                "dateRange": "custom",
                "startdt": (datetime.now(timezone.utc)).strftime("%Y-%m-%d"),
                "forms": form_type,
            }
            resp = self._http.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": search_term, "dateRange": "custom"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.warning(f"SEC EDGAR 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
