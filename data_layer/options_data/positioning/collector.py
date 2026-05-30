from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class PositioningCollector(OptionsCollectorBase):
    """期权持仓结构采集器。"""

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

    @staticmethod
    def _first_number(row: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = row.get(key)
            if value is None or value == "":
                continue
            return float(value)
        return None

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        source = load_options_sources(
            source_names=["positioning"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["positioning"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_positioning_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            call_oi_30d = self._first_number(
                row,
                (
                    "call_open_interest_notional_30d",
                    "call_open_interest_notional",
                    "call_oi_notional_30d",
                    "call_oi_notional",
                ),
            )
            put_oi_30d = self._first_number(
                row,
                (
                    "put_open_interest_notional_30d",
                    "put_open_interest_notional",
                    "put_oi_notional_30d",
                    "put_oi_notional",
                ),
            )
            total_oi_30d = self._first_number(
                row,
                (
                    "total_open_interest_notional_30d",
                    "total_open_interest_notional",
                ),
            )
            if total_oi_30d is None and call_oi_30d is not None and put_oi_30d is not None:
                total_oi_30d = call_oi_30d + put_oi_30d

            total_oi_all = self._first_number(
                row,
                (
                    "total_open_interest_notional_all",
                    "aggregate_open_interest_notional",
                    "total_open_interest_notional_global",
                ),
            ) or total_oi_30d
            near_expiry_oi_notional = self._first_number(
                row,
                ("near_expiry_open_interest_notional",),
            )
            largest_expiry_oi_notional = self._first_number(
                row,
                ("largest_expiry_open_interest_notional",),
            )

            put_call_oi_ratio_30d = self._first_number(row, ("put_call_oi_ratio_30d",))
            if put_call_oi_ratio_30d is None and put_oi_30d is not None and (call_oi_30d or 0.0) > 0.0:
                put_call_oi_ratio_30d = put_oi_30d / call_oi_30d

            call_oi_share_30d = self._first_number(row, ("call_oi_share_30d",))
            if call_oi_share_30d is None and call_oi_30d is not None and (total_oi_30d or 0.0) > 0.0:
                call_oi_share_30d = call_oi_30d / total_oi_30d

            near_expiry_oi_share = self._first_number(row, ("near_expiry_oi_share",))
            if near_expiry_oi_share is None and near_expiry_oi_notional is not None and (total_oi_all or 0.0) > 0.0:
                near_expiry_oi_share = near_expiry_oi_notional / total_oi_all

            largest_expiry_oi_share = self._first_number(row, ("largest_expiry_oi_share",))
            if largest_expiry_oi_share is None and largest_expiry_oi_notional is not None and (total_oi_all or 0.0) > 0.0:
                largest_expiry_oi_share = largest_expiry_oi_notional / total_oi_all

            factor_rows = [
                (
                    "options_put_call_oi_ratio_30d",
                    put_call_oi_ratio_30d,
                    {"tenor": "30d", "metric": "put_call_ratio"},
                ),
                (
                    "options_call_oi_share_30d",
                    call_oi_share_30d,
                    {"tenor": "30d", "metric": "call_share"},
                ),
                (
                    "options_total_oi_notional_30d",
                    total_oi_30d,
                    {"tenor": "30d", "metric": "total_oi_notional"},
                ),
                (
                    "options_near_expiry_oi_share",
                    near_expiry_oi_share,
                    {"scope": "all_expiries", "metric": "near_expiry_share"},
                ),
                (
                    "options_largest_expiry_oi_share",
                    largest_expiry_oi_share,
                    {"scope": "all_expiries", "metric": "largest_expiry_share"},
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
                            row.get("source_symbol") or f"{str(row['entity_key']).upper()}-OPTIONS-OI"
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
