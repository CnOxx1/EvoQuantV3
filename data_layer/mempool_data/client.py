"""mempool_data HTTP 客户端。"""

import httpx
from loguru import logger


class MempoolDataClient:
    """比特币内存池数据 API 客户端。

    数据源：mempool.space (免费公开 API)
    """

    BASE_URL = "https://mempool.space/api"

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_mempool_stats(self) -> dict:
        """获取内存池统计信息（待确认交易数、虚拟大小等）。"""
        try:
            resp = self._http.get(f"{self.BASE_URL}/mempool")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"mempool.space /mempool 请求失败: {e}")
            return {}

    def fetch_recommended_fees(self) -> dict:
        """获取推荐费率（fastest, halfHour, hour, economy）。"""
        try:
            resp = self._http.get(f"{self.BASE_URL}/v1/fees/recommended")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"mempool.space /v1/fees/recommended 请求失败: {e}")
            return {}

    def fetch_pending_large_txs(self, min_value_btc: float = 10) -> list[dict]:
        """获取内存池中的大额待确认交易。

        从 /mempool/recent 获取最近交易，筛选价值 >= min_value_btc 的交易。
        """
        try:
            resp = self._http.get(f"{self.BASE_URL}/mempool/recent")
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return []
            # 筛选大额交易 (value 单位为 satoshi，转换为 BTC)
            min_value_sat = min_value_btc * 1e8
            large_txs = []
            for tx in data:
                value = tx.get("value", 0)
                if value >= min_value_sat:
                    large_txs.append(tx)
            return large_txs
        except Exception as e:
            logger.warning(f"mempool.space /mempool/recent 请求失败: {e}")
            return []

    def close(self):
        self._http.close()
