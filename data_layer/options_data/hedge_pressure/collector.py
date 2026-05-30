from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class HedgePressureCollector(OptionsCollectorBase):
    """期权动态对冲压力采集器。"""

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
    def _ratio(value: float | None, total: float | None) -> float | None:
        if value is None or total is None or total == 0:
            return None
        return value / total

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
            source_names=["hedge_pressure"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["hedge_pressure"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_hedge_pressure_snapshots(
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
            gross_gamma = self._first_number(
                row,
                ("gross_gamma_exposure", "absolute_gamma_exposure", "total_abs_gamma_exposure"),
            )
            total_charm = self._first_number(
                row,
                ("total_charm_exposure", "absolute_charm_exposure"),
            )
            total_color = self._first_number(
                row,
                ("total_color_exposure", "absolute_color_exposure"),
            )
            vanna_exposure = self._first_number(
                row,
                ("vanna_exposure", "dealer_vanna_exposure"),
            )
            charm_exposure = self._first_number(
                row,
                ("charm_exposure", "dealer_charm_exposure"),
            )
            volga_exposure = self._first_number(
                row,
                ("volga_exposure", "dealer_volga_exposure"),
            )
            vomma_exposure = self._first_number(
                row,
                ("vomma_exposure", "dealer_vomma_exposure"),
            )
            color_exposure = self._first_number(
                row,
                ("color_exposure", "dealer_color_exposure"),
            )
            vanna_flip_price = self._first_number(row, ("vanna_flip_price",))
            charm_flip_price = self._first_number(row, ("charm_flip_price",))
            near_expiry_charm_exposure = self._first_number(
                row,
                ("near_expiry_charm_exposure", "near_expiry_total_charm_exposure"),
            )
            near_expiry_color_exposure = self._first_number(
                row,
                ("near_expiry_color_exposure", "near_expiry_total_color_exposure"),
            )

            vanna_exposure_ratio = self._first_number(row, ("vanna_exposure_ratio",))
            if vanna_exposure_ratio is None:
                vanna_exposure_ratio = self._ratio(vanna_exposure, gross_gamma)

            charm_exposure_ratio = self._first_number(row, ("charm_exposure_ratio",))
            if charm_exposure_ratio is None:
                charm_exposure_ratio = self._ratio(charm_exposure, gross_gamma)

            volga_exposure_ratio = self._first_number(row, ("volga_exposure_ratio",))
            if volga_exposure_ratio is None:
                volga_exposure_ratio = self._ratio(volga_exposure, gross_gamma)

            vomma_exposure_ratio = self._first_number(row, ("vomma_exposure_ratio",))
            if vomma_exposure_ratio is None:
                vomma_exposure_ratio = self._ratio(vomma_exposure, gross_gamma)

            color_exposure_ratio = self._first_number(row, ("color_exposure_ratio",))
            if color_exposure_ratio is None:
                color_exposure_ratio = self._ratio(color_exposure, gross_gamma)

            vanna_flip_distance_pct = self._first_number(row, ("vanna_flip_distance_pct",))
            if vanna_flip_distance_pct is None:
                vanna_flip_distance_pct = self._signed_distance_ratio(vanna_flip_price, spot_price)

            charm_flip_distance_pct = self._first_number(row, ("charm_flip_distance_pct",))
            if charm_flip_distance_pct is None:
                charm_flip_distance_pct = self._signed_distance_ratio(charm_flip_price, spot_price)

            near_expiry_charm_share = self._first_number(row, ("near_expiry_charm_share",))
            if near_expiry_charm_share is None:
                near_expiry_charm_share = self._ratio(near_expiry_charm_exposure, total_charm)

            near_expiry_color_share = self._first_number(row, ("near_expiry_color_share",))
            if near_expiry_color_share is None:
                near_expiry_color_share = self._ratio(near_expiry_color_exposure, total_color)

            factor_rows = [
                (
                    "options_vanna_exposure",
                    vanna_exposure,
                    {"metric": "vanna_exposure"},
                ),
                (
                    "options_vanna_exposure_ratio",
                    vanna_exposure_ratio,
                    {"metric": "vanna_exposure_ratio"},
                ),
                (
                    "options_charm_exposure",
                    charm_exposure,
                    {"metric": "charm_exposure"},
                ),
                (
                    "options_charm_exposure_ratio",
                    charm_exposure_ratio,
                    {"metric": "charm_exposure_ratio"},
                ),
                (
                    "options_vanna_flip_distance_pct",
                    vanna_flip_distance_pct,
                    {"metric": "vanna_flip_distance", "reference": "spot"},
                ),
                (
                    "options_charm_flip_distance_pct",
                    charm_flip_distance_pct,
                    {"metric": "charm_flip_distance", "reference": "spot"},
                ),
                (
                    "options_near_expiry_charm_share",
                    near_expiry_charm_share,
                    {"metric": "near_expiry_charm_share"},
                ),
                (
                    "options_volga_exposure",
                    volga_exposure,
                    {"metric": "volga_exposure"},
                ),
                (
                    "options_volga_exposure_ratio",
                    volga_exposure_ratio,
                    {"metric": "volga_exposure_ratio"},
                ),
                (
                    "options_vomma_exposure",
                    vomma_exposure,
                    {"metric": "vomma_exposure"},
                ),
                (
                    "options_vomma_exposure_ratio",
                    vomma_exposure_ratio,
                    {"metric": "vomma_exposure_ratio"},
                ),
                (
                    "options_color_exposure",
                    color_exposure,
                    {"metric": "color_exposure"},
                ),
                (
                    "options_color_exposure_ratio",
                    color_exposure_ratio,
                    {"metric": "color_exposure_ratio"},
                ),
                (
                    "options_near_expiry_color_share",
                    near_expiry_color_share,
                    {"metric": "near_expiry_color_share"},
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
                            row.get("source_symbol")
                            or f"{str(row['entity_key']).upper()}-OPTIONS-HEDGE"
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
