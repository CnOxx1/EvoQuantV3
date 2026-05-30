from datetime import datetime

from data_layer.tokenomics_data.base import TokenomicsCollectorBase
from data_layer.tokenomics_data.client import TokenomicsDataClient
from data_layer.tokenomics_data.models import TokenomicsTimeSeriesPoint, dump_json
from data_layer.tokenomics_data.sources import (
    load_tokenomics_factors,
    load_tokenomics_sources,
)


class UnlockRealizationCollector(TokenomicsCollectorBase):
    """已实现解锁采集器。"""

    def __init__(self, client: TokenomicsDataClient, db):
        super().__init__(db)
        self.client = client

    @staticmethod
    def _parse_time(value) -> datetime:
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[TokenomicsTimeSeriesPoint]:
        source = load_tokenomics_sources(
            source_names=["unlock_realization"],
            enabled_only=False,
        )[0]
        factor = load_tokenomics_factors(
            source_names=["unlock_realization"],
            enabled_only=False,
        )[0]
        rows = self.client.fetch_points(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[TokenomicsTimeSeriesPoint] = []
        for row in rows:
            if row.get("realized_unlock_usd_24h") is None:
                continue
            points.append(
                TokenomicsTimeSeriesPoint(
                    factor_id=factor.factor_id,
                    category=factor.category,
                    factor_type=factor.factor_type,
                    entity_type=factor.entity_type,
                    entity_key=str(row["entity_key"]),
                    interval=str(row.get("interval") or interval or source.default_interval),
                    observation_time=self._parse_time(row["observation_time"]),
                    value=float(row["realized_unlock_usd_24h"]),
                    unit=str(row.get("unit") or factor.unit or "usd"),
                    quality_flag=str(row.get("quality_flag") or "ok"),
                    dimensions_json=dict(row.get("dimensions_json") or {}),
                    config_version=str(row.get("config_version") or factor.config_version),
                    source_name=factor.source_name,
                    source_symbol=str(row.get("source_symbol") or factor.source_symbol),
                    raw_payload_json=row.get("raw_payload_json") or dump_json(row),
                )
            )
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
