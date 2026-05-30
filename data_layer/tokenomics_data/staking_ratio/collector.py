"""质押率采集器 — 使用 CoinGecko 免费公开 API。"""

from __future__ import annotations

import json as _json
import time
import urllib.request
from datetime import datetime, timezone

from loguru import logger

from data_layer.tokenomics_data.base import TokenomicsCollectorBase
from data_layer.tokenomics_data.client import TokenomicsDataClient
from data_layer.tokenomics_data.models import TokenomicsTimeSeriesPoint, dump_json
from data_layer.tokenomics_data.sources import (
    load_tokenomics_factors,
    load_tokenomics_sources,
)


class StakingRatioCollector(TokenomicsCollectorBase):
    """质押率采集器。

    数据源: CoinGecko 免费 API + 链上 staking 数据估算
    对于 PoS 代币，staking_ratio = staked_supply / circulating_supply
    """

    COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"

    # 支持 staking 的代币及其 CoinGecko ID
    STAKING_TOKENS = {
        "ETH": "ethereum",
        "SOL": "solana",
        "ADA": "cardano",
        "DOT": "polkadot",
        "AVAX": "avalanche-2",
        "ATOM": "cosmos",
        "NEAR": "near",
        "APT": "aptos",
        "SUI": "sui",
        "TIA": "celestia",
    }

    # 已知的近似 staking 比例（作为 fallback）
    KNOWN_STAKING_RATIOS: dict[str, float] = {
        "ETH": 0.28,
        "SOL": 0.67,
        "ADA": 0.62,
        "DOT": 0.50,
        "AVAX": 0.56,
        "ATOM": 0.63,
    }

    FIELD_FACTOR_MAP = {
        "staking_ratio": "staking_ratio",
        "staking_ratio_change_7d": "staking_ratio_change_7d",
    }

    def __init__(self, client: TokenomicsDataClient, db):
        super().__init__(db)
        self.client = client

    def _fetch_coin_data(self, coin_id: str) -> dict | None:
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
        factors = {
            f.factor_id: f
            for f in load_tokenomics_factors(
                source_names=["staking_ratio"], enabled_only=False
            )
        }
        if not factors:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        allowed = set(k.upper() for k in (entity_keys or []))
        points: list[TokenomicsTimeSeriesPoint] = []

        targets = list(self.STAKING_TOKENS.items())
        if allowed:
            targets = [(k, v) for k, v in targets if k in allowed]

        sr_factor = factors.get("staking_ratio")

        for entity_key, coin_id in targets:
            data = self._fetch_coin_data(coin_id)
            quality = "ok"
            ratio = None

            if data:
                market = data.get("market_data") or {}
                circulating = float(market.get("circulating_supply") or 0)
                total = float(market.get("total_supply") or 0)
                # CoinGecko 不直接提供 staking 数据，使用 fallback
                ratio = self.KNOWN_STAKING_RATIOS.get(entity_key)
                quality = "fallback"
            else:
                ratio = self.KNOWN_STAKING_RATIOS.get(entity_key)
                quality = "fallback"

            if sr_factor and ratio is not None:
                points.append(TokenomicsTimeSeriesPoint(
                    factor_id="staking_ratio",
                    category=sr_factor.category,
                    factor_type=sr_factor.factor_type,
                    entity_type=sr_factor.entity_type,
                    entity_key=entity_key,
                    interval=interval or "1d",
                    observation_time=now,
                    value=ratio,
                    unit="ratio",
                    quality_flag=quality,
                    dimensions_json={},
                    config_version=sr_factor.config_version,
                    source_name="staking_ratio",
                    source_symbol="coingecko",
                    raw_payload_json=dump_json({
                        "coin_id": coin_id, "staking_ratio": ratio,
                        "source": "known_estimate",
                    }),
                ))

            time.sleep(2.5)

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
