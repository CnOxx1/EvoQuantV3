from datetime import datetime

from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.models import OnchainTimeSeriesPoint, dump_json
from data_layer.onchain_data.sources import load_onchain_factors, load_onchain_sources


class ExchangeReserveCollector:
    """交易所储备采集器。"""

    FIELD_FACTOR_MAP = {
        "exchange_reserve_balance": "exchange_reserve_balance",
        "exchange_reserve_change_24h": "exchange_reserve_change_24h",
    }

    def __init__(self, client: OnchainDataClient):
        self.client = client

    @staticmethod
    def _parse_time(value) -> datetime:
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
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
            source_names=["exchange_reserve"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_onchain_factors(
                source_names=["exchange_reserve"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_points(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OnchainTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            for field_name, factor_id in self.FIELD_FACTOR_MAP.items():
                if row.get(field_name) is None:
                    continue
                factor = factors[factor_id]
                points.append(
                    OnchainTimeSeriesPoint(
                        factor_id=factor.factor_id,
                        category=factor.category,
                        factor_type=factor.factor_type,
                        entity_type=factor.entity_type,
                        entity_key=str(row["entity_key"]),
                        interval=str(row.get("interval") or interval or source.default_interval),
                        observation_time=observation_time,
                        value=float(row[field_name]),
                        unit=str(row.get("unit_map", {}).get(field_name) or factor.unit or "usd"),
                        quality_flag=str(row.get("quality_flag") or "ok"),
                        dimensions_json=dict(row.get("dimensions_json") or {}),
                        config_version=str(row.get("config_version") or factor.config_version),
                        source_name=factor.source_name,
                        source_symbol=str(row.get("source_symbol") or factor.source_symbol),
                        raw_payload_json=row.get("raw_payload_json") or dump_json(row),
                    )
                )
        return points
