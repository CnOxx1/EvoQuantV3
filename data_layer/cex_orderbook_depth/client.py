"""cex_orderbook_depth HTTP 客户端。"""

import httpx
from loguru import logger


class CexOrderbookDepthClient:
    """CEX 深度盘口数据 API 客户端。

    数据源：
    - Binance REST API (免费)
    - OKX REST API (免费)
    - Bybit REST API (免费)
    """

    EXCHANGE_URLS = {
        "binance": "https://api.binance.com/api/v3/depth",
        "okx": "https://www.okx.com/api/v5/market/books",
        "bybit": "https://api.bybit.com/v5/market/orderbook",
    }

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    # ─── Full Depth ───────────────────────────────────────────────────────

    def fetch_full_depth(
        self, symbol: str, exchange: str = "binance", limit: int = 5000
    ) -> dict:
        """获取指定交易所的完整深度盘口数据（最多5000档）。"""
        if exchange == "binance":
            return self._fetch_binance_depth(symbol, limit)
        elif exchange == "okx":
            return self._fetch_okx_depth(symbol, limit)
        elif exchange == "bybit":
            return self._fetch_bybit_depth(symbol, limit)
        else:
            logger.warning(f"不支持的交易所: {exchange}")
            return {}

    def _fetch_binance_depth(self, symbol: str, limit: int) -> dict:
        """从 Binance 获取深度数据。"""
        try:
            resp = self._http.get(
                self.EXCHANGE_URLS["binance"],
                params={"symbol": symbol, "limit": min(limit, 5000)},
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Binance depth 请求失败 ({symbol}): {e}")
            return {}

    def _fetch_okx_depth(self, symbol: str, limit: int) -> dict:
        """从 OKX 获取深度数据。"""
        try:
            # OKX 使用 BTC-USDT 格式
            inst_id = symbol.replace("USDT", "-USDT").replace("BTC-", "BTC-")
            if "-" not in inst_id:
                inst_id = f"{symbol[:-4]}-{symbol[-4:]}" if len(symbol) > 4 else symbol
            resp = self._http.get(
                self.EXCHANGE_URLS["okx"],
                params={"instId": inst_id, "sz": str(min(limit, 400))},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                books = data["data"]
                if books and len(books) > 0:
                    return books[0]
            return {}
        except Exception as e:
            logger.warning(f"OKX depth 请求失败 ({symbol}): {e}")
            return {}

    def _fetch_bybit_depth(self, symbol: str, limit: int) -> dict:
        """从 Bybit 获取深度数据。"""
        try:
            resp = self._http.get(
                self.EXCHANGE_URLS["bybit"],
                params={
                    "category": "spot",
                    "symbol": symbol,
                    "limit": str(min(limit, 200)),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                result = data.get("result", {})
                return result if isinstance(result, dict) else {}
            return {}
        except Exception as e:
            logger.warning(f"Bybit depth 请求失败 ({symbol}): {e}")
            return {}

    def close(self):
        self._http.close()
