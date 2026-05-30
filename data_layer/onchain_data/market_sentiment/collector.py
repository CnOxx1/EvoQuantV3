"""市场情绪采集器 — Fear & Greed Index (alternative.me 免费 API)。"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors


class MarketSentimentCollector:
    """市场情绪采集器。

    数据源: alternative.me Fear & Greed Index (免费，无需 API key)
    端点: https://api.alternative.me/fng/?limit=1&format=json
    """

    FNG_URL = "https://api.alternative.me/fng/?limit=1&format=json"

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
                source_names=["market_sentiment"], enabled_only=False
            )
        }
        if not factors:
            return []

        try:
            payload = self.client._fetch_json(self.FNG_URL)
        except Exception as exc:
            logger.warning(f"Fear & Greed 数据获取失败: {exc}")
            return []

        if not isinstance(payload, dict):
            return []

        data_list = payload.get("data") or []
        if not data_list:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        points: list[OnchainTimeSeriesPoint] = []
        fng_factor = factors.get("fear_greed_index")

        item = data_list[0]
        value = float(item.get("value", 0))
        classification = item.get("value_classification", "")

        if fng_factor and value > 0:
            points.append(OnchainTimeSeriesPoint(
                factor_id="fear_greed_index",
                category=fng_factor.category,
                factor_type=fng_factor.factor_type,
                entity_type="market",
                entity_key="CRYPTO",
                interval=interval or "1d",
                observation_time=now,
                value=value,
                unit="index",
                quality_flag="ok",
                dimensions_json={"classification": classification},
                config_version=fng_factor.config_version,
                source_name="market_sentiment",
                source_symbol="alternative_me",
                raw_payload_json=dump_json(item),
            ))

        return points
