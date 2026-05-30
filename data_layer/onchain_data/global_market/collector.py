"""全球市场数据采集器 — CoinGecko Global API (免费，无需 API key)。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class GlobalMarketCollector:
    """全球加密市场数据采集器。

    数据源: CoinGecko Global API (免费，无需 API key)
    端点: https://api.coingecko.com/api/v3/global
    """

    COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

    FACTOR_FIELDS = {
        "total_market_cap": ("total_market_cap", "usd"),
        "btc_dominance": ("market_cap_percentage", "btc"),
        "market_cap_change_24h": ("market_cap_change_percentage_24h_usd", None),
        "total_volume_24h": ("total_volume", "usd"),
    }

    def __init__(self, client: OnchainDataClient):
        self.client = client

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OnchainTimeSeriesPoint]:
        factors = {
            f.factor_id: f
            for f in load_onchain_factors(
                source_names=["global_market"], enabled_only=False
            )
        }
        if not factors:
            return []

        try:
            payload = self.client._fetch_json(self.COINGECKO_GLOBAL_URL)
        except Exception as exc:
            logger.warning(f"CoinGecko Global 数据获取失败: {exc}")
            return []

        if not isinstance(payload, dict):
            return []

        data = payload.get("data") or {}
        if not data:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        points: list[OnchainTimeSeriesPoint] = []

        values = {
            "total_market_cap": float(
                (data.get("total_market_cap") or {}).get("usd", 0)
            ),
            "btc_dominance": float(
                (data.get("market_cap_percentage") or {}).get("btc", 0)
            ),
            "market_cap_change_24h": float(
                data.get("market_cap_change_percentage_24h_usd", 0)
            ),
            "total_volume_24h": float(
                (data.get("total_volume") or {}).get("usd", 0)
            ),
        }

        units = {
            "total_market_cap": "usd",
            "btc_dominance": "percent",
            "market_cap_change_24h": "percent",
            "total_volume_24h": "usd",
        }

        for factor_id, value in values.items():
            factor = factors.get(factor_id)
            if not factor or value == 0:
                continue
            points.append(OnchainTimeSeriesPoint(
                factor_id=factor_id,
                category=factor.category,
                factor_type=factor.factor_type,
                entity_type="market",
                entity_key="CRYPTO",
                interval=interval or "1h",
                observation_time=now,
                value=value,
                unit=units[factor_id],
                quality_flag="ok",
                dimensions_json={},
                config_version=factor.config_version,
                source_name="global_market",
                source_symbol="coingecko",
                raw_payload_json=dump_json(values),
            ))

        return points
