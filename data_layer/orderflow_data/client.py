"""orderflow_data HTTP/WebSocket 客户端。"""

import os
import time
from datetime import datetime, timezone

import httpx
from loguru import logger


class OrderflowClient:
    """订单流数据客户端。

    通过交易所 REST API 获取近期逐笔成交（aggTrades）。
    生产环境建议使用 WebSocket 实时流，此处用 REST 轮询作为基础实现。
    """

    ENDPOINTS = {
        "binance": "https://fapi.binance.com/fapi/v1/aggTrades",
        "bybit": "https://api.bybit.com/v5/market/recent-trade",
        "okx": "https://www.okx.com/api/v5/market/trades",
    }

    # 大单阈值（USD）
    LARGE_TRADE_THRESHOLD = 100_000

    def __init__(self):
        self._http = httpx.Client(timeout=15, follow_redirects=True)

    def fetch_recent_trades_binance(self, symbol: str, limit: int = 1000) -> list[dict]:
        """从 Binance Futures 获取近期聚合成交。"""
        try:
            resp = self._http.get(
                self.ENDPOINTS["binance"],
                params={"symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            trades = resp.json()
            return [
                {
                    "trade_id": str(t["a"]),
                    "price": float(t["p"]),
                    "quantity": float(t["q"]),
                    "time": datetime.fromtimestamp(t["T"] / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                    "is_buyer_maker": t["m"],
                }
                for t in trades
            ]
        except Exception as e:
            logger.warning(f"Binance aggTrades 请求失败 [{symbol}]: {e}")
            return []

    def fetch_recent_trades_bybit(self, symbol: str, limit: int = 1000) -> list[dict]:
        """从 Bybit 获取近期成交。"""
        try:
            resp = self._http.get(
                self.ENDPOINTS["bybit"],
                params={"category": "linear", "symbol": symbol, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            trades = data.get("result", {}).get("list", [])
            return [
                {
                    "trade_id": t.get("execId", ""),
                    "price": float(t.get("price", 0)),
                    "quantity": float(t.get("size", 0)),
                    "time": datetime.fromtimestamp(
                        int(t.get("time", 0)) / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S"),
                    "is_buyer_maker": t.get("side", "").lower() == "sell",
                }
                for t in trades
            ]
        except Exception as e:
            logger.warning(f"Bybit trades 请求失败 [{symbol}]: {e}")
            return []

    def fetch_recent_trades_okx(self, inst_id: str, limit: int = 100) -> list[dict]:
        """从 OKX 获取近期成交。"""
        try:
            resp = self._http.get(
                self.ENDPOINTS["okx"],
                params={"instId": inst_id, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            trades = data.get("data", [])
            return [
                {
                    "trade_id": t.get("tradeId", ""),
                    "price": float(t.get("px", 0)),
                    "quantity": float(t.get("sz", 0)),
                    "time": datetime.fromtimestamp(
                        int(t.get("ts", 0)) / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S"),
                    "is_buyer_maker": t.get("side", "").lower() == "sell",
                }
                for t in trades
            ]
        except Exception as e:
            logger.warning(f"OKX trades 请求失败 [{inst_id}]: {e}")
            return []

    def close(self):
        self._http.close()
