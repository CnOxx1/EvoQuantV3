from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class RelativeValueCollector(OptionsCollectorBase):
    """期权隐含波动率相对已实现波动率采集器。"""

    def __init__(self, client: OptionsDataClient, db):
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

    @staticmethod
    def _to_float(value) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    @staticmethod
    def _normalize_raw_payload_json(row: dict) -> str | None:
        raw_payload = row.get("raw_payload_json")
        if isinstance(raw_payload, str):
            return raw_payload
        if isinstance(raw_payload, dict | list):
            return dump_json(raw_payload)
        return dump_json(row)

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        source = load_options_sources(
            source_names=["relative_value"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["relative_value"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_relative_value_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            realized_vol_7d = self._to_float(row.get("realized_vol_7d"))
            realized_vol_30d = self._to_float(row.get("realized_vol_30d"))
            atm_iv_7d = self._to_float(row.get("atm_iv_7d"))
            atm_iv_30d = self._to_float(row.get("atm_iv_30d"))
            iv_rv_spread_7d = self._to_float(row.get("iv_rv_spread_7d"))
            iv_rv_spread_30d = self._to_float(row.get("iv_rv_spread_30d"))
            if iv_rv_spread_7d is None and atm_iv_7d is not None and realized_vol_7d is not None:
                iv_rv_spread_7d = atm_iv_7d - realized_vol_7d
            if iv_rv_spread_30d is None and atm_iv_30d is not None and realized_vol_30d is not None:
                iv_rv_spread_30d = atm_iv_30d - realized_vol_30d

            factor_rows = [
                (
                    "options_realized_vol_7d",
                    realized_vol_7d,
                    {"tenor": "7d", "metric": "realized_vol"},
                ),
                (
                    "options_realized_vol_30d",
                    realized_vol_30d,
                    {"tenor": "30d", "metric": "realized_vol"},
                ),
                (
                    "options_iv_rv_spread_7d",
                    iv_rv_spread_7d,
                    {"tenor": "7d", "metric": "iv_minus_rv"},
                ),
                (
                    "options_iv_rv_spread_30d",
                    iv_rv_spread_30d,
                    {"tenor": "30d", "metric": "iv_minus_rv"},
                ),
            ]
            for factor_id, value, dimensions in factor_rows:
                if value is None:
                    continue
                factor = factors[factor_id]
                points.append(
                    OptionsTimeSeriesPoint(
                        factor_id=factor.factor_id,
                        category=factor.category,
                        factor_type=factor.factor_type,
                        entity_type=factor.entity_type,
                        entity_key=str(row["entity_key"]),
                        interval=row_interval,
                        observation_time=observation_time,
                        value=float(value),
                        unit=factor.unit or "",
                        quality_flag=str(row.get("quality_flag") or "ok"),
                        dimensions_json=dimensions,
                        config_version=str(row.get("config_version") or factor.config_version),
                        source_name=factor.source_name,
                        source_symbol=str(
                            row.get("source_symbol") or f"{str(row['entity_key']).upper()}-OPTIONS-RV"
                        ),
                        raw_payload_json=self._normalize_raw_payload_json(row),
                    )
                )
        return points

    def collect(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        points = self.fetch_recent_points(
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        if points:
            self.save_to_db(points)
        return points
