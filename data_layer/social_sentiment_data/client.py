"""social_sentiment_data HTTP 客户端。"""

import time
from datetime import datetime, timezone

import httpx
from loguru import logger


class SocialSentimentClient:
    """社交情绪数据 API 客户端。

    支持数据源：
    - LunarCrush (社交聚合)
    - Santiment (链上+社交)
    - Twitter API v2 (原始推文)
    """

    BASE_URLS = {
        "lunarcrush": "https://lunarcrush.com/api4/public",
        "santiment": "https://api.santiment.net/graphql",
        "twitter": "https://api.twitter.com/2",
    }

    def __init__(self, lunarcrush_key: str = "", santiment_key: str = "", twitter_bearer: str = ""):
        import os
        self.lunarcrush_key = lunarcrush_key or os.environ.get("LUNARCRUSH_API_KEY", "")
        self.santiment_key = santiment_key or os.environ.get("SANTIMENT_API_KEY", "")
        self.twitter_bearer = twitter_bearer or os.environ.get("TWITTER_BEARER_TOKEN", "")
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_lunarcrush_social(self, symbol: str, interval: str = "1d") -> list[dict]:
        """从 LunarCrush 获取社交指标。"""
        if not self.lunarcrush_key:
            logger.debug("LunarCrush API key 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['lunarcrush']}/coins/{symbol}/time-series/v2",
                params={"key": self.lunarcrush_key, "bucket": interval},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"LunarCrush 请求失败 [{symbol}]: {e}")
            return []

    def fetch_santiment_social_volume(self, slug: str, from_dt: str, to_dt: str) -> list[dict]:
        """从 Santiment 获取社交量数据。"""
        if not self.santiment_key:
            logger.debug("Santiment API key 未配置，跳过")
            return []
        query = """
        {
            getMetric(metric: "social_volume_total") {
                timeseriesData(slug: "%s", from: "%s", to: "%s", interval: "1h") {
                    datetime
                    value
                }
            }
        }
        """ % (slug, from_dt, to_dt)
        try:
            resp = self._http.post(
                self.BASE_URLS["santiment"],
                json={"query": query},
                headers={"Authorization": f"Apikey {self.santiment_key}"},
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        except Exception as e:
            logger.warning(f"Santiment 请求失败 [{slug}]: {e}")
            return []

    def fetch_santiment_sentiment(self, slug: str, from_dt: str, to_dt: str) -> list[dict]:
        """从 Santiment 获取情绪加权数据。"""
        if not self.santiment_key:
            return []
        query = """
        {
            getMetric(metric: "sentiment_volume_consumed_total") {
                timeseriesData(slug: "%s", from: "%s", to: "%s", interval: "1h") {
                    datetime
                    value
                }
            }
        }
        """ % (slug, from_dt, to_dt)
        try:
            resp = self._http.post(
                self.BASE_URLS["santiment"],
                json={"query": query},
                headers={"Authorization": f"Apikey {self.santiment_key}"},
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        except Exception as e:
            logger.warning(f"Santiment sentiment 请求失败 [{slug}]: {e}")
            return []

    def fetch_twitter_recent(self, query: str, max_results: int = 100) -> list[dict]:
        """从 Twitter API v2 搜索近期推文。"""
        if not self.twitter_bearer:
            logger.debug("Twitter Bearer Token 未配置，跳过")
            return []
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['twitter']}/tweets/search/recent",
                params={
                    "query": query,
                    "max_results": min(max_results, 100),
                    "tweet.fields": "created_at,public_metrics,author_id",
                },
                headers={"Authorization": f"Bearer {self.twitter_bearer}"},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.warning(f"Twitter 请求失败 [{query}]: {e}")
            return []

    def close(self):
        self._http.close()
