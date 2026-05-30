from datetime import datetime

from data_layer.tokenomics_data.base import TokenomicsCollectorBase
from data_layer.tokenomics_data.client import TokenomicsDataClient
from data_layer.tokenomics_data.models import (
    TokenUnlockEvent,
    TokenomicsTimeSeriesPoint,
    dump_json,
)
from data_layer.tokenomics_data.sources import (
    load_tokenomics_factors,
    load_tokenomics_sources,
)


class UnlockScheduleCollector(TokenomicsCollectorBase):
    """未来解锁压力与解锁事件采集器。"""

    FIELD_FACTOR_MAP = {
        "scheduled_unlock_usd_7d": "scheduled_unlock_usd_7d",
        "scheduled_unlock_pct_float_7d": "scheduled_unlock_pct_float_7d",
        "scheduled_unlock_usd_30d": "scheduled_unlock_usd_30d",
    }

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
            source_names=["unlock_schedule"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_tokenomics_factors(
                source_names=["unlock_schedule"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_points(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[TokenomicsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            for field_name, factor_id in self.FIELD_FACTOR_MAP.items():
                if row.get(field_name) is None:
                    continue
                factor = factors[factor_id]
                points.append(
                    TokenomicsTimeSeriesPoint(
                        factor_id=factor.factor_id,
                        category=factor.category,
                        factor_type=factor.factor_type,
                        entity_type=factor.entity_type,
                        entity_key=str(row["entity_key"]),
                        interval=str(row.get("interval") or interval or source.default_interval),
                        observation_time=observation_time,
                        value=float(row[field_name]),
                        unit=str(row.get("unit_map", {}).get(field_name) or factor.unit or ""),
                        quality_flag=str(row.get("quality_flag") or "ok"),
                        dimensions_json=dict(row.get("dimensions_json") or {}),
                        config_version=str(row.get("config_version") or factor.config_version),
                        source_name=factor.source_name,
                        source_symbol=str(row.get("source_symbol") or factor.source_symbol),
                        raw_payload_json=row.get("raw_payload_json") or dump_json(row),
                    )
                )
        return points

    def fetch_unlock_events(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[TokenUnlockEvent]:
        source = load_tokenomics_sources(
            source_names=["unlock_schedule"],
            enabled_only=False,
        )[0]
        rows = self.client.fetch_events(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        events: list[TokenUnlockEvent] = []
        for row in rows:
            if "scheduled_at" not in row:
                continue
            events.append(
                TokenUnlockEvent(
                    asset=str(row["asset"] if "asset" in row else row.get("entity_key")),
                    event_type=str(row.get("event_type") or "unlock"),
                    scheduled_at=self._parse_time(row["scheduled_at"]),
                    unlock_amount=(
                        float(row["unlock_amount"])
                        if row.get("unlock_amount") is not None
                        else None
                    ),
                    unlock_value_usd=(
                        float(row["unlock_value_usd"])
                        if row.get("unlock_value_usd") is not None
                        else None
                    ),
                    unlock_pct_float=(
                        float(row["unlock_pct_float"])
                        if row.get("unlock_pct_float") is not None
                        else None
                    ),
                    beneficiary_group=str(row.get("beneficiary_group") or "") or None,
                    status=str(row.get("status") or "scheduled"),
                    source_name=source.source_name,
                    source_url=str(row.get("source_url") or "") or None,
                    raw_payload_json=row.get("raw_payload_json") or dump_json(row),
                )
            )
        return events
