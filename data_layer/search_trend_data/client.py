"""search_trend_data 客户端（基于 pytrends）。"""

from loguru import logger


class SearchTrendClient:
    """Google Trends 搜索趋势数据客户端。

    使用 pytrends 库获取加密货币相关关键词热度。
    """

    DEFAULT_KEYWORDS = ["bitcoin", "ethereum", "crypto", "solana", "defi"]

    def __init__(self):
        self._pytrends = None

    def _get_pytrends(self):
        """懒加载 TrendReq，避免初始化时网络异常导致进程崩溃。"""
        if self._pytrends is None:
            from pytrends.request import TrendReq
            self._pytrends = TrendReq(hl='en-US', tz=0, timeout=(5, 10))
        return self._pytrends

    def fetch_crypto_trends(self) -> dict:
        """获取默认加密关键词的兴趣度时间序列。"""
        try:
            pt = self._get_pytrends()
            pt.build_payload(
                self.DEFAULT_KEYWORDS,
                cat=0,
                timeframe="now 7-d",
                geo="",
            )
            df = pt.interest_over_time()
            if df.empty:
                return {}
            # 去除 isPartial 列
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            return df.to_dict()
        except Exception as e:
            logger.warning(f"Google Trends crypto 请求失败: {e}")
            return {}

    def fetch_keyword_interest(self, keywords: list[str]) -> dict:
        """获取指定关键词的当前兴趣度评分。"""
        try:
            pt = self._get_pytrends()
            pt.build_payload(
                keywords[:5],  # pytrends 限制最多5个关键词
                cat=0,
                timeframe="now 1-d",
                geo="",
            )
            df = pt.interest_over_time()
            if df.empty:
                return {}
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            # 返回最后一行作为当前兴趣度
            latest = df.iloc[-1]
            return {kw: int(latest.get(kw, 0)) for kw in keywords if kw in df.columns}
        except Exception as e:
            logger.warning(f"Google Trends keyword interest 请求失败: {e}")
            return {}

    def fetch_related_queries(self, keyword: str) -> dict:
        """获取关键词的相关查询。"""
        try:
            pt = self._get_pytrends()
            pt.build_payload(
                [keyword],
                cat=0,
                timeframe="now 7-d",
                geo="",
            )
            related = pt.related_queries()
            return related.get(keyword, {})
        except Exception as e:
            logger.warning(f"Google Trends related queries 请求失败 [{keyword}]: {e}")
            return

    def close(self):
        """无连接需关闭。"""
        pass
