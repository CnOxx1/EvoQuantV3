import json
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from config.settings import OPTIONS_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import (
    is_quality_summary_ai_ready,
    resolve_source_health_status,
    summarize_health_rows,
    summarize_quality_flag_counts,
)
from data_layer.options_data.client import OptionsDataClient
from data_layer.options_data.expiry_structure import ExpiryStructureCollector
from data_layer.options_data.flow_activity import FlowActivityCollector
from data_layer.options_data.gamma_exposure import GammaExposureCollector
from data_layer.options_data.hedge_pressure import HedgePressureCollector
from data_layer.options_data.positioning import PositioningCollector
from data_layer.options_data.relative_value import RelativeValueCollector
from data_layer.options_data.strike_concentration import StrikeConcentrationCollector
from data_layer.options_data.sources import (
    load_options_entities,
    load_options_factors,
    load_options_sources,
)
from data_layer.options_data.vol_surface import VolSurfaceCollector


class OptionsDataService:
    """期权数据模块统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH = 6

    CONTEXT_INTERVAL_RANK = {
        "1h": 4,
        "4h": 3,
        "1d": 2,
        "1w": 1,
    }
    CONTEXT_INTERVAL_PREFERENCES = {
        factor.factor_id: OPTIONS_CONFIG["default_interval"]
        for factor in load_options_factors(enabled_only=False)
    }

    def __init__(
        self,
        client: OptionsDataClient | None = None,
        db: DBManager | None = None,
        vol_surface_collector: VolSurfaceCollector | None = None,
        relative_value_collector: RelativeValueCollector | None = None,
        strike_concentration_collector: StrikeConcentrationCollector | None = None,
        gamma_exposure_collector: GammaExposureCollector | None = None,
        flow_activity_collector: FlowActivityCollector | None = None,
        expiry_structure_collector: ExpiryStructureCollector | None = None,
        hedge_pressure_collector: HedgePressureCollector | None = None,
        positioning_collector: PositioningCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or OptionsDataClient()
        self.vol_surface_collector = vol_surface_collector or VolSurfaceCollector(
            self.client,
            self.db,
        )
        self.relative_value_collector = relative_value_collector or RelativeValueCollector(
            self.client,
            self.db,
        )
        self.strike_concentration_collector = (
            strike_concentration_collector
            or StrikeConcentrationCollector(
                self.client,
                self.db,
            )
        )
        self.gamma_exposure_collector = gamma_exposure_collector or GammaExposureCollector(
            self.client,
            self.db,
        )
        self.flow_activity_collector = flow_activity_collector or FlowActivityCollector(
            self.client,
            self.db,
        )
        self.expiry_structure_collector = (
            expiry_structure_collector
            or ExpiryStructureCollector(
                self.client,
                self.db,
            )
        )
        self.hedge_pressure_collector = (
            hedge_pressure_collector
            or HedgePressureCollector(
                self.client,
                self.db,
            )
        )
        self.positioning_collector = positioning_collector or PositioningCollector(
            self.client,
            self.db,
        )

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _loads_json(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _parse_db_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _count_rows_by_source(rows: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            source_name = str(row["source_name"])
            counts[source_name] = counts.get(source_name, 0) + 1
        return dict(
            sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    @staticmethod
    def _latest_observation_time(rows: list[dict]) -> datetime | None:
        return max(
            (
                row["observation_time_dt"]
                for row in rows
                if row.get("observation_time_dt") is not None
            ),
            default=None,
        )

    @staticmethod
    def _ai_ready_source_names(coverage_rows: list[dict]) -> set[str]:
        return {
            str(row["source_name"])
            for row in coverage_rows
            if row.get("is_ready_for_ai")
        }

    @classmethod
    def _build_ai_excluded_sources(
        cls,
        *,
        raw_rows: list[dict],
        coverage_rows: list[dict],
    ) -> list[dict]:
        raw_rows_by_source: dict[str, list[dict]] = {}
        for row in raw_rows:
            raw_rows_by_source.setdefault(str(row["source_name"]), []).append(row)

        excluded: list[dict] = []
        for coverage_row in coverage_rows:
            source_name = str(coverage_row["source_name"])
            source_rows = raw_rows_by_source.get(source_name) or []
            if not source_rows or coverage_row.get("is_ready_for_ai"):
                continue
            excluded.append(
                {
                    "source_name": source_name,
                    "excluded_reason": cls.AI_EXCLUDED_SOURCE_REASON,
                    "raw_row_count": len(source_rows),
                    "raw_entity_count": len(
                        {
                            str(row["entity_key"])
                            for row in source_rows
                        }
                    ),
                    "raw_factor_ids": sorted(
                        {
                            str(row["factor_id"])
                            for row in source_rows
                        }
                    ),
                    "raw_latest_observation_time": max(
                        (
                            row["observation_time_dt"].isoformat()
                            for row in source_rows
                            if row.get("observation_time_dt") is not None
                        ),
                        default=None,
                    ),
                    "recommended_venues": list(coverage_row.get("recommended_venues") or []),
                    "observed_venues": list(coverage_row.get("observed_venues") or []),
                    "missing_recommended_venues": list(
                        coverage_row.get("missing_recommended_venues") or []
                    ),
                    "venue_coverage_ratio": coverage_row.get("venue_coverage_ratio"),
                    "is_venue_coverage_complete": coverage_row.get(
                        "is_venue_coverage_complete"
                    ),
                    "latest_quality_flag_breakdown": coverage_row.get(
                        "latest_quality_flag_breakdown"
                    ),
                    "latest_quality_ready_ratio": coverage_row.get(
                        "latest_quality_ready_ratio"
                    ),
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    @staticmethod
    def _normalize_venue_name(
        value: object,
        preferred_names: list[str] | None = None,
    ) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        for preferred_name in preferred_names or []:
            if preferred_name.casefold() == text.casefold():
                return preferred_name
        known_aliases = {
            "deribit": "Deribit",
            "okx": "OKX",
            "binance": "Binance",
            "bybit": "Bybit",
            "cme": "CME",
            "cboe": "CBOE",
        }
        alias = known_aliases.get(text.casefold())
        if alias:
            return alias
        if preferred_names:
            return None
        return text

    @classmethod
    def _ordered_venues(
        cls,
        venues: set[str],
        preferred_names: list[str] | None = None,
    ) -> list[str]:
        ordered = [
            venue
            for venue in (preferred_names or [])
            if venue in venues
        ]
        remaining = sorted(
            venue
            for venue in venues
            if venue not in ordered
        )
        return ordered + remaining

    @classmethod
    def _collect_venues_from_payload(
        cls,
        payload,
        observed: set[str],
        preferred_names: list[str] | None = None,
    ) -> None:
        if isinstance(payload, list):
            for item in payload:
                cls._collect_venues_from_payload(item, observed, preferred_names)
            return
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in {"venue", "exchange"}:
                    cls._collect_venues_from_payload(value, observed, preferred_names)
                    continue
                if normalized_key in {
                    "venues",
                    "exchanges",
                    "covered_venues",
                    "included_venues",
                    "contributing_venues",
                    "source_venues",
                }:
                    cls._collect_venues_from_payload(value, observed, preferred_names)
                    continue
                if normalized_key in {
                    "venue_breakdown",
                    "exchange_breakdown",
                    "venue_weights",
                    "exchange_weights",
                }:
                    if isinstance(value, dict):
                        for venue_name in value:
                            normalized_name = cls._normalize_venue_name(
                                venue_name,
                                preferred_names,
                            )
                            if normalized_name:
                                observed.add(normalized_name)
                    else:
                        cls._collect_venues_from_payload(value, observed, preferred_names)
                    continue
                if normalized_key in {"components", "sources"}:
                    cls._collect_venues_from_payload(value, observed, preferred_names)
            return
        normalized_name = cls._normalize_venue_name(payload, preferred_names)
        if normalized_name:
            observed.add(normalized_name)

    @classmethod
    def _extract_observed_venues_from_rows(
        cls,
        rows: list[dict],
        preferred_names: list[str] | None = None,
    ) -> list[str]:
        observed: set[str] = set()
        for row in rows:
            cls._collect_venues_from_payload(
                cls._loads_json(row.get("dimensions_json")) or {},
                observed,
                preferred_names,
            )
            cls._collect_venues_from_payload(
                cls._loads_json(row.get("raw_payload_json")) or {},
                observed,
                preferred_names,
            )
        return cls._ordered_venues(observed, preferred_names)

    @staticmethod
    def _normalize_source_names(
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> list[str]:
        if source_names:
            return [
                source_name.strip().lower()
                for source_name in source_names
                if source_name.strip()
            ]
        if factor_ids:
            factors = load_options_factors(factor_ids=factor_ids, enabled_only=False)
            seen: set[str] = set()
            ordered: list[str] = []
            for factor in factors:
                if factor.source_name in seen:
                    continue
                seen.add(factor.source_name)
                ordered.append(factor.source_name)
            return ordered
        return [source.source_name for source in load_options_sources(enabled_only=False)]

    @staticmethod
    def _normalize_entity_keys(entity_keys: list[str] | None = None) -> list[str] | None:
        values = [
            item.strip().upper()
            for item in (entity_keys or [])
            if item.strip()
        ]
        return values or None

    @staticmethod
    def _normalize_factor_ids(factor_ids: list[str] | None = None) -> list[str] | None:
        values = [
            item.strip()
            for item in (factor_ids or [])
            if item.strip()
        ]
        return values or None

    @staticmethod
    def _requested_sources_reduce_configured_universe(
        requested_source_names: list[str] | None = None,
    ) -> bool:
        normalized_requested = {
            source_name.strip().lower()
            for source_name in (requested_source_names or [])
            if source_name.strip()
        }
        if not normalized_requested:
            return False
        default_sources = {
            source.source_name.strip().lower()
            for source in load_options_sources(enabled_only=False)
        }
        return normalized_requested != default_sources

    @staticmethod
    def _count_collection_items(result) -> int:
        if result is None:
            return 0
        if isinstance(result, dict):
            return sum(
                int(value)
                for value in result.values()
                if isinstance(value, int | float)
            )
        if isinstance(result, str | bytes):
            return int(bool(result))
        return len(result)

    @staticmethod
    def _source_interval_seconds(source_name: str) -> int:
        return {
            "vol_surface": OPTIONS_CONFIG["vol_surface_interval_seconds"],
            "relative_value": OPTIONS_CONFIG["relative_value_interval_seconds"],
            "strike_concentration": OPTIONS_CONFIG["strike_concentration_interval_seconds"],
            "gamma_exposure": OPTIONS_CONFIG["gamma_exposure_interval_seconds"],
            "flow_activity": OPTIONS_CONFIG["flow_activity_interval_seconds"],
            "expiry_structure": OPTIONS_CONFIG["expiry_structure_interval_seconds"],
            "hedge_pressure": OPTIONS_CONFIG["hedge_pressure_interval_seconds"],
            "positioning": OPTIONS_CONFIG["positioning_interval_seconds"],
        }.get(source_name, 3600)

    @staticmethod
    def _should_run_source(
        requested_sources: set[str],
        source_name: str,
        enabled: bool,
    ) -> bool:
        if not enabled:
            return False
        if not requested_sources:
            return True
        return source_name in requested_sources

    @classmethod
    def _context_row_rank(cls, row: dict) -> tuple:
        preferred_interval = cls.CONTEXT_INTERVAL_PREFERENCES.get(row["factor_id"])
        observation_time = row.get("observation_time_dt") or datetime.min
        is_preferred_interval = (
            1
            if preferred_interval is None or row.get("interval") == preferred_interval
            else 0
        )
        interval_rank = cls.CONTEXT_INTERVAL_RANK.get(str(row.get("interval") or ""), 0)
        return (
            is_preferred_interval,
            observation_time,
            interval_rank,
        )

    @classmethod
    def _select_preferred_context_rows(
        cls,
        rows: list[dict],
    ) -> list[dict]:
        selected: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (str(row["factor_id"]), str(row["entity_key"]))
            previous = selected.get(key)
            if previous is None or cls._context_row_rank(row) >= cls._context_row_rank(previous):
                selected[key] = row
        return list(selected.values())

    @staticmethod
    def _entity_observation_time(row_map: dict[str, dict]) -> str | None:
        timestamps = [
            row.get("observation_time_dt")
            for row in row_map.values()
            if row.get("observation_time_dt") is not None
        ]
        if not timestamps:
            return None
        return max(timestamps).isoformat()

    @staticmethod
    def _entity_quality_flag(row_map: dict[str, dict], preferred_factor_ids: list[str]) -> str:
        for factor_id in preferred_factor_ids:
            row = row_map.get(factor_id)
            if row is not None:
                return str(row.get("quality_flag") or "ok")
        for row in row_map.values():
            return str(row.get("quality_flag") or "ok")
        return "ok"

    @classmethod
    def _build_venue_coverage_summary(
        cls,
        coverage_rows: list[dict],
    ) -> dict:
        tracked_rows = [
            row
            for row in coverage_rows
            if row.get("recommended_venues")
        ]
        preferred_order: list[str] = []
        observed_venues: set[str] = set()
        coverage_by_source: dict[str, dict] = {}
        for row in tracked_rows:
            for venue in row.get("recommended_venues") or []:
                if venue not in preferred_order:
                    preferred_order.append(venue)
            for venue in row.get("observed_venues") or []:
                observed_venues.add(str(venue))
            coverage_by_source[str(row["source_name"])] = {
                "recommended_venues": list(row.get("recommended_venues") or []),
                "observed_venues": list(row.get("observed_venues") or []),
                "missing_recommended_venues": list(
                    row.get("missing_recommended_venues") or []
                ),
                "recommended_venue_count": int(row.get("recommended_venue_count") or 0),
                "observed_venue_count": int(row.get("observed_venue_count") or 0),
                "venue_coverage_ratio": row.get("venue_coverage_ratio"),
                "is_venue_coverage_complete": bool(
                    row.get("is_venue_coverage_complete")
                ),
                "is_ready_for_ai": bool(row.get("is_ready_for_ai")),
            }
        return {
            "source_count": len(tracked_rows),
            "complete_source_count": sum(
                1
                for row in tracked_rows
                if row.get("is_venue_coverage_complete")
            ),
            "partial_source_count": sum(
                1
                for row in tracked_rows
                if row.get("observed_venue_count")
                and row.get("missing_recommended_venues")
            ),
            "missing_identity_source_count": sum(
                1
                for row in tracked_rows
                if int(row.get("recommended_venue_count") or 0) > 0
                and not row.get("observed_venue_count")
            ),
            "observed_venue_count": len(observed_venues),
            "observed_venues": cls._ordered_venues(observed_venues, preferred_order),
            "coverage_by_source": coverage_by_source,
        }

    @staticmethod
    def _is_source_ready_for_ai(
        *,
        health_status: str,
        expected_entity_count: int,
        latest_entity_count: int,
        expected_factor_count: int,
        latest_factor_count: int,
        recommended_venue_count: int,
        missing_recommended_venues: list[str],
        quality_summary: dict[str, object],
    ) -> bool:
        if health_status != "ready":
            return False
        if expected_entity_count > 0 and latest_entity_count < expected_entity_count:
            return False
        if expected_factor_count > 0 and latest_factor_count < expected_factor_count:
            return False
        if recommended_venue_count > 0 and missing_recommended_venues:
            return False
        return is_quality_summary_ai_ready(quality_summary)

    @staticmethod
    def _pick_leader(
        entities: list[dict],
        *,
        field_name: str,
        reverse: bool = True,
    ) -> dict | None:
        candidates = [
            entity
            for entity in entities
            if entity.get(field_name) is not None
        ]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda item: (
                float(item[field_name]),
                item["entity_key"],
            ),
            reverse=reverse,
        )[0]

    @staticmethod
    def _pick_smallest_abs(
        entities: list[dict],
        *,
        field_name: str,
    ) -> dict | None:
        candidates = [
            entity
            for entity in entities
            if entity.get(field_name) is not None
        ]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda item: (
                abs(float(item[field_name])),
                item["entity_key"],
            ),
        )[0]

    @staticmethod
    def _pick_largest_abs(
        entities: list[dict],
        *,
        field_name: str,
    ) -> dict | None:
        candidates = [
            entity
            for entity in entities
            if entity.get(field_name) is not None
        ]
        if not candidates:
            return None
        return sorted(
            candidates,
            key=lambda item: (
                abs(float(item[field_name])),
                item["entity_key"],
            ),
            reverse=True,
        )[0]

    def _run_collection_job(
        self,
        *,
        source_name: str,
        job_name: str,
        func,
        metadata: dict[str, object] | None = None,
        configuration_ready: bool = True,
        unconfigured_message: str | None = None,
    ):
        started_at = self._utc_now_naive()
        status = "success"
        message = None
        item_count = 0
        result = None
        captured_exception = None

        if not configuration_ready:
            status = "unconfigured"
            message = unconfigured_message or f"期权来源 {source_name} 未配置 endpoint"
        else:
            try:
                result = func()
                item_count = self._count_collection_items(result)
                if item_count == 0:
                    status = "empty"
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                captured_exception = exc
                logger.error(f"期权来源采集失败 [{source_name}]: {message}")

        finished_at = self._utc_now_naive()
        self.db.record_collection_run(
            module_name="options_data",
            source_name=source_name,
            job_name=job_name,
            status=status,
            item_count=item_count,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=(finished_at - started_at).total_seconds(),
            message=message,
            metadata_json=json.dumps(
                metadata or {},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        if captured_exception is not None:
            raise captured_exception
        return result

    def init_storage(self):
        self.db.init_market_data_tables()
        self.sync_factor_catalog()

    def sync_factor_catalog(self):
        factors = load_options_factors(enabled_only=False)
        if not factors:
            return
        sql = """
            INSERT INTO options_factor_catalog (
                factor_id, name, category, factor_type, entity_scope, entity_type,
                description, default_interval, unit, source_name, source_symbol,
                source_priority, config_version, staleness_ttl_seconds, enabled,
                raw_meta_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                factor_type=excluded.factor_type,
                entity_scope=excluded.entity_scope,
                entity_type=excluded.entity_type,
                description=excluded.description,
                default_interval=excluded.default_interval,
                unit=excluded.unit,
                source_name=excluded.source_name,
                source_symbol=excluded.source_symbol,
                source_priority=excluded.source_priority,
                config_version=excluded.config_version,
                staleness_ttl_seconds=excluded.staleness_ttl_seconds,
                enabled=excluded.enabled,
                raw_meta_json=excluded.raw_meta_json,
                updated_at=excluded.updated_at
        """
        self.db.execute_many(sql, [factor.to_catalog_tuple() for factor in factors])
        self.db.commit()

    def _collect_source(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ):
        if source_name == "vol_surface":
            return self.vol_surface_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "relative_value":
            return self.relative_value_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "strike_concentration":
            return self.strike_concentration_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "gamma_exposure":
            return self.gamma_exposure_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "flow_activity":
            return self.flow_activity_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "expiry_structure":
            return self.expiry_structure_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "hedge_pressure":
            return self.hedge_pressure_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "positioning":
            return self.positioning_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        raise ValueError(f"未知 options source: {source_name}")

    def collect_once(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> dict[str, int]:
        self.sync_factor_catalog()
        requested_sources = set(self._normalize_source_names(source_names=source_names))
        entity_keys = self._normalize_entity_keys(entity_keys)
        summary = {
            "vol_surface_points": 0,
            "relative_value_points": 0,
            "strike_concentration_points": 0,
            "gamma_exposure_points": 0,
            "flow_activity_points": 0,
            "expiry_structure_points": 0,
            "hedge_pressure_points": 0,
            "positioning_points": 0,
            "total_points": 0,
        }
        for source in load_options_sources(enabled_only=False):
            if not self._should_run_source(requested_sources, source.source_name, source.enabled):
                continue
            points = self._run_collection_job(
                source_name=source.source_name,
                job_name="options_timeseries",
                func=lambda source_name=source.source_name: self._collect_source(
                    source_name=source_name,
                    entity_keys=entity_keys,
                    interval=interval or OPTIONS_CONFIG["default_interval"],
                    lookback_hours=lookback_hours or OPTIONS_CONFIG["default_lookback_hours"],
                ),
                metadata={
                    "mode": "once",
                    "entity_keys": entity_keys,
                    "interval": interval or OPTIONS_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or OPTIONS_CONFIG["default_lookback_hours"],
                    "endpoint": source.endpoint,
                },
                configuration_ready=bool(source.endpoint),
                unconfigured_message=(
                    f"期权来源 {source.source_name} 未配置 endpoint，无法执行采集"
                ),
            ) or []
            summary_key = f"{source.source_name}_points"
            summary[summary_key] = len(points)
            summary["total_points"] += len(points)
        return summary

    def describe_registry(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict[str, list[dict]]:
        source_names = self._normalize_source_names(source_names=source_names, factor_ids=factor_ids)
        factor_ids = self._normalize_factor_ids(factor_ids)
        entity_keys = self._normalize_entity_keys(entity_keys)
        return {
            "sources": [
                {
                    "source_name": source.source_name,
                    "name": source.name,
                    "collector_key": source.collector_key,
                    "primary_factor_id": source.primary_factor_id,
                    "entity_type": source.entity_type,
                    "default_interval": source.default_interval,
                    "enabled": source.enabled,
                    "endpoint": source.endpoint,
                    "description": source.description,
                    "phase": source.raw_meta.get("phase"),
                    "semantic_scope": source.raw_meta.get("semantic_scope"),
                }
                for source in load_options_sources(
                    source_names=source_names,
                    enabled_only=False,
                )
            ],
            "factors": [
                {
                    "factor_id": factor.factor_id,
                    "name": factor.name,
                    "category": factor.category,
                    "factor_type": factor.factor_type,
                    "entity_type": factor.entity_type,
                    "default_interval": factor.default_interval,
                    "source_name": factor.source_name,
                    "enabled": factor.enabled,
                }
                for factor in load_options_factors(
                    factor_ids=factor_ids,
                    source_names=source_names,
                    enabled_only=False,
                )
            ],
            "entities": load_options_entities(
                source_names=source_names,
                entity_keys=entity_keys,
            ),
        }

    def load_latest_context(
        self,
        entity_keys: list[str] | None = None,
        factor_ids: list[str] | None = None,
        source_names: list[str] | None = None,
    ) -> list[dict]:
        sql = """
            SELECT factor_id, category, factor_type, entity_type, entity_key,
                   interval, observation_time, value, unit, quality_flag,
                   dimensions_key, dimensions_json, config_version, source_name,
                   source_symbol, raw_payload_json, collected_at, updated_at
            FROM latest_options_timeseries
        """
        clauses: list[str] = []
        params: list[str] = []
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        normalized_source_names = self._normalize_source_names(
            source_names=source_names,
            factor_ids=factor_ids,
        )
        if normalized_entity_keys:
            placeholders = ",".join("?" for _ in normalized_entity_keys)
            clauses.append(f"entity_key IN ({placeholders})")
            params.extend(normalized_entity_keys)
        if normalized_factor_ids:
            placeholders = ",".join("?" for _ in normalized_factor_ids)
            clauses.append(f"factor_id IN ({placeholders})")
            params.extend(normalized_factor_ids)
        if normalized_source_names:
            placeholders = ",".join("?" for _ in normalized_source_names)
            clauses.append(f"source_name IN ({placeholders})")
            params.extend(normalized_source_names)
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        sql += " ORDER BY entity_key, factor_id, observation_time DESC"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]

    def _build_combined_assets(
        self,
        rows: list[dict],
        entity_name_map: dict[tuple[str, str], dict[str, str]],
    ) -> list[dict]:
        rows_by_entity: dict[str, dict[str, dict]] = {}
        for row in rows:
            rows_by_entity.setdefault(str(row["entity_key"]), {})[str(row["factor_id"])] = row

        assets: list[dict] = []
        for entity_key, row_map in rows_by_entity.items():
            meta = entity_name_map.get(("vol_surface", entity_key)) or entity_name_map.get(
                ("relative_value", entity_key),
                {},
            ) or entity_name_map.get(
                ("strike_concentration", entity_key),
                {},
            ) or entity_name_map.get(
                ("gamma_exposure", entity_key),
                {},
            ) or entity_name_map.get(
                ("flow_activity", entity_key),
                {},
            ) or entity_name_map.get(
                ("expiry_structure", entity_key),
                {},
            ) or entity_name_map.get(
                ("hedge_pressure", entity_key),
                {},
            ) or entity_name_map.get(
                ("positioning", entity_key),
                {},
            )
            assets.append(
                {
                    "entity_key": entity_key,
                    "name": meta.get("name") or entity_key,
                    "description": meta.get("description"),
                    "observation_time": self._entity_observation_time(row_map),
                    "quality_flag": self._entity_quality_flag(
                        row_map,
                        [
                            "options_atm_iv_30d",
                            "options_iv_rv_spread_30d",
                            "options_top_strike_oi_share",
                            "options_net_gamma_exposure_ratio",
                            "options_net_call_premium_flow_ratio",
                            "options_oi_share_30d",
                            "options_vanna_exposure_ratio",
                            "options_color_exposure_ratio",
                            "options_put_call_oi_ratio_30d",
                        ],
                    ),
                    "atm_iv_7d": (row_map.get("options_atm_iv_7d") or {}).get("value"),
                    "atm_iv_30d": (row_map.get("options_atm_iv_30d") or {}).get("value"),
                    "iv_term_structure_7d_30d": (
                        (row_map.get("options_iv_term_structure_7d_30d") or {}).get("value")
                    ),
                    "risk_reversal_25d_30d": (
                        (row_map.get("options_25d_risk_reversal_30d") or {}).get("value")
                    ),
                    "butterfly_25d_30d": (
                        (row_map.get("options_25d_butterfly_30d") or {}).get("value")
                    ),
                    "realized_vol_7d": (
                        (row_map.get("options_realized_vol_7d") or {}).get("value")
                    ),
                    "realized_vol_30d": (
                        (row_map.get("options_realized_vol_30d") or {}).get("value")
                    ),
                    "iv_rv_spread_7d": (
                        (row_map.get("options_iv_rv_spread_7d") or {}).get("value")
                    ),
                    "iv_rv_spread_30d": (
                        (row_map.get("options_iv_rv_spread_30d") or {}).get("value")
                    ),
                    "max_pain_distance_pct": (
                        (row_map.get("options_max_pain_distance_pct") or {}).get("value")
                    ),
                    "call_wall_distance_pct": (
                        (row_map.get("options_call_wall_distance_pct") or {}).get("value")
                    ),
                    "put_wall_distance_pct": (
                        (row_map.get("options_put_wall_distance_pct") or {}).get("value")
                    ),
                    "top_strike_oi_share": (
                        (row_map.get("options_top_strike_oi_share") or {}).get("value")
                    ),
                    "near_expiry_top_strike_oi_share": (
                        (row_map.get("options_near_expiry_top_strike_oi_share") or {}).get("value")
                    ),
                    "atm_strike_oi_share": (
                        (row_map.get("options_atm_strike_oi_share") or {}).get("value")
                    ),
                    "net_gamma_exposure": (
                        (row_map.get("options_net_gamma_exposure") or {}).get("value")
                    ),
                    "net_gamma_exposure_ratio": (
                        (row_map.get("options_net_gamma_exposure_ratio") or {}).get("value")
                    ),
                    "gamma_flip_distance_pct": (
                        (row_map.get("options_gamma_flip_distance_pct") or {}).get("value")
                    ),
                    "call_gamma_wall_distance_pct": (
                        (row_map.get("options_call_gamma_wall_distance_pct") or {}).get("value")
                    ),
                    "put_gamma_wall_distance_pct": (
                        (row_map.get("options_put_gamma_wall_distance_pct") or {}).get("value")
                    ),
                    "top_gamma_strike_share": (
                        (row_map.get("options_top_gamma_strike_share") or {}).get("value")
                    ),
                    "near_expiry_gamma_share": (
                        (row_map.get("options_near_expiry_gamma_share") or {}).get("value")
                    ),
                    "call_buyer_premium_share": (
                        (row_map.get("options_call_buyer_premium_share") or {}).get("value")
                    ),
                    "put_buyer_premium_share": (
                        (row_map.get("options_put_buyer_premium_share") or {}).get("value")
                    ),
                    "net_call_premium_flow_ratio": (
                        (row_map.get("options_net_call_premium_flow_ratio") or {}).get("value")
                    ),
                    "net_put_premium_flow_ratio": (
                        (row_map.get("options_net_put_premium_flow_ratio") or {}).get("value")
                    ),
                    "opening_flow_share": (
                        (row_map.get("options_opening_flow_share") or {}).get("value")
                    ),
                    "near_expiry_flow_share": (
                        (row_map.get("options_near_expiry_flow_share") or {}).get("value")
                    ),
                    "block_trade_flow_share": (
                        (row_map.get("options_block_trade_flow_share") or {}).get("value")
                    ),
                    "oi_share_7d": (
                        (row_map.get("options_oi_share_7d") or {}).get("value")
                    ),
                    "oi_share_30d": (
                        (row_map.get("options_oi_share_30d") or {}).get("value")
                    ),
                    "oi_share_90d_plus": (
                        (row_map.get("options_oi_share_90d_plus") or {}).get("value")
                    ),
                    "gamma_share_7d": (
                        (row_map.get("options_gamma_share_7d") or {}).get("value")
                    ),
                    "gamma_share_30d": (
                        (row_map.get("options_gamma_share_30d") or {}).get("value")
                    ),
                    "premium_flow_share_7d": (
                        (row_map.get("options_premium_flow_share_7d") or {}).get("value")
                    ),
                    "premium_flow_share_30d": (
                        (row_map.get("options_premium_flow_share_30d") or {}).get("value")
                    ),
                    "vanna_exposure": (
                        (row_map.get("options_vanna_exposure") or {}).get("value")
                    ),
                    "vanna_exposure_ratio": (
                        (row_map.get("options_vanna_exposure_ratio") or {}).get("value")
                    ),
                    "charm_exposure": (
                        (row_map.get("options_charm_exposure") or {}).get("value")
                    ),
                    "charm_exposure_ratio": (
                        (row_map.get("options_charm_exposure_ratio") or {}).get("value")
                    ),
                    "vanna_flip_distance_pct": (
                        (row_map.get("options_vanna_flip_distance_pct") or {}).get("value")
                    ),
                    "charm_flip_distance_pct": (
                        (row_map.get("options_charm_flip_distance_pct") or {}).get("value")
                    ),
                    "near_expiry_charm_share": (
                        (row_map.get("options_near_expiry_charm_share") or {}).get("value")
                    ),
                    "volga_exposure": (
                        (row_map.get("options_volga_exposure") or {}).get("value")
                    ),
                    "volga_exposure_ratio": (
                        (row_map.get("options_volga_exposure_ratio") or {}).get("value")
                    ),
                    "vomma_exposure": (
                        (row_map.get("options_vomma_exposure") or {}).get("value")
                    ),
                    "vomma_exposure_ratio": (
                        (row_map.get("options_vomma_exposure_ratio") or {}).get("value")
                    ),
                    "color_exposure": (
                        (row_map.get("options_color_exposure") or {}).get("value")
                    ),
                    "color_exposure_ratio": (
                        (row_map.get("options_color_exposure_ratio") or {}).get("value")
                    ),
                    "near_expiry_color_share": (
                        (row_map.get("options_near_expiry_color_share") or {}).get("value")
                    ),
                    "put_call_oi_ratio_30d": (
                        (row_map.get("options_put_call_oi_ratio_30d") or {}).get("value")
                    ),
                    "call_oi_share_30d": (
                        (row_map.get("options_call_oi_share_30d") or {}).get("value")
                    ),
                    "total_oi_notional_30d": (
                        (row_map.get("options_total_oi_notional_30d") or {}).get("value")
                    ),
                    "near_expiry_oi_share": (
                        (row_map.get("options_near_expiry_oi_share") or {}).get("value")
                    ),
                    "largest_expiry_oi_share": (
                        (row_map.get("options_largest_expiry_oi_share") or {}).get("value")
                    ),
                }
            )

        assets.sort(
            key=lambda item: (
                -(float(item["total_oi_notional_30d"]) if item["total_oi_notional_30d"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return assets

    def _build_vol_surface_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "atm_iv_7d": asset["atm_iv_7d"],
                "atm_iv_30d": asset["atm_iv_30d"],
                "iv_term_structure_7d_30d": asset["iv_term_structure_7d_30d"],
                "risk_reversal_25d_30d": asset["risk_reversal_25d_30d"],
                "butterfly_25d_30d": asset["butterfly_25d_30d"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "atm_iv_7d",
                    "atm_iv_30d",
                    "iv_term_structure_7d_30d",
                    "risk_reversal_25d_30d",
                    "butterfly_25d_30d",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(float(item["atm_iv_30d"]) if item["atm_iv_30d"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "iv_leaders": rows[:5],
            "entities": rows,
        }

    def _build_relative_value_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "realized_vol_7d": asset["realized_vol_7d"],
                "realized_vol_30d": asset["realized_vol_30d"],
                "iv_rv_spread_7d": asset["iv_rv_spread_7d"],
                "iv_rv_spread_30d": asset["iv_rv_spread_30d"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "realized_vol_7d",
                    "realized_vol_30d",
                    "iv_rv_spread_7d",
                    "iv_rv_spread_30d",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(float(item["iv_rv_spread_30d"]) if item["iv_rv_spread_30d"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "rich_iv_leaders": rows[:5],
            "entities": rows,
        }

    def _build_strike_concentration_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "max_pain_distance_pct": asset["max_pain_distance_pct"],
                "call_wall_distance_pct": asset["call_wall_distance_pct"],
                "put_wall_distance_pct": asset["put_wall_distance_pct"],
                "top_strike_oi_share": asset["top_strike_oi_share"],
                "near_expiry_top_strike_oi_share": asset["near_expiry_top_strike_oi_share"],
                "atm_strike_oi_share": asset["atm_strike_oi_share"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "max_pain_distance_pct",
                    "call_wall_distance_pct",
                    "put_wall_distance_pct",
                    "top_strike_oi_share",
                    "near_expiry_top_strike_oi_share",
                    "atm_strike_oi_share",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(float(item["near_expiry_top_strike_oi_share"]) if item["near_expiry_top_strike_oi_share"] is not None else -999999.0),
                -(float(item["top_strike_oi_share"]) if item["top_strike_oi_share"] is not None else -999999.0),
                abs(float(item["max_pain_distance_pct"])) if item["max_pain_distance_pct"] is not None else 999999.0,
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "pin_risk_watchlist": rows[:5],
            "entities": rows,
        }

    def _build_gamma_exposure_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "net_gamma_exposure": asset["net_gamma_exposure"],
                "net_gamma_exposure_ratio": asset["net_gamma_exposure_ratio"],
                "gamma_flip_distance_pct": asset["gamma_flip_distance_pct"],
                "call_gamma_wall_distance_pct": asset["call_gamma_wall_distance_pct"],
                "put_gamma_wall_distance_pct": asset["put_gamma_wall_distance_pct"],
                "top_gamma_strike_share": asset["top_gamma_strike_share"],
                "near_expiry_gamma_share": asset["near_expiry_gamma_share"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "net_gamma_exposure",
                    "net_gamma_exposure_ratio",
                    "gamma_flip_distance_pct",
                    "call_gamma_wall_distance_pct",
                    "put_gamma_wall_distance_pct",
                    "top_gamma_strike_share",
                    "near_expiry_gamma_share",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(
                    abs(float(item["net_gamma_exposure_ratio"]))
                    if item["net_gamma_exposure_ratio"] is not None
                    else -999999.0
                ),
                (
                    abs(float(item["gamma_flip_distance_pct"]))
                    if item["gamma_flip_distance_pct"] is not None
                    else 999999.0
                ),
                -(
                    float(item["near_expiry_gamma_share"])
                    if item["near_expiry_gamma_share"] is not None
                    else -999999.0
                ),
                -(
                    float(item["top_gamma_strike_share"])
                    if item["top_gamma_strike_share"] is not None
                    else -999999.0
                ),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "regime_watchlist": rows[:5],
            "entities": rows,
        }

    def _build_flow_activity_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "call_buyer_premium_share": asset["call_buyer_premium_share"],
                "put_buyer_premium_share": asset["put_buyer_premium_share"],
                "net_call_premium_flow_ratio": asset["net_call_premium_flow_ratio"],
                "net_put_premium_flow_ratio": asset["net_put_premium_flow_ratio"],
                "opening_flow_share": asset["opening_flow_share"],
                "near_expiry_flow_share": asset["near_expiry_flow_share"],
                "block_trade_flow_share": asset["block_trade_flow_share"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "call_buyer_premium_share",
                    "put_buyer_premium_share",
                    "net_call_premium_flow_ratio",
                    "net_put_premium_flow_ratio",
                    "opening_flow_share",
                    "near_expiry_flow_share",
                    "block_trade_flow_share",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -max(
                    abs(float(item["net_call_premium_flow_ratio"]))
                    if item["net_call_premium_flow_ratio"] is not None
                    else 0.0,
                    abs(float(item["net_put_premium_flow_ratio"]))
                    if item["net_put_premium_flow_ratio"] is not None
                    else 0.0,
                ),
                -(
                    float(item["opening_flow_share"])
                    if item["opening_flow_share"] is not None
                    else -999999.0
                ),
                -(
                    float(item["near_expiry_flow_share"])
                    if item["near_expiry_flow_share"] is not None
                    else -999999.0
                ),
                -(
                    float(item["block_trade_flow_share"])
                    if item["block_trade_flow_share"] is not None
                    else -999999.0
                ),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "flow_watchlist": rows[:5],
            "entities": rows,
        }

    def _build_expiry_structure_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "oi_share_7d": asset["oi_share_7d"],
                "oi_share_30d": asset["oi_share_30d"],
                "oi_share_90d_plus": asset["oi_share_90d_plus"],
                "gamma_share_7d": asset["gamma_share_7d"],
                "gamma_share_30d": asset["gamma_share_30d"],
                "premium_flow_share_7d": asset["premium_flow_share_7d"],
                "premium_flow_share_30d": asset["premium_flow_share_30d"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "oi_share_7d",
                    "oi_share_30d",
                    "oi_share_90d_plus",
                    "gamma_share_7d",
                    "gamma_share_30d",
                    "premium_flow_share_7d",
                    "premium_flow_share_30d",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(
                    float(item["gamma_share_7d"])
                    if item["gamma_share_7d"] is not None
                    else -999999.0
                ),
                -(
                    float(item["premium_flow_share_7d"])
                    if item["premium_flow_share_7d"] is not None
                    else -999999.0
                ),
                -(
                    float(item["oi_share_7d"])
                    if item["oi_share_7d"] is not None
                    else -999999.0
                ),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "expiry_watchlist": rows[:5],
            "entities": rows,
        }

    def _build_hedge_pressure_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "vanna_exposure": asset["vanna_exposure"],
                "vanna_exposure_ratio": asset["vanna_exposure_ratio"],
                "charm_exposure": asset["charm_exposure"],
                "charm_exposure_ratio": asset["charm_exposure_ratio"],
                "vanna_flip_distance_pct": asset["vanna_flip_distance_pct"],
                "charm_flip_distance_pct": asset["charm_flip_distance_pct"],
                "near_expiry_charm_share": asset["near_expiry_charm_share"],
                "volga_exposure": asset["volga_exposure"],
                "volga_exposure_ratio": asset["volga_exposure_ratio"],
                "vomma_exposure": asset["vomma_exposure"],
                "vomma_exposure_ratio": asset["vomma_exposure_ratio"],
                "color_exposure": asset["color_exposure"],
                "color_exposure_ratio": asset["color_exposure_ratio"],
                "near_expiry_color_share": asset["near_expiry_color_share"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "vanna_exposure",
                    "vanna_exposure_ratio",
                    "charm_exposure",
                    "charm_exposure_ratio",
                    "vanna_flip_distance_pct",
                    "charm_flip_distance_pct",
                    "near_expiry_charm_share",
                    "volga_exposure",
                    "volga_exposure_ratio",
                    "vomma_exposure",
                    "vomma_exposure_ratio",
                    "color_exposure",
                    "color_exposure_ratio",
                    "near_expiry_color_share",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -max(
                    abs(float(item["color_exposure_ratio"]))
                    if item["color_exposure_ratio"] is not None
                    else 0.0,
                    abs(float(item["vomma_exposure_ratio"]))
                    if item["vomma_exposure_ratio"] is not None
                    else 0.0,
                    abs(float(item["volga_exposure_ratio"]))
                    if item["volga_exposure_ratio"] is not None
                    else 0.0,
                    abs(float(item["vanna_exposure_ratio"]))
                    if item["vanna_exposure_ratio"] is not None
                    else 0.0,
                    abs(float(item["charm_exposure_ratio"]))
                    if item["charm_exposure_ratio"] is not None
                    else 0.0,
                ),
                -(
                    abs(float(item["color_exposure_ratio"]))
                    if item["color_exposure_ratio"] is not None
                    else 0.0
                ),
                (
                    abs(float(item["vanna_flip_distance_pct"]))
                    if item["vanna_flip_distance_pct"] is not None
                    else 999999.0
                ),
                (
                    abs(float(item["charm_flip_distance_pct"]))
                    if item["charm_flip_distance_pct"] is not None
                    else 999999.0
                ),
                -(
                    float(item["near_expiry_charm_share"])
                    if item["near_expiry_charm_share"] is not None
                    else -999999.0
                ),
                -(
                    float(item["near_expiry_color_share"])
                    if item["near_expiry_color_share"] is not None
                    else -999999.0
                ),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "hedge_watchlist": rows[:5],
            "entities": rows,
        }

    def _build_positioning_context(
        self,
        assets: list[dict],
    ) -> dict:
        rows = [
            {
                "entity_key": asset["entity_key"],
                "name": asset["name"],
                "description": asset["description"],
                "observation_time": asset["observation_time"],
                "quality_flag": asset["quality_flag"],
                "put_call_oi_ratio_30d": asset["put_call_oi_ratio_30d"],
                "call_oi_share_30d": asset["call_oi_share_30d"],
                "total_oi_notional_30d": asset["total_oi_notional_30d"],
                "near_expiry_oi_share": asset["near_expiry_oi_share"],
                "largest_expiry_oi_share": asset["largest_expiry_oi_share"],
            }
            for asset in assets
            if any(
                asset.get(key) is not None
                for key in (
                    "put_call_oi_ratio_30d",
                    "call_oi_share_30d",
                    "total_oi_notional_30d",
                    "near_expiry_oi_share",
                    "largest_expiry_oi_share",
                )
            )
        ]
        rows.sort(
            key=lambda item: (
                -(float(item["total_oi_notional_30d"]) if item["total_oi_notional_30d"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(rows),
            "oi_leaders": rows[:5],
            "entities": rows,
        }

    @staticmethod
    def _missing_asset_count(
        assets: list[dict],
        required_fields: tuple[str, ...],
    ) -> int:
        return sum(
            1
            for asset in assets
            if any(asset.get(field_name) is None for field_name in required_fields)
        )

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        configured_entity_keys: list[str],
        requested_entity_keys: list[str] | None = None,
        requested_factor_ids: list[str] | None = None,
        requested_source_names: list[str] | None = None,
    ) -> dict[str, object]:
        source_names_reduce_universe = cls._requested_sources_reduce_configured_universe(
            requested_source_names
        )
        scope_kind = (
            "filtered"
            if requested_entity_keys or requested_factor_ids or source_names_reduce_universe
            else "default"
        )
        asset_count = len(configured_entity_keys)
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = (
                "sufficient"
                if asset_count >= cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH
                else "limited"
            )
        return {
            "scope_kind": scope_kind,
            "tracked_entity_keys": list(configured_entity_keys),
            "asset_entity_count": asset_count,
            "minimum_asset_entity_count_for_market_breadth": (
                cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH
            ),
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    def _build_context_quality(
        self,
        *,
        assets: list[dict],
        raw_row_count: int,
        ai_excluded_source_count: int,
        expected_entity_keys: list[str],
        expected_factor_ids: list[str],
        observed_factor_ids: set[str],
        quality_summary: dict[str, object],
        coverage_rows: list[dict],
        requested_entity_keys: list[str] | None = None,
        configured_universe_summary: dict[str, object] | None = None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []
        observed_entity_keys = [
            str(asset["entity_key"])
            for asset in assets
        ]
        missing_entity_keys = [
            entity_key
            for entity_key in expected_entity_keys
            if entity_key not in observed_entity_keys
        ]
        missing_factor_ids = [
            factor_id
            for factor_id in expected_factor_ids
            if factor_id not in observed_factor_ids
        ]
        non_ready_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("health_status") != "ready"
        ]
        not_ready_for_ai_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("is_ready_for_ai")
        ]
        venue_incomplete_sources = [
            row
            for row in coverage_rows
            if row.get("missing_recommended_venues")
        ]

        if non_ready_sources:
            flags.append("options_source_not_ready_present")
            notes.append(
                "当前仍有未 ready 的 options source: "
                f"{', '.join(non_ready_sources[:6])}"
                f"{' ...' if len(non_ready_sources) > 6 else ''}。"
            )
        if not_ready_for_ai_sources:
            flags.append("options_source_not_ready_for_ai_present")
            notes.append(
                "当前仍有 options source 虽然最近任务成功，但 latest 快照还不适合直接作为 AI 的期权证据: "
                f"{', '.join(not_ready_for_ai_sources[:6])}"
                f"{' ...' if len(not_ready_for_ai_sources) > 6 else ''}。"
            )

        if venue_incomplete_sources:
            flags.append("options_recommended_venue_coverage_incomplete")
            venue_notes = []
            for row in venue_incomplete_sources[:4]:
                missing_venues = ", ".join(row.get("missing_recommended_venues") or [])
                if row.get("observed_venue_count"):
                    venue_notes.append(
                        f"{row['source_name']} 缺少 {missing_venues}"
                    )
                else:
                    venue_notes.append(
                        f"{row['source_name']} 未暴露可识别 venue 身份"
                    )
            notes.append(
                "部分 options source 的 venue 覆盖仍不完整: "
                f"{'; '.join(venue_notes)}"
                f"{' ...' if len(venue_incomplete_sources) > 4 else ''}。"
            )

        if expected_entity_keys and missing_entity_keys:
            flags.append("options_entity_coverage_incomplete")
            notes.append(
                "当前 options context 只覆盖了 "
                f"{len(observed_entity_keys)}/{len(expected_entity_keys)} 个目标资产，"
                "缺少的资产有: "
                f"{', '.join(missing_entity_keys[:6])}"
                f"{' ...' if len(missing_entity_keys) > 6 else ''}。"
            )

        if expected_factor_ids and missing_factor_ids:
            flags.append("options_factor_coverage_incomplete")
            notes.append(
                "当前 options context 缺少部分设计内因子: "
                f"{', '.join(missing_factor_ids[:8])}"
                f"{' ...' if len(missing_factor_ids) > 8 else ''}。"
            )

        if (
            configured_universe_summary
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            flags.append("options_configured_market_breadth_limited")
            asset_count = int(configured_universe_summary.get("asset_entity_count") or 0)
            minimum_count = int(
                configured_universe_summary.get(
                    "minimum_asset_entity_count_for_market_breadth"
                )
                or 0
            )
            notes.append(
                "当前 options 默认资产宇宙只覆盖 "
                f"{asset_count} 个资产，仍偏向核心风险代理，"
                f"未达到用于更广市场 breadth 判断的建议门槛 {minimum_count}。"
            )

        if not assets:
            flags.append("options_context_empty")
            if raw_row_count > 0 and ai_excluded_source_count > 0:
                notes.append(
                    "当前 options 虽然已有真实已落库快照，但它们全部来自尚未达到 AI-ready 门槛的 source，"
                    "当前没有任何可直接给 AI 使用的期权证据。"
                )
            else:
                notes.append("当前 options context 没有任何最新快照，AI 不能把期权层证据视为已覆盖。")
            return flags, notes

        if quality_summary["partial_count"]:
            flags.append("options_partial_present")
            notes.append("latest options 快照里存在 partial 样本，说明部分期权结构字段尚未完整。")
        if quality_summary["fallback_count"]:
            flags.append("options_fallback_present")
            notes.append("latest options 快照里存在 fallback 样本，说明部分字段来自降级路径或近似值。")
        if quality_summary["stale_count"]:
            flags.append("options_stale_present")
            notes.append("latest options 快照里存在 stale 样本，不应把这些字段视为当前盘面。")
        if quality_summary["unknown_count"]:
            flags.append("options_unknown_quality_flag_present")
            notes.append("latest options 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")

        missing_vol_surface = self._missing_asset_count(
            assets,
            ("atm_iv_30d", "iv_term_structure_7d_30d"),
        )
        missing_relative_value = self._missing_asset_count(
            assets,
            ("realized_vol_30d", "iv_rv_spread_30d"),
        )
        missing_strike_concentration = self._missing_asset_count(
            assets,
            ("top_strike_oi_share", "max_pain_distance_pct"),
        )
        missing_gamma_exposure = self._missing_asset_count(
            assets,
            ("net_gamma_exposure_ratio", "gamma_flip_distance_pct"),
        )
        missing_flow_activity = self._missing_asset_count(
            assets,
            ("net_call_premium_flow_ratio", "opening_flow_share"),
        )
        missing_expiry_structure = self._missing_asset_count(
            assets,
            ("oi_share_30d", "gamma_share_7d"),
        )
        missing_hedge_pressure = self._missing_asset_count(
            assets,
            (
                "vanna_exposure_ratio",
                "charm_flip_distance_pct",
                "volga_exposure_ratio",
                "vomma_exposure_ratio",
                "color_exposure_ratio",
                "near_expiry_color_share",
            ),
        )
        missing_positioning = self._missing_asset_count(
            assets,
            ("put_call_oi_ratio_30d", "total_oi_notional_30d"),
        )
        if missing_vol_surface:
            flags.append(f"missing_vol_surface_for_{missing_vol_surface}_assets")
            notes.append("部分资产缺少 ATM IV 或期限结构，AI 对未来波动定价的判断会变弱。")
        if missing_relative_value:
            flags.append(f"missing_relative_value_for_{missing_relative_value}_assets")
            notes.append("部分资产缺少 IV 相对已实现波动率证据，AI 难以判断期权是否被高估。")
        if missing_strike_concentration:
            flags.append(
                f"missing_strike_concentration_for_{missing_strike_concentration}_assets"
            )
            notes.append("部分资产缺少 max pain 或行权价拥挤度证据，AI 无法判断 pinning 和墙位压力。")
        if missing_gamma_exposure:
            flags.append(f"missing_gamma_exposure_for_{missing_gamma_exposure}_assets")
            notes.append("部分资产缺少 net gamma 或 gamma flip 证据，AI 无法判断 long gamma / short gamma 状态与被动对冲风险。")
        if missing_flow_activity:
            flags.append(f"missing_flow_activity_for_{missing_flow_activity}_assets")
            notes.append("部分资产缺少期权增量成交流证据，AI 看不到当前是追涨、买保护还是新开仓。")
        if missing_expiry_structure:
            flags.append(f"missing_expiry_structure_for_{missing_expiry_structure}_assets")
            notes.append("部分资产缺少按到期桶拆分的期限结构证据，AI 无法判断风险究竟堆在 7d、30d 还是长端。")
        if missing_hedge_pressure:
            flags.append(f"missing_hedge_pressure_for_{missing_hedge_pressure}_assets")
            notes.append("部分资产缺少 vanna / charm / volga / vomma / color 对冲压力证据，AI 无法判断波动率变化、波动率凸性冲击和 gamma 随时间衰减会把 dealer 推向哪边。")
        if missing_positioning:
            flags.append(f"missing_positioning_for_{missing_positioning}_assets")
            notes.append("部分资产缺少期权持仓结构数据，AI 无法完整识别到期拥挤和保护需求。")
        if (
            not requested_entity_keys
            and len(expected_entity_keys) > 1
            and len(assets) <= 1
        ):
            flags.append("narrow_asset_coverage")
            notes.append("当前 options context 只覆盖极少数资产，横向比较能力不足。")
        return flags, notes

    def load_latest_context_bundle(
        self,
        entity_keys: list[str] | None = None,
        factor_ids: list[str] | None = None,
        source_names: list[str] | None = None,
    ) -> dict:
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        normalized_source_names = self._normalize_source_names(
            source_names=source_names,
            factor_ids=factor_ids,
        )
        raw_rows = self.load_latest_context(
            entity_keys=normalized_entity_keys,
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
        )
        parsed_rows: list[dict] = []
        for row in raw_rows:
            parsed_rows.append(
                {
                    **row,
                    "observation_time_dt": self._parse_db_timestamp(row.get("observation_time")),
                    "collected_at_dt": self._parse_db_timestamp(row.get("collected_at")),
                    "dimensions_json": self._loads_json(row.get("dimensions_json")) or {},
                    "raw_payload": self._loads_json(row.get("raw_payload_json")) or {},
                }
            )
        raw_preferred_rows = self._select_preferred_context_rows(parsed_rows)
        factor_definitions = load_options_factors(
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
            enabled_only=False,
        )
        expected_factor_ids = [
            factor.factor_id
            for factor in factor_definitions
        ]
        entity_meta_rows = load_options_entities(
            source_names=normalized_source_names,
            entity_keys=normalized_entity_keys,
        )
        expected_entity_keys = sorted(
            {
                str(row["entity_key"])
                for row in entity_meta_rows
            }
        )
        configured_universe_summary = self._build_configured_universe_summary(
            configured_entity_keys=expected_entity_keys,
            requested_entity_keys=normalized_entity_keys,
            requested_factor_ids=normalized_factor_ids,
            requested_source_names=normalized_source_names if source_names else None,
        )
        entity_name_map = {
            (str(row["source_name"]), str(row["entity_key"])): {
                "name": str(row["name"]),
                "description": str(row.get("description") or ""),
            }
            for row in entity_meta_rows
        }
        coverage = self.load_source_coverage(
            source_names=normalized_source_names,
            factor_ids=normalized_factor_ids,
            entity_keys=normalized_entity_keys,
        )
        coverage_rows = coverage.get("sources", [])
        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=raw_preferred_rows,
            coverage_rows=coverage_rows,
        )
        preferred_rows = [
            row
            for row in raw_preferred_rows
            if str(row["source_name"]) in ai_ready_source_names
        ]
        observed_factor_ids = {
            str(row["factor_id"])
            for row in preferred_rows
        }
        raw_observed_factor_ids = {
            str(row["factor_id"])
            for row in raw_preferred_rows
        }
        quality_summary = summarize_quality_flag_counts(preferred_rows)
        raw_quality_summary = summarize_quality_flag_counts(raw_preferred_rows)
        assets = self._build_combined_assets(preferred_rows, entity_name_map)
        latest_observation_time = self._latest_observation_time(preferred_rows)
        raw_latest_observation_time = self._latest_observation_time(raw_preferred_rows)
        source_counts = self._count_rows_by_source(preferred_rows)
        raw_source_counts = self._count_rows_by_source(raw_preferred_rows)
        source_health = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "recommended_venues": row["recommended_venues"],
                "observed_venues": row["observed_venues"],
                "missing_recommended_venues": row["missing_recommended_venues"],
                "recommended_venue_count": row["recommended_venue_count"],
                "observed_venue_count": row["observed_venue_count"],
                "venue_coverage_ratio": row["venue_coverage_ratio"],
                "is_venue_coverage_complete": row["is_venue_coverage_complete"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "quality_notes": row["quality_notes"],
            }
            for row in coverage_rows
        ]
        missing_entity_keys = [
            entity_key
            for entity_key in expected_entity_keys
            if entity_key not in {
                str(asset["entity_key"])
                for asset in assets
            }
        ]
        missing_factor_ids = [
            factor_id
            for factor_id in expected_factor_ids
            if factor_id not in observed_factor_ids
        ]
        data_quality_flags, quality_notes = self._build_context_quality(
            assets=assets,
            raw_row_count=len(raw_preferred_rows),
            ai_excluded_source_count=len(ai_excluded_sources),
            expected_entity_keys=expected_entity_keys,
            expected_factor_ids=expected_factor_ids,
            observed_factor_ids=observed_factor_ids,
            quality_summary=quality_summary,
            coverage_rows=coverage_rows,
            requested_entity_keys=normalized_entity_keys,
            configured_universe_summary=configured_universe_summary,
        )
        raw_observed_entity_keys = sorted(
            {
                str(row["entity_key"])
                for row in raw_preferred_rows
            }
        )
        sources: dict[str, dict] = {}
        source_context_builders = {
            "vol_surface": self._build_vol_surface_context,
            "relative_value": self._build_relative_value_context,
            "strike_concentration": self._build_strike_concentration_context,
            "gamma_exposure": self._build_gamma_exposure_context,
            "flow_activity": self._build_flow_activity_context,
            "expiry_structure": self._build_expiry_structure_context,
            "hedge_pressure": self._build_hedge_pressure_context,
            "positioning": self._build_positioning_context,
        }
        for source_name, builder in source_context_builders.items():
            if source_name not in ai_ready_source_names:
                continue
            sources[source_name] = builder(assets)
        return {
            "as_of": latest_observation_time.isoformat() if latest_observation_time else None,
            "raw_as_of": raw_latest_observation_time.isoformat() if raw_latest_observation_time else None,
            "row_count": len(preferred_rows),
            "raw_row_count": len(raw_preferred_rows),
            "entity_count": len(assets),
            "raw_entity_count": len(raw_observed_entity_keys),
            "source_counts": source_counts,
            "raw_source_counts": raw_source_counts,
            "ai_ready_source_names": sorted(ai_ready_source_names),
            "ai_excluded_source_names": [
                str(item["source_name"])
                for item in ai_excluded_sources
            ],
            "ai_excluded_sources": ai_excluded_sources,
            "configured_universe_summary": configured_universe_summary,
            "coverage_summary": {
                "expected_entity_count": len(expected_entity_keys),
                "observed_entity_count": len(assets),
                "raw_observed_entity_count": len(raw_observed_entity_keys),
                "expected_factor_count": len(expected_factor_ids),
                "observed_factor_count": len(observed_factor_ids),
                "raw_observed_factor_count": len(raw_observed_factor_ids),
                "expected_point_count": (
                    len(expected_entity_keys) * len(expected_factor_ids)
                    if expected_entity_keys and expected_factor_ids
                    else None
                ),
                "observed_point_count": len(preferred_rows),
                "raw_observed_point_count": len(raw_preferred_rows),
                "missing_entity_keys": missing_entity_keys,
                "missing_factor_ids": missing_factor_ids,
            },
            "latest_quality_flag_breakdown": quality_summary["breakdown"],
            "latest_ok_point_count": quality_summary["ok_count"],
            "latest_partial_point_count": quality_summary["partial_count"],
            "latest_fallback_point_count": quality_summary["fallback_count"],
            "latest_stale_point_count": quality_summary["stale_count"],
            "latest_unknown_quality_point_count": quality_summary["unknown_count"],
            "latest_non_ok_point_count": quality_summary["non_ok_count"],
            "latest_quality_ready_ratio": quality_summary["ready_ratio"],
            "raw_latest_quality_flag_breakdown": raw_quality_summary["breakdown"],
            "raw_latest_quality_ready_ratio": raw_quality_summary["ready_ratio"],
            "source_health_summary": {
                "source_count": coverage.get("source_count", 0),
                "ready_source_count": coverage.get("ready_source_count", 0),
                "problem_source_count": coverage.get("problem_source_count", 0),
                "stale_source_count": coverage.get("stale_source_count", 0),
                "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
            },
            "venue_coverage_summary": coverage.get("venue_coverage_summary") or {},
            "source_health": source_health,
            "leaders": {
                "highest_atm_iv_30d": self._pick_leader(assets, field_name="atm_iv_30d"),
                "steepest_short_term_iv": self._pick_leader(
                    assets,
                    field_name="iv_term_structure_7d_30d",
                ),
                "most_put_skewed": self._pick_leader(
                    assets,
                    field_name="risk_reversal_25d_30d",
                    reverse=False,
                ),
                "closest_max_pain_to_spot": self._pick_smallest_abs(
                    assets,
                    field_name="max_pain_distance_pct",
                ),
                "richest_iv_vs_rv_30d": self._pick_leader(
                    assets,
                    field_name="iv_rv_spread_30d",
                ),
                "cheapest_iv_vs_rv_30d": self._pick_leader(
                    assets,
                    field_name="iv_rv_spread_30d",
                    reverse=False,
                ),
                "most_positive_net_gamma_ratio": self._pick_leader(
                    assets,
                    field_name="net_gamma_exposure_ratio",
                ),
                "most_negative_net_gamma_ratio": self._pick_leader(
                    assets,
                    field_name="net_gamma_exposure_ratio",
                    reverse=False,
                ),
                "closest_gamma_flip_to_spot": self._pick_smallest_abs(
                    assets,
                    field_name="gamma_flip_distance_pct",
                ),
                "most_call_buyer_dominated": self._pick_leader(
                    assets,
                    field_name="call_buyer_premium_share",
                ),
                "most_put_buyer_dominated": self._pick_leader(
                    assets,
                    field_name="put_buyer_premium_share",
                ),
                "most_bullish_net_call_flow": self._pick_leader(
                    assets,
                    field_name="net_call_premium_flow_ratio",
                ),
                "most_bearish_net_put_flow": self._pick_leader(
                    assets,
                    field_name="net_put_premium_flow_ratio",
                ),
                "highest_oi_share_7d": self._pick_leader(
                    assets,
                    field_name="oi_share_7d",
                ),
                "highest_oi_share_90d_plus": self._pick_leader(
                    assets,
                    field_name="oi_share_90d_plus",
                ),
                "highest_gamma_share_7d": self._pick_leader(
                    assets,
                    field_name="gamma_share_7d",
                ),
                "highest_gamma_share_30d": self._pick_leader(
                    assets,
                    field_name="gamma_share_30d",
                ),
                "most_positive_vanna_ratio": self._pick_leader(
                    assets,
                    field_name="vanna_exposure_ratio",
                ),
                "most_negative_vanna_ratio": self._pick_leader(
                    assets,
                    field_name="vanna_exposure_ratio",
                    reverse=False,
                ),
                "closest_vanna_flip_to_spot": self._pick_smallest_abs(
                    assets,
                    field_name="vanna_flip_distance_pct",
                ),
                "closest_charm_flip_to_spot": self._pick_smallest_abs(
                    assets,
                    field_name="charm_flip_distance_pct",
                ),
                "most_positive_volga_ratio": self._pick_leader(
                    assets,
                    field_name="volga_exposure_ratio",
                ),
                "most_negative_volga_ratio": self._pick_leader(
                    assets,
                    field_name="volga_exposure_ratio",
                    reverse=False,
                ),
                "most_positive_vomma_ratio": self._pick_leader(
                    assets,
                    field_name="vomma_exposure_ratio",
                ),
                "most_negative_vomma_ratio": self._pick_leader(
                    assets,
                    field_name="vomma_exposure_ratio",
                    reverse=False,
                ),
                "largest_abs_color_ratio": self._pick_largest_abs(
                    assets,
                    field_name="color_exposure_ratio",
                ),
                "highest_near_expiry_color_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_color_share",
                ),
                "highest_put_call_oi_ratio": self._pick_leader(
                    assets,
                    field_name="put_call_oi_ratio_30d",
                ),
                "largest_total_oi_notional": self._pick_leader(
                    assets,
                    field_name="total_oi_notional_30d",
                ),
                "highest_top_strike_oi_share": self._pick_leader(
                    assets,
                    field_name="top_strike_oi_share",
                ),
                "highest_top_gamma_strike_share": self._pick_leader(
                    assets,
                    field_name="top_gamma_strike_share",
                ),
                "highest_near_expiry_top_strike_oi_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_top_strike_oi_share",
                ),
                "highest_near_expiry_gamma_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_gamma_share",
                ),
                "highest_premium_flow_share_7d": self._pick_leader(
                    assets,
                    field_name="premium_flow_share_7d",
                ),
                "highest_premium_flow_share_30d": self._pick_leader(
                    assets,
                    field_name="premium_flow_share_30d",
                ),
                "highest_near_expiry_charm_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_charm_share",
                ),
                "highest_opening_flow_share": self._pick_leader(
                    assets,
                    field_name="opening_flow_share",
                ),
                "highest_near_expiry_flow_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_flow_share",
                ),
                "highest_block_trade_flow_share": self._pick_leader(
                    assets,
                    field_name="block_trade_flow_share",
                ),
                "highest_near_expiry_oi_share": self._pick_leader(
                    assets,
                    field_name="near_expiry_oi_share",
                ),
            },
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
            "assets": assets,
            "sources": sources,
        }

    def load_source_coverage(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict:
        normalized_source_names = self._normalize_source_names(
            source_names=source_names,
            factor_ids=factor_ids,
        )
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        sources = load_options_sources(
            source_names=normalized_source_names,
            enabled_only=False,
        )
        if not sources:
            return {
                "generated_at": self._utc_now_naive().isoformat(),
                "source_count": 0,
                "sources": [],
            }
        source_name_list = [source.source_name for source in sources]
        placeholders = ",".join("?" for _ in source_name_list)
        latest_clauses = [f"source_name IN ({placeholders})"]
        latest_params: list[str] = list(source_name_list)
        if normalized_factor_ids:
            factor_placeholders = ",".join("?" for _ in normalized_factor_ids)
            latest_clauses.append(f"factor_id IN ({factor_placeholders})")
            latest_params.extend(normalized_factor_ids)
        if normalized_entity_keys:
            entity_placeholders = ",".join("?" for _ in normalized_entity_keys)
            latest_clauses.append(f"entity_key IN ({entity_placeholders})")
            latest_params.extend(normalized_entity_keys)
        latest_where_sql = f"WHERE {' AND '.join(latest_clauses)}"
        latest_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                COUNT(*) AS latest_point_count,
                COUNT(DISTINCT entity_key) AS latest_entity_count,
                COUNT(DISTINCT factor_id) AS latest_factor_count,
                MAX(observation_time) AS latest_observation_time
            FROM latest_options_timeseries
            {latest_where_sql}
            GROUP BY source_name
            """,
            tuple(latest_params),
        )
        latest_map = {str(row["source_name"]): dict(row) for row in latest_rows}
        quality_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                quality_flag,
                COUNT(*) AS point_count
            FROM latest_options_timeseries
            {latest_where_sql}
            GROUP BY source_name, quality_flag
            """,
            tuple(latest_params),
        )
        quality_counts_map: dict[str, dict[str, int]] = {}
        for row in quality_rows:
            source_name = str(row["source_name"])
            quality_flag = str(row["quality_flag"] or "")
            quality_counts_map.setdefault(source_name, {})[quality_flag] = int(
                row["point_count"] or 0
            )
        venue_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                dimensions_json,
                raw_payload_json
            FROM latest_options_timeseries
            {latest_where_sql}
            """,
            tuple(latest_params),
        )
        venue_rows_by_source: dict[str, list[dict]] = {}
        for row in venue_rows:
            venue_rows_by_source.setdefault(str(row["source_name"]), []).append(dict(row))
        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'options_data'
                  AND source_name IN ({placeholders})
                GROUP BY source_name
            ) AS latest
                ON runs.id = latest.latest_id
            """,
            tuple(source_name_list),
        )
        run_map = {str(row["source_name"]): dict(row) for row in run_rows}
        entity_registry_rows = load_options_entities(
            source_names=normalized_source_names,
            entity_keys=normalized_entity_keys,
        )
        expected_entity_counts: dict[str, int] = {}
        for row in entity_registry_rows:
            source_name = str(row["source_name"])
            expected_entity_counts[source_name] = expected_entity_counts.get(source_name, 0) + 1
        factor_counts: dict[str, int] = {}
        for factor in load_options_factors(
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
            enabled_only=False,
        ):
            factor_counts[factor.source_name] = factor_counts.get(factor.source_name, 0) + 1

        rows = []
        now = self._utc_now_naive()
        for source in sources:
            latest_meta = latest_map.get(source.source_name, {})
            run_meta = run_map.get(source.source_name, {})
            quality_summary = summarize_quality_flag_counts(
                quality_counts_map.get(source.source_name, {})
            )
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = (
                datetime.fromisoformat(last_run_finished_at)
                if last_run_finished_at
                else None
            )
            interval_seconds = self._source_interval_seconds(source.source_name)
            is_stale = last_run_dt is None or (now - last_run_dt).total_seconds() > interval_seconds * 3
            configuration_ready = bool(source.endpoint)
            health_status = resolve_source_health_status(
                enabled=bool(source.enabled),
                configuration_ready=configuration_ready,
                last_run_status=run_meta.get("status"),
                latest_point_count=int(latest_meta.get("latest_point_count") or 0),
                is_stale=is_stale,
            )
            quality_notes: list[str] = []
            quality_flags: list[str] = []
            if source.raw_meta.get("recommended_venues"):
                quality_notes.append(
                    "建议标准化链路至少聚合 Deribit、OKX、Binance 等主流期权流动性场所。"
                )
            expected_factor_count = factor_counts.get(source.source_name, 0)
            latest_factor_count = int(latest_meta.get("latest_factor_count") or 0)
            expected_entity_count = expected_entity_counts.get(source.source_name, 0)
            latest_entity_count = int(latest_meta.get("latest_entity_count") or 0)
            recommended_venues = list(source.raw_meta.get("recommended_venues") or [])
            observed_venues = self._extract_observed_venues_from_rows(
                venue_rows_by_source.get(source.source_name, []),
                recommended_venues,
            )
            missing_recommended_venues = [
                venue
                for venue in recommended_venues
                if venue not in observed_venues
            ]
            recommended_venue_count = len(recommended_venues)
            observed_venue_count = len(observed_venues)
            venue_coverage_ratio = (
                observed_venue_count / recommended_venue_count
                if recommended_venue_count
                else None
            )
            if latest_factor_count and expected_factor_count and latest_factor_count < expected_factor_count:
                quality_flags.append("factor_coverage_incomplete")
                quality_notes.append("当前已落库 factor 数少于设计目标，AI 看到的期权结构仍不完整。")
            if latest_entity_count and expected_entity_count and latest_entity_count < expected_entity_count:
                quality_flags.append("entity_coverage_incomplete")
                quality_notes.append("当前资产覆盖少于注册表目标，AI 只看到了部分币种的期权证据。")
            if recommended_venue_count and not observed_venue_count:
                quality_flags.append("venue_identity_missing")
                quality_notes.append(
                    "当前 latest 快照没有暴露可识别的 venue 身份，AI 无法判断这些期权信号是否覆盖主流流动性场所。"
                )
            elif missing_recommended_venues:
                quality_flags.append("recommended_venue_coverage_incomplete")
                quality_notes.append(
                    "当前 latest 快照缺少部分推荐 venue 的可见证据: "
                    f"{', '.join(missing_recommended_venues[:6])}"
                    f"{' ...' if len(missing_recommended_venues) > 6 else ''}。"
                )
            elif recommended_venues:
                quality_notes.append(
                    "当前 latest 快照已识别推荐 venue 覆盖: "
                    f"{', '.join(observed_venues)}。"
                )
            if source.source_name == "relative_value":
                quality_notes.append("IV-RV spread 是判断期权定价是否偏贵的关键证据，建议不要长期缺失。")
            if source.source_name == "strike_concentration":
                quality_notes.append("行权价墙位与 max pain 是短线 pinning / breakout 风险的重要证据，建议不要长期缺失。")
            if source.source_name == "gamma_exposure":
                quality_notes.append("dealer gamma regime 与 gamma flip 是短线交易判断的重要证据，建议不要长期缺失。")
            if source.source_name == "flow_activity":
                quality_notes.append("期权增量成交流和开仓意图是短线情绪切换的重要证据，建议不要长期缺失。")
            if source.source_name == "expiry_structure":
                quality_notes.append("按到期桶拆分的 OI、gamma 与 flow 是判断事件窗和 back-end 风险分布的重要证据，建议不要长期缺失。")
            if source.source_name == "hedge_pressure":
                quality_notes.append("vanna / charm / volga / vomma / color 是判断 dealer 动态对冲压力和二次放大的重要证据，建议不要长期缺失。")
            is_ready_for_ai = self._is_source_ready_for_ai(
                health_status=health_status,
                expected_entity_count=expected_entity_count,
                latest_entity_count=latest_entity_count,
                expected_factor_count=expected_factor_count,
                latest_factor_count=latest_factor_count,
                recommended_venue_count=recommended_venue_count,
                missing_recommended_venues=missing_recommended_venues,
                quality_summary=quality_summary,
            )
            if health_status == "ready" and not is_ready_for_ai:
                quality_notes.append(
                    "当前 source 虽然最近运行成功，但 latest 快照仍未达到可直接给 AI 使用的质量门槛。"
                )
            if quality_summary["partial_count"]:
                quality_flags.append("partial_points_present")
                quality_notes.append("latest 快照里存在 partial 期权样本，说明部分期权结构字段尚未完整。")
            if quality_summary["fallback_count"]:
                quality_flags.append("fallback_points_present")
                quality_notes.append("latest 快照里存在 fallback 期权样本，说明部分字段来自降级路径或近似值。")
            if quality_summary["stale_count"]:
                quality_flags.append("stale_points_present")
                quality_notes.append("latest 快照里存在 stale 期权样本，即使最近任务成功也不应视为当前盘面。")
            if quality_summary["unknown_count"]:
                quality_flags.append("unknown_quality_flag_present")
                quality_notes.append("latest 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")
            rows.append(
                {
                    "source_name": source.source_name,
                    "name": source.name,
                    "collector_key": source.collector_key,
                    "primary_factor_id": source.primary_factor_id,
                    "entity_type": source.entity_type,
                    "default_interval": source.default_interval,
                    "enabled": source.enabled,
                    "endpoint": source.endpoint,
                    "phase": source.raw_meta.get("phase"),
                    "semantic_scope": source.raw_meta.get("semantic_scope"),
                    "recommended_venues": recommended_venues,
                    "observed_venues": observed_venues,
                    "missing_recommended_venues": missing_recommended_venues,
                    "recommended_venue_count": recommended_venue_count,
                    "observed_venue_count": observed_venue_count,
                    "venue_coverage_ratio": venue_coverage_ratio,
                    "is_venue_coverage_complete": (
                        bool(recommended_venue_count)
                        and not missing_recommended_venues
                    ),
                    "configuration_ready": configuration_ready,
                    "expected_entity_count": expected_entity_count,
                    "expected_factor_count": expected_factor_count,
                    "latest_entity_count": latest_entity_count,
                    "latest_factor_count": latest_factor_count,
                    "latest_point_count": int(latest_meta.get("latest_point_count") or 0),
                    "latest_observation_time": latest_meta.get("latest_observation_time"),
                    "last_run_status": run_meta.get("status"),
                    "last_run_item_count": int(run_meta.get("item_count") or 0),
                    "last_run_finished_at": run_meta.get("finished_at"),
                    "last_run_message": run_meta.get("message"),
                    "last_run_metadata": self._loads_json(run_meta.get("metadata_json")),
                    "is_stale": is_stale,
                    "health_status": health_status,
                    "is_ready_for_ai": is_ready_for_ai,
                    "latest_quality_flag_breakdown": quality_summary["breakdown"],
                    "latest_ok_point_count": quality_summary["ok_count"],
                    "latest_partial_point_count": quality_summary["partial_count"],
                    "latest_fallback_point_count": quality_summary["fallback_count"],
                    "latest_stale_point_count": quality_summary["stale_count"],
                    "latest_unknown_quality_point_count": quality_summary["unknown_count"],
                    "latest_non_ok_point_count": quality_summary["non_ok_count"],
                    "latest_quality_ready_ratio": quality_summary["ready_ratio"],
                    "data_quality_flags": quality_flags,
                    "quality_notes": quality_notes,
                }
            )
        rows.sort(key=lambda item: (item["health_status"] != "ready", item["is_stale"], item["source_name"]))
        health_summary = summarize_health_rows(rows)
        venue_coverage_summary = self._build_venue_coverage_summary(rows)
        ready_for_ai_source_count = sum(
            1
            for item in rows
            if item["is_ready_for_ai"]
        )
        return {
            "generated_at": now.isoformat(),
            "source_count": len(rows),
            "stale_source_count": sum(1 for item in rows if item["is_stale"]),
            "total_latest_entity_count": sum(item["latest_entity_count"] for item in rows),
            "total_latest_point_count": sum(item["latest_point_count"] for item in rows),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
            "venue_coverage_summary": venue_coverage_summary,
            **health_summary,
            "sources": rows,
        }

    def _run_source_job(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ):
        local_db = DBManager(self.db.db_path)
        local_service = OptionsDataService(client=self.client, db=local_db)
        try:
            return local_service.collect_once(
                source_names=[source_name],
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        finally:
            local_service.close()

    def build_scheduler(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        enabled_sources = {source.source_name for source in load_options_sources()}
        source_config = {
            "vol_surface": OPTIONS_CONFIG["vol_surface_interval_seconds"],
            "relative_value": OPTIONS_CONFIG["relative_value_interval_seconds"],
            "strike_concentration": OPTIONS_CONFIG["strike_concentration_interval_seconds"],
            "gamma_exposure": OPTIONS_CONFIG["gamma_exposure_interval_seconds"],
            "flow_activity": OPTIONS_CONFIG["flow_activity_interval_seconds"],
            "expiry_structure": OPTIONS_CONFIG["expiry_structure_interval_seconds"],
            "hedge_pressure": OPTIONS_CONFIG["hedge_pressure_interval_seconds"],
            "positioning": OPTIONS_CONFIG["positioning_interval_seconds"],
        }
        source_titles = {
            "vol_surface": "期权隐含波动率曲面采集",
            "relative_value": "期权 IV 相对 realized vol 采集",
            "strike_concentration": "期权墙位与行权价拥挤度采集",
            "gamma_exposure": "期权 gamma regime 采集",
            "flow_activity": "期权增量成交流采集",
            "expiry_structure": "期权到期桶期限结构采集",
            "hedge_pressure": "期权动态对冲压力采集",
            "positioning": "期权持仓结构采集",
        }
        for source_name, interval_seconds in source_config.items():
            if source_name not in enabled_sources:
                continue
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=interval_seconds,
                id=f"options_{source_name}",
                name=source_titles[source_name],
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, interval_seconds),
                kwargs={
                    "source_name": source_name,
                    "entity_keys": self._normalize_entity_keys(entity_keys),
                    "interval": interval or OPTIONS_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or OPTIONS_CONFIG["default_lookback_hours"],
                },
            )
        return scheduler

    def close(self):
        self.db.close()
