"""流通盘与自由流通盘采集器 — 使用 CoinGecko 免费公开 API。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.tokenomics_data.base import TokenomicsCollectorBase
from data_layer.tokenomics_data.client import TokenomicsDataClient
from data_layer.tokenomics_data.models import TokenomicsTimeSeriesPoint, dump_json
from data_layer.tokenomics_data.sources import (
    load_tokenomics_factors,
    load_tokenomics_sources,
)


class CirculatingSupplyCollector(TokenomicsCollectorBase):
    """流通盘与自由流通盘采集器。

    数据源: CoinGecko 免费 API (30 calls/min, 无需 key)
    端点: https://api.coingecko.com/api/v3/coins/{id}
    """

    COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"

    # 内部 entity_key → CoinGecko coin ID
    ENTITY_COINGECKO_MAP = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "SUI": "sui",
        "DOGE": "dogecoin",
        "XRP": "ripple",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "ADA": "cardano",
        "DOT": "polkadot",
        "POL": "matic-network",
        "UNI": "uniswap",
        "ARB": "arbitrum",
        "OP": "optimism",
        "NEAR": "near",
        "ATOM": "cosmos",
        "APT": "aptos",
        "TIA": "celestia",
    }

    FIELD_FACTOR_MAP = {
        "circulating_supply": "circulating_supply",
        "float_supply": "float_supply",
        "inflation_rate_annualized": "inflation_rate_annualized",
    }

    def __init__(self, client: TokenomicsDataClient, db):
        super().__init__(db)
        self.client = client

    def _fetch_coin_data(self, coin_id: str) -> dict | None:
        """从 CoinGecko 获取单个代币数据。"""
        import time
        import urllib.request
        import json as _json

        url = self.COINGECKO_COIN_URL.format(coin_id=coin_id)
        url += "?localization=false&tickers=false&market_data=true"
        url += "&community_data=false&developer_data=false&sparkline=false"
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning(f"CoinGecko 请求失败 [{coin_id}]: {exc}")
            return None

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[TokenomicsTimeSeriesPoint]:
        import time

        factors = {
            f.factor_id: f
            for f in load_tokenomics_factors(
                source_names=["circulating_supply"], enabled_only=False
            )
        }
        if not factors:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[TokenomicsTimeSeriesPoint] = []

        targets = list(self.ENTITY_COINGECKO_MAP.items())
        if allowed:
            targets = [(k, v) for k, v in targets if k in allowed]

        for entity_key, coin_id in targets:
            data = self._fetch_coin_data(coin_id)
            if not data:
                time.sleep(2.5)
                continue

            market = data.get("market_data") or {}
            circulating = float(market.get("circulating_supply") or 0)
            total = float(market.get("total_supply") or 0)
            max_supply = market.get("max_supply")

            if circulating <= 0:
                time.sleep(2.5)
                continue

            # float_supply = circulating / total
            float_ratio = (circulating / total) if total > 0 else None

            cs_factor = factors.get("circulating_supply")
            if cs_factor:
                points.append(TokenomicsTimeSeriesPoint(
                    factor_id="circulating_supply",
                    category=cs_factor.category,
                    factor_type=cs_factor.factor_type,
                    entity_type=cs_factor.entity_type,
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=circulating,
                    unit="coins",
                    quality_flag="ok",
                    dimensions_json={"total_supply": total},
                    config_version=cs_factor.config_version,
                    source_name="circulating_supply",
                    source_symbol="coingecko",
                    raw_payload_json=dump_json({
                        "coin_id": coin_id,
                        "circulating": circulating,
                        "total": total,
                        "max_supply": max_supply,
                    }),
                ))

            fs_factor = factors.get("float_supply")
            if fs_factor and float_ratio is not None:
                points.append(TokenomicsTimeSeriesPoint(
                    factor_id="float_supply",
                    category=fs_factor.category,
                    factor_type=fs_factor.factor_type,
                    entity_type=fs_factor.entity_type,
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=float_ratio,
                    unit="ratio",
                    quality_flag="ok",
                    dimensions_json={},
                    config_version=fs_factor.config_version,
                    source_name="circulating_supply",
                    source_symbol="coingecko",
                    raw_payload_json=dump_json({
                        "coin_id": coin_id, "float_ratio": float_ratio,
                    }),
                ))

            time.sleep(2.5)  # CoinGecko 免费限制 30 calls/min

        return points

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[TokenomicsTimeSeriesPoint]:
        points = self.fetch_recent_points(
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        if points:
            self.save_to_db(points)
        return points
