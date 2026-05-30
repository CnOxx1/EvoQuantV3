from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class GammaExposureCollector(OptionsCollectorBase):
    """期权 gamma regime 采集器。"""

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
    def _first_number(row: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = row.get(key)
            if value is None or value == "":
                continue
            return float(value)
        return None

    @staticmethod
    def _normalize_raw_payload_json(row: dict) -> str | None:
        raw_payload = row.get("raw_payload_json")
        if isinstance(raw_payload, str):
            return raw_payload
        if isinstance(raw_payload, dict | list):
            return dump_json(raw_payload)
        return dump_json(row)

    @staticmethod
    def _signed_distance_ratio(level: float | None, anchor: float | None) -> float | None:
        if level is None or anchor is None or anchor == 0:
            return None
        return level / anchor - 1.0

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        source = load_options_sources(
            source_names=["gamma_exposure"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["gamma_exposure"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_gamma_exposure_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            spot_price = self._first_number(
                row,
                ("spot_price", "underlying_spot_price", "underlying_price", "index_price"),
            )
            net_gamma_exposure = self._first_number(
                row,
                ("net_gamma_exposure", "dealer_net_gamma_exposure"),
            )
            gross_gamma_exposure = self._first_number(
                row,
                ("gross_gamma_exposure", "absolute_gamma_exposure", "total_abs_gamma_exposure"),
            )
            gamma_flip_price = self._first_number(row, ("gamma_flip_price",))
            call_gamma_wall_strike = self._first_number(
                row,
                ("call_gamma_wall_strike", "largest_call_gamma_wall_strike"),
            )
            put_gamma_wall_strike = self._first_number(
                row,
                ("put_gamma_wall_strike", "largest_put_gamma_wall_strike"),
            )
            top_gamma_strike_exposure = self._first_number(
                row,
                ("top_gamma_strike_exposure", "largest_strike_gamma_exposure"),
            )
            near_expiry_gamma_exposure = self._first_number(
                row,
                ("near_expiry_gamma_exposure", "near_expiry_total_gamma_exposure"),
            )

            net_gamma_exposure_ratio = (
                net_gamma_exposure / gross_gamma_exposure
                if net_gamma_exposure is not None
                and gross_gamma_exposure is not None
                and gross_gamma_exposure > 0
                else None
            )
            gamma_flip_distance_pct = self._signed_distance_ratio(gamma_flip_price, spot_price)
            call_gamma_wall_distance_pct = self._signed_distance_ratio(
                call_gamma_wall_strike,
                spot_price,
            )
            put_gamma_wall_distance_pct = self._signed_distance_ratio(
                put_gamma_wall_strike,
                spot_price,
            )
            top_gamma_strike_share = (
                top_gamma_strike_exposure / gross_gamma_exposure
                if top_gamma_strike_exposure is not None
                and gross_gamma_exposure is not None
                and gross_gamma_exposure > 0
                else None
            )
            near_expiry_gamma_share = (
                near_expiry_gamma_exposure / gross_gamma_exposure
                if near_expiry_gamma_exposure is not None
                and gross_gamma_exposure is not None
                and gross_gamma_exposure > 0
                else None
            )

            factor_rows = [
                (
                    "options_net_gamma_exposure",
                    net_gamma_exposure,
                    {"metric": "net_gamma_exposure"},
                ),
                (
                    "options_net_gamma_exposure_ratio",
                    net_gamma_exposure_ratio,
                    {"metric": "net_gamma_ratio"},
                ),
                (
                    "options_gamma_flip_distance_pct",
                    gamma_flip_distance_pct,
                    {"metric": "gamma_flip_distance", "reference": "spot"},
                ),
                (
                    "options_call_gamma_wall_distance_pct",
                    call_gamma_wall_distance_pct,
                    {"metric": "call_gamma_wall_distance", "reference": "spot"},
                ),
                (
                    "options_put_gamma_wall_distance_pct",
                    put_gamma_wall_distance_pct,
                    {"metric": "put_gamma_wall_distance", "reference": "spot"},
                ),
                (
                    "options_top_gamma_strike_share",
                    top_gamma_strike_share,
                    {"metric": "top_gamma_strike_share"},
                ),
                (
                    "options_near_expiry_gamma_share",
                    near_expiry_gamma_share,
                    {"metric": "near_expiry_gamma_share"},
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
                            row.get("source_symbol") or f"{str(row['entity_key']).upper()}-OPTIONS-GAMMA"
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
