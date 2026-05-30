from datetime import datetime

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors, load_onchain_sources


class WhaleActivityCollector:
    """鲸鱼地址异动采集器。"""

    def __init__(self, client: OnchainDataClient):
        self.client = client

    @staticmethod
    def _parse_time(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("observation_time 必须是 ISO 时间字符串或 datetime")
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OnchainTimeSeriesPoint]:
        source = load_onchain_sources(
            source_names=["whale_activity"],
            enabled_only=False,
        )[0]
        factor = load_onchain_factors(
            factor_ids=["whale_transfer_count"],
            enabled_only=False,
        )[0]
        rows = self.client.fetch_points(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OnchainTimeSeriesPoint] = []
        for row in rows:
            points.append(
                OnchainTimeSeriesPoint(
                    factor_id=factor.factor_id,
                    category=factor.category,
                    factor_type=factor.factor_type,
                    entity_type=factor.entity_type,
                    entity_key=str(row["entity_key"]),
                    interval=str(row.get("interval") or interval or source.default_interval),
                    observation_time=self._parse_time(row["observation_time"]),
                    value=float(row["value"]),
                    unit=str(row.get("unit") or factor.unit or "count"),
                    quality_flag=str(row.get("quality_flag") or "ok"),
                    dimensions_json=dict(row.get("dimensions_json") or {}),
                    config_version=str(row.get("config_version") or factor.config_version),
                    source_name=factor.source_name,
                    source_symbol=str(row.get("source_symbol") or factor.source_symbol),
                    raw_payload_json=row.get("raw_payload_json") or dump_json(row),
                )
            )
        return points
