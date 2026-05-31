"""defi_protocol_data HTTP 客户端。"""

import os
from datetime import datetime, timezone

import httpx
from loguru import logger


class DefiProtocolClient:
    """DeFi 协议数据 API 客户端。

    数据源：
    - DefiLlama (TVL、DEX 交易量、协议收入)
    - Aave/Compound 公开 API (借贷利率)
    """

    BASE_URLS = {
        "defillama": "https://api.llama.fi",
        "defillama_yields": "https://yields.llama.fi",
        "defillama_dex": "https://api.llama.fi/overview/dexs",
    }

    # 追踪的主要协议
    TRACKED_PROTOCOLS = [
        "aave", "lido", "makerdao", "uniswap", "curve-dex",
        "compound", "rocket-pool", "gmx", "dydx", "raydium",
        "jupiter", "morpho", "eigenlayer", "pendle", "ethena",
    ]

    def __init__(self):
        self._http = httpx.Client(timeout=30, follow_redirects=True)

    def fetch_protocol_tvl(self, protocol: str) -> dict:
        """获取单个协议的 TVL 数据。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['defillama']}/protocol/{protocol}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama TVL 请求失败 [{protocol}]: {e}")
            return {}

    def fetch_all_protocols_tvl(self) -> list[dict]:
        """获取所有协议 TVL 概览。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['defillama']}/protocols")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama protocols 请求失败: {e}")
            return []

    def fetch_chain_tvl(self) -> list[dict]:
        """获取各链 TVL。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['defillama']}/v2/chains")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama chains 请求失败: {e}")
            return []

    def fetch_yields_pools(self) -> list[dict]:
        """获取借贷池收益率数据。"""
        try:
            resp = self._http.get(f"{self.BASE_URLS['defillama_yields']}/pools")
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            logger.warning(f"DefiLlama yields 请求失败: {e}")
            return []

    def fetch_dex_overview(self) -> dict:
        """获取 DEX 交易量概览。"""
        try:
            resp = self._http.get(self.BASE_URLS["defillama_dex"])
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama DEX 请求失败: {e}")
            return {}

    def fetch_protocol_fees(self, protocol: str) -> dict:
        """获取协议费用/收入数据。"""
        try:
            resp = self._http.get(
                f"{self.BASE_URLS['defillama']}/summary/fees/{protocol}"
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"DefiLlama fees 请求失败 [{protocol}]: {e}")
            return {}

    def close(self):
        self._http.close()
