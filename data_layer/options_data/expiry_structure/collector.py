from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class ExpiryStructureCollector(OptionsCollectorBase):
    """期权按到期桶拆分的期限结构采集器。"""

    BUCKET_ALIASES = {
        "7d": {
            "7d",
            "0_7d",
            "front_7d",
            "1w",
            "weekly",
            "lt_7d",
            "lte_7d",
        },
        "30d": {
            "30d",
            "8_30d",
            "front_30d",
            "1m",
            "monthly",
            "lt_30d",
            "lte_30d",
        },
        "90d_plus": {
            "90d_plus",
            "90d+",
            "gt_90d",
            "gte_90d",
            "90d_over",
            "long_dated",
            "back_end",
            "quarter_plus",
        },
    }

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
        if value is None or total is None or total <= 0:
            return None
        return value / total

    @classmethod
    def _normalize_bucket_name(cls, value) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        for normalized_name, aliases in cls.BUCKET_ALIASES.items():
            if text in aliases:
                return normalized_name
        if "90" in text and ("+" in text or "plus" in text or "gt" in text or "over" in text):
            return "90d_plus"
        return None

    @classmethod
    def _bucket_map(cls, row: dict) -> dict[str, dict]:
        bucket_map: dict[str, dict] = {}
        for entry in (
            row.get("expiry_buckets")
            or row.get("buckets")
            or row.get("bucket_snapshots")
            or []
        ):
            if not isinstance(entry, dict):
                continue
            bucket_name = cls._normalize_bucket_name(
                entry.get("bucket")
                or entry.get("expiry_bucket")
                or entry.get("tenor")
                or entry.get("window")
            )
            if bucket_name is None:
                continue
            bucket_map[bucket_name] = dict(entry)
        return bucket_map

    @classmethod
    def _bucket_metric(
        cls,
        bucket_map: dict[str, dict],
        bucket_name: str,
        keys: tuple[str, ...],
    ) -> float | None:
        bucket = bucket_map.get(bucket_name) or {}
        for key in keys:
            value = bucket.get(key)
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
            source_names=["expiry_structure"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["expiry_structure"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_expiry_structure_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            bucket_map = self._bucket_map(row)

            total_oi = self._first_number(
                row,
                (
                    "total_open_interest_notional",
                    "aggregate_open_interest_notional",
                    "total_open_interest_notional_all",
                ),
            )
            gross_gamma = self._first_number(
                row,
                (
                    "gross_gamma_exposure",
                    "absolute_gamma_exposure",
                    "total_abs_gamma_exposure",
                ),
            )
            total_premium = self._first_number(
                row,
                (
                    "total_premium_notional",
                    "total_options_premium_notional",
                    "total_premium",
                ),
            )

            oi_share_7d = self._first_number(row, ("oi_share_7d",))
            if oi_share_7d is None:
                oi_share_7d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "7d",
                        ("open_interest_notional", "oi_notional", "oi"),
                    ),
                    total_oi,
                )

            oi_share_30d = self._first_number(row, ("oi_share_30d",))
            if oi_share_30d is None:
                oi_share_30d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "30d",
                        ("open_interest_notional", "oi_notional", "oi"),
                    ),
                    total_oi,
                )

            oi_share_90d_plus = self._first_number(row, ("oi_share_90d_plus",))
            if oi_share_90d_plus is None:
                oi_share_90d_plus = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "90d_plus",
                        ("open_interest_notional", "oi_notional", "oi"),
                    ),
                    total_oi,
                )

            gamma_share_7d = self._first_number(row, ("gamma_share_7d",))
            if gamma_share_7d is None:
                gamma_share_7d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "7d",
                        ("gamma_exposure", "gross_gamma_exposure", "gamma"),
                    ),
                    gross_gamma,
                )

            gamma_share_30d = self._first_number(row, ("gamma_share_30d",))
            if gamma_share_30d is None:
                gamma_share_30d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "30d",
                        ("gamma_exposure", "gross_gamma_exposure", "gamma"),
                    ),
                    gross_gamma,
                )

            premium_flow_share_7d = self._first_number(row, ("premium_flow_share_7d",))
            if premium_flow_share_7d is None:
                premium_flow_share_7d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "7d",
                        ("premium_notional", "flow_premium_notional", "premium_flow_notional"),
                    ),
                    total_premium,
                )

            premium_flow_share_30d = self._first_number(row, ("premium_flow_share_30d",))
            if premium_flow_share_30d is None:
                premium_flow_share_30d = self._ratio(
                    self._bucket_metric(
                        bucket_map,
                        "30d",
                        ("premium_notional", "flow_premium_notional", "premium_flow_notional"),
                    ),
                    total_premium,
                )

            factor_rows = [
                (
                    "options_oi_share_7d",
                    oi_share_7d,
                    {"bucket": "7d", "metric": "oi_share"},
                ),
                (
                    "options_oi_share_30d",
                    oi_share_30d,
                    {"bucket": "30d", "metric": "oi_share"},
                ),
                (
                    "options_oi_share_90d_plus",
                    oi_share_90d_plus,
                    {"bucket": "90d_plus", "metric": "oi_share"},
                ),
                (
                    "options_gamma_share_7d",
                    gamma_share_7d,
                    {"bucket": "7d", "metric": "gamma_share"},
                ),
                (
                    "options_gamma_share_30d",
                    gamma_share_30d,
                    {"bucket": "30d", "metric": "gamma_share"},
                ),
                (
                    "options_premium_flow_share_7d",
                    premium_flow_share_7d,
                    {"bucket": "7d", "metric": "premium_flow_share"},
                ),
                (
                    "options_premium_flow_share_30d",
                    premium_flow_share_30d,
                    {"bucket": "30d", "metric": "premium_flow_share"},
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
                            or f"{str(row['entity_key']).upper()}-OPTIONS-EXPIRY"
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
