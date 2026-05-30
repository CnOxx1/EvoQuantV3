from datetime import datetime

from data_layer.options_data.base import OptionsCollectorBase
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.models import OptionsTimeSeriesPoint, dump_json
from data_layer.options_data.sources import (
    load_options_factors,
    load_options_sources,
)


class VolSurfaceCollector(OptionsCollectorBase):
    """期权波动率曲面采集器。"""

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
    def _build_term_map(row: dict) -> dict[str, dict]:
        term_map: dict[str, dict] = {}
        for entry in row.get("terms") or []:
            if not isinstance(entry, dict):
                continue
            tenor = str(entry.get("tenor") or "").strip().lower()
            if tenor:
                term_map[tenor] = dict(entry)
        if "7d" not in term_map and row.get("atm_iv_7d") is not None:
            term_map["7d"] = {"atm_iv": row.get("atm_iv_7d")}
        if "30d" not in term_map:
            term_30d: dict[str, object] = {}
            if row.get("atm_iv_30d") is not None:
                term_30d["atm_iv"] = row.get("atm_iv_30d")
            if row.get("risk_reversal_25d_30d") is not None:
                term_30d["risk_reversal_25d"] = row.get("risk_reversal_25d_30d")
            if row.get("butterfly_25d_30d") is not None:
                term_30d["butterfly_25d"] = row.get("butterfly_25d_30d")
            if term_30d:
                term_map["30d"] = term_30d
        return term_map

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OptionsTimeSeriesPoint]:
        source = load_options_sources(
            source_names=["vol_surface"],
            enabled_only=False,
        )[0]
        factors = {
            factor.factor_id: factor
            for factor in load_options_factors(
                source_names=["vol_surface"],
                enabled_only=False,
            )
        }
        rows = self.client.fetch_surface_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval or source.default_interval,
            lookback_hours=lookback_hours,
        )
        points: list[OptionsTimeSeriesPoint] = []
        for row in rows:
            observation_time = self._parse_time(row["observation_time"])
            row_interval = str(row.get("interval") or interval or source.default_interval)
            term_map = self._build_term_map(row)
            atm_iv_7d = self._to_float((term_map.get("7d") or {}).get("atm_iv"))
            atm_iv_30d = self._to_float((term_map.get("30d") or {}).get("atm_iv"))
            risk_reversal_25d_30d = self._to_float(
                (term_map.get("30d") or {}).get("risk_reversal_25d")
            )
            butterfly_25d_30d = self._to_float(
                (term_map.get("30d") or {}).get("butterfly_25d")
            )
            iv_term_structure = self._to_float(row.get("iv_term_structure_7d_30d"))
            if iv_term_structure is None and atm_iv_7d is not None and atm_iv_30d is not None:
                iv_term_structure = atm_iv_7d - atm_iv_30d

            factor_rows = [
                (
                    "options_atm_iv_7d",
                    atm_iv_7d,
                    {"tenor": "7d", "metric": "atm_iv"},
                ),
                (
                    "options_atm_iv_30d",
                    atm_iv_30d,
                    {"tenor": "30d", "metric": "atm_iv"},
                ),
                (
                    "options_iv_term_structure_7d_30d",
                    iv_term_structure,
                    {
                        "front_tenor": "7d",
                        "back_tenor": "30d",
                        "metric": "iv_term_structure",
                    },
                ),
                (
                    "options_25d_risk_reversal_30d",
                    risk_reversal_25d_30d,
                    {"tenor": "30d", "delta": "25d", "metric": "risk_reversal"},
                ),
                (
                    "options_25d_butterfly_30d",
                    butterfly_25d_30d,
                    {"tenor": "30d", "delta": "25d", "metric": "butterfly"},
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
                            row.get("source_symbol") or f"{str(row['entity_key']).upper()}-OPTIONS-IV"
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
