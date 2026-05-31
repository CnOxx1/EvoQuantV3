import json
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from config.settings import ONCHAIN_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import (
    is_quality_summary_ai_ready,
    resolve_source_health_status,
    summarize_health_rows,
    summarize_quality_flag_counts,
)
from data_layer.onchain_data.bridge_netflow import BridgeNetflowCollector
from data_layer.onchain_data.client import OnchainDataClient
from data_layer.onchain_data.collectors.exchange_flow import ExchangeFlowCollector
from data_layer.onchain_data.collectors.stablecoin_flow import StablecoinFlowCollector
from data_layer.onchain_data.collectors.whale_activity import WhaleActivityCollector
from data_layer.onchain_data.defi_yields import DefiYieldsCollector
from data_layer.onchain_data.dex_volume.collector import DexVolumeCollector
from data_layer.onchain_data.exchange_reserve import ExchangeReserveCollector
from data_layer.onchain_data.global_market import GlobalMarketCollector
from data_layer.onchain_data.market_sentiment import MarketSentimentCollector
from data_layer.onchain_data.models import OnchainTimeSeriesPoint
from data_layer.onchain_data.network_usage import NetworkUsageCollector
from data_layer.onchain_data.protocol_tvl import ProtocolTVLCollector
from data_layer.onchain_data.stablecoin_supply.collector import StablecoinSupplyCollector
from data_layer.onchain_data.staking_flow import StakingFlowCollector
from data_layer.onchain_data.sources import (
    load_onchain_entities,
    load_onchain_factors,
    load_onchain_sources,
)


class OnchainDataService:
    """链上数据模块统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    MINIMUM_MARKET_BREADTH_THRESHOLDS = {
        "asset": 6,
        "chain": 8,
        "stablecoin_asset": 4,
        "protocol": 6,
    }

    def __init__(
        self,
        client: OnchainDataClient | None = None,
        db: DBManager | None = None,
        exchange_flow_collector: ExchangeFlowCollector | None = None,
        whale_activity_collector: WhaleActivityCollector | None = None,
        stablecoin_flow_collector: StablecoinFlowCollector | None = None,
        bridge_netflow_collector: BridgeNetflowCollector | None = None,
        exchange_reserve_collector: ExchangeReserveCollector | None = None,
        protocol_tvl_collector: ProtocolTVLCollector | None = None,
        network_usage_collector: NetworkUsageCollector | None = None,
        staking_flow_collector: StakingFlowCollector | None = None,
        dex_volume_collector: DexVolumeCollector | None = None,
        stablecoin_supply_collector: StablecoinSupplyCollector | None = None,
        market_sentiment_collector: MarketSentimentCollector | None = None,
        global_market_collector: GlobalMarketCollector | None = None,
        defi_yields_collector: DefiYieldsCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or OnchainDataClient()
        self.exchange_flow_collector = exchange_flow_collector or ExchangeFlowCollector(
            self.client
        )
        self.whale_activity_collector = whale_activity_collector or WhaleActivityCollector(
            self.client
        )
        self.stablecoin_flow_collector = stablecoin_flow_collector or StablecoinFlowCollector(
            self.client
        )
        self.bridge_netflow_collector = bridge_netflow_collector or BridgeNetflowCollector(
            self.client
        )
        self.exchange_reserve_collector = exchange_reserve_collector or ExchangeReserveCollector(
            self.client
        )
        self.protocol_tvl_collector = protocol_tvl_collector or ProtocolTVLCollector(
            self.client
        )
        self.network_usage_collector = network_usage_collector or NetworkUsageCollector(
            self.client
        )
        self.staking_flow_collector = staking_flow_collector or StakingFlowCollector(
            self.client
        )
        self.dex_volume_collector = dex_volume_collector or DexVolumeCollector(
            self.client
        )
        self.stablecoin_supply_collector = stablecoin_supply_collector or StablecoinSupplyCollector(
            self.client
        )
        self.market_sentiment_collector = market_sentiment_collector or MarketSentimentCollector(
            self.client
        )
        self.global_market_collector = global_market_collector or GlobalMarketCollector(
            self.client
        )
        self.defi_yields_collector = defi_yields_collector or DefiYieldsCollector(
            self.client
        )

    @staticmethod
    def _quality_rank(point: OnchainTimeSeriesPoint) -> tuple:
        quality_rank = {
            "ok": 3,
            "partial": 2,
            "fallback": 1,
            "stale": 0,
        }
        return (
            point.observation_time,
            quality_rank.get(point.quality_flag, -1),
            point.collected_at,
        )

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _expected_point_count(
        expected_entity_count: int,
        expected_factor_count: int,
    ) -> int:
        return int(expected_entity_count or 0) * int(expected_factor_count or 0)

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
                            (str(row["entity_type"]), str(row["entity_key"]))
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
                            row["observation_time"]
                            for row in source_rows
                            if row.get("observation_time")
                        ),
                        default=None,
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

    @classmethod
    def _is_source_ready_for_ai(
        cls,
        *,
        health_status: str,
        expected_entity_count: int,
        latest_entity_count: int,
        expected_factor_count: int,
        latest_factor_count: int,
        expected_point_count: int,
        latest_point_count: int,
        quality_summary: dict[str, object],
    ) -> bool:
        if health_status != "ready":
            return False
        if not is_quality_summary_ai_ready(quality_summary):
            return False
        if expected_entity_count and latest_entity_count < expected_entity_count:
            return False
        if expected_factor_count and latest_factor_count < expected_factor_count:
            return False
        if expected_point_count and latest_point_count < expected_point_count:
            return False
        return True

    @staticmethod
    def _history_identity(point: OnchainTimeSeriesPoint) -> tuple:
        return (
            point.factor_id,
            point.entity_type,
            point.entity_key,
            point.interval,
            point.observation_time,
            point.dimensions_key,
            point.source_name,
            point.config_version,
        )

    @staticmethod
    def _latest_identity(point: OnchainTimeSeriesPoint) -> tuple:
        return (
            point.factor_id,
            point.entity_type,
            point.entity_key,
            point.interval,
            point.dimensions_key,
            point.source_name,
            point.config_version,
        )

    def _deduplicate_history_points(
        self,
        points: list[OnchainTimeSeriesPoint],
    ) -> list[OnchainTimeSeriesPoint]:
        deduped: dict[tuple, OnchainTimeSeriesPoint] = {}
        for point in points:
            key = self._history_identity(point)
            previous = deduped.get(key)
            if previous is None or self._quality_rank(point) >= self._quality_rank(previous):
                deduped[key] = point
        return list(deduped.values())

    def _deduplicate_latest_points(
        self,
        points: list[OnchainTimeSeriesPoint],
    ) -> list[OnchainTimeSeriesPoint]:
        deduped: dict[tuple, OnchainTimeSeriesPoint] = {}
        for point in points:
            key = self._latest_identity(point)
            previous = deduped.get(key)
            if previous is None or self._quality_rank(point) >= self._quality_rank(previous):
                deduped[key] = point
        return list(deduped.values())

    def init_storage(self):
        self.db.init_market_data_tables()
        self.sync_factor_catalog()

    def sync_factor_catalog(self):
        factors = load_onchain_factors(enabled_only=False)
        if not factors:
            return
        sql = """
            INSERT INTO onchain_factor_catalog (
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

    def save_to_db(self, points: list[OnchainTimeSeriesPoint]):
        points = self._deduplicate_history_points(points)
        if not points:
            return

        history_sql = """
            INSERT INTO onchain_timeseries (
                factor_id, category, factor_type, entity_type, entity_key,
                interval, observation_time, value, unit, quality_flag,
                dimensions_key, dimensions_json, config_version, source_name,
                source_symbol, raw_payload_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                factor_id, entity_type, entity_key, interval, observation_time,
                dimensions_key, source_name, config_version
            ) DO UPDATE SET
                category=excluded.category,
                factor_type=excluded.factor_type,
                value=excluded.value,
                unit=excluded.unit,
                quality_flag=excluded.quality_flag,
                dimensions_json=excluded.dimensions_json,
                source_symbol=excluded.source_symbol,
                raw_payload_json=excluded.raw_payload_json,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
        """
        latest_sql = """
            INSERT INTO latest_onchain_timeseries (
                factor_id, category, factor_type, entity_type, entity_key,
                interval, observation_time, value, unit, quality_flag,
                dimensions_key, dimensions_json, config_version, source_name,
                source_symbol, raw_payload_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                factor_id, entity_type, entity_key, interval, dimensions_key,
                source_name, config_version
            ) DO UPDATE SET
                category=excluded.category,
                factor_type=excluded.factor_type,
                observation_time=excluded.observation_time,
                value=excluded.value,
                unit=excluded.unit,
                quality_flag=excluded.quality_flag,
                dimensions_json=excluded.dimensions_json,
                source_symbol=excluded.source_symbol,
                raw_payload_json=excluded.raw_payload_json,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.observation_time >= latest_onchain_timeseries.observation_time
        """
        history_params = [point.history_db_tuple() for point in points]
        latest_points = self._deduplicate_latest_points(points)
        latest_params = [point.latest_db_tuple() for point in latest_points]

        self.db.execute_many(history_sql, history_params)
        self.db.execute_many(latest_sql, latest_params)
        self.db.commit()

    def _normalize_source_names(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> list[str]:
        if source_names:
            return [source_name.strip().lower() for source_name in source_names if source_name.strip()]
        if factor_ids:
            factors = load_onchain_factors(factor_ids=factor_ids, enabled_only=False)
            source_names = [factor.source_name for factor in factors]
            seen: set[str] = set()
            ordered: list[str] = []
            for source_name in source_names:
                if source_name in seen:
                    continue
                seen.add(source_name)
                ordered.append(source_name)
            return ordered
        return [source.source_name for source in load_onchain_sources()]

    def _collect_for_source(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> list[OnchainTimeSeriesPoint]:
        if source_name == "exchange_flow":
            return self.exchange_flow_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "whale_activity":
            return self.whale_activity_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "stablecoin_flow":
            return self.stablecoin_flow_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "bridge_netflow":
            return self.bridge_netflow_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "exchange_reserve":
            return self.exchange_reserve_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "protocol_tvl":
            return self.protocol_tvl_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "network_usage":
            return self.network_usage_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "staking_flow":
            return self.staking_flow_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "dex_volume":
            return self.dex_volume_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "stablecoin_supply":
            return self.stablecoin_supply_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "market_sentiment":
            return self.market_sentiment_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "global_market":
            return self.global_market_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        if source_name == "defi_yields":
            return self.defi_yields_collector.collect(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
        raise ValueError(f"未知链上 source: {source_name}")

    def collect_once(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> dict[str, int]:
        self.sync_factor_catalog()
        selected_source_names = self._normalize_source_names(
            source_names=source_names,
            factor_ids=factor_ids,
        )
        source_definitions = {
            source.source_name: source
            for source in load_onchain_sources(
                source_names=selected_source_names,
                enabled_only=False,
            )
        }
        summary: dict[str, int] = {}
        total_points = 0
        for source_name in selected_source_names:
            started_at = self._utc_now_naive()
            status = "success"
            message = None
            points: list[OnchainTimeSeriesPoint] = []
            try:
                source_definition = source_definitions.get(source_name)
                if source_definition and source_definition.enabled and not source_definition.endpoint:
                    status = "unconfigured"
                    message = f"链上来源 {source_name} 未配置 endpoint"
                else:
                    points = self._collect_for_source(
                        source_name=source_name,
                        entity_keys=entity_keys,
                        interval=interval,
                        lookback_hours=lookback_hours,
                    )
                    if points:
                        self.save_to_db(points)
                    if not points:
                        status = "empty"
                    total_points += len(points)
                summary[source_name] = len(points)
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                summary[source_name] = 0
                logger.error(f"链上来源采集失败 [{source_name}]: {message}")
            finally:
                finished_at = self._utc_now_naive()
                self.db.record_collection_run(
                    module_name="onchain_data",
                    source_name=source_name,
                    job_name="onchain_timeseries",
                    status=status,
                    item_count=len(points),
                    started_at=started_at.isoformat(),
                    finished_at=finished_at.isoformat(),
                    duration_seconds=(finished_at - started_at).total_seconds(),
                    message=message,
                    metadata_json=json.dumps(
                        {
                            "factor_ids": factor_ids,
                            "entity_keys": entity_keys,
                            "interval": interval,
                            "lookback_hours": lookback_hours,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
        summary["total_points"] = total_points
        return summary

    def describe_registry(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict[str, list[dict]]:
        return {
            "sources": [
                {
                    "source_name": source.source_name,
                    "name": source.name,
                    "collector_key": source.collector_key,
                    "factor_id": source.factor_id,
                    "entity_type": source.entity_type,
                    "default_interval": source.default_interval,
                    "enabled": source.enabled,
                    "endpoint": source.endpoint,
                    "description": source.description,
                }
                for source in load_onchain_sources(
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
                for factor in load_onchain_factors(
                    factor_ids=factor_ids,
                    source_names=source_names,
                    enabled_only=False,
                )
            ],
            "entities": load_onchain_entities(
                source_names=source_names,
                entity_keys=entity_keys,
            ),
        }

    @staticmethod
    def _loads_json(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _normalize_factor_ids(factor_ids: list[str] | None) -> list[str]:
        return [
            factor_id.strip()
            for factor_id in (factor_ids or [])
            if factor_id.strip()
        ]

    @staticmethod
    def _normalize_entity_keys(entity_keys: list[str] | None) -> list[str]:
        return [
            entity_key.strip().upper()
            for entity_key in (entity_keys or [])
            if entity_key.strip()
        ]

    @staticmethod
    def _missing_entity_count(
        entities: list[dict],
        required_fields: tuple[str, ...],
    ) -> int:
        return sum(
            1
            for entity in entities
            if any(
                field_name in set(entity.get("expected_factor_ids") or [])
                and entity["metric_map"].get(field_name) is None
                for field_name in required_fields
            )
        )

    @staticmethod
    def _pick_entity_quality_flag(
        entity_rows: list[dict],
        preferred_factor_ids: list[str],
    ) -> str:
        for factor_id in preferred_factor_ids:
            for row in entity_rows:
                if str(row["factor_id"]) == factor_id:
                    return str(row.get("quality_flag") or "ok")
        for row in entity_rows:
            return str(row.get("quality_flag") or "ok")
        return "ok"

    def _build_context_quality(
        self,
        *,
        entities: list[dict],
        raw_row_count: int,
        ai_excluded_source_count: int,
        expected_entity_identities: list[tuple[str, str]],
        expected_factor_ids: list[str],
        observed_factor_ids: set[str],
        quality_summary: dict[str, object],
        coverage_rows: list[dict],
        requested_entity_keys: list[str] | None = None,
        configured_universe_summary: dict[str, object] | None = None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []
        expected_factor_set = set(expected_factor_ids)
        observed_entity_count = len(entities)
        expected_entity_count = len(expected_entity_identities)
        observed_factor_count = len(observed_factor_ids)
        expected_factor_count = len(expected_factor_ids)

        if expected_entity_count and observed_entity_count < expected_entity_count:
            flags.append("onchain_entity_coverage_incomplete")
            notes.append(
                "当前 onchain bundle 只覆盖了 "
                f"{observed_entity_count}/{expected_entity_count} 个目标实体，AI 看到的链上横截面仍不完整。"
            )

        if expected_factor_count and observed_factor_count < expected_factor_count:
            missing_factor_ids = [
                factor_id
                for factor_id in expected_factor_ids
                if factor_id not in observed_factor_ids
            ]
            flags.append("onchain_factor_coverage_incomplete")
            notes.append(
                "当前 onchain bundle 缺少部分设计内因子: "
                f"{', '.join(missing_factor_ids[:8])}"
                f"{' ...' if len(missing_factor_ids) > 8 else ''}。"
            )

        if quality_summary["partial_count"]:
            flags.append("onchain_partial_present")
            notes.append("latest onchain 快照里存在 partial 样本，说明部分链上实体只完成了部分标准化。")
        if quality_summary["fallback_count"]:
            flags.append("onchain_fallback_present")
            notes.append("latest onchain 快照里存在 fallback 样本，说明部分链上实体来自降级路径或历史近似值。")
        if quality_summary["stale_count"]:
            flags.append("onchain_stale_present")
            notes.append("latest onchain 快照里存在 stale 样本，不应把这些字段视为实时链上状态。")
        if quality_summary["unknown_count"]:
            flags.append("onchain_unknown_quality_flag_present")
            notes.append("latest onchain 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")

        if (
            configured_universe_summary
            and configured_universe_summary.get("scope_kind") == "default"
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            flags.append("onchain_configured_market_breadth_limited")
            type_counts = configured_universe_summary.get("entity_type_counts") or {}
            notes.append(
                "当前 onchain 默认实体宇宙仍偏向核心执行资产，"
                f"asset={int(type_counts.get('asset') or 0)}, "
                f"chain={int(type_counts.get('chain') or 0)}, "
                f"stablecoin={int(type_counts.get('stablecoin_asset') or 0)}, "
                f"protocol={int(type_counts.get('protocol') or 0)}，"
                "更适合做执行资产链上跟踪，而不是更广的市场 breadth 判断。"
            )

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
        if non_ready_sources:
            flags.append("onchain_source_not_ready_present")
            notes.append(
                "当前仍有未 ready 的 onchain source: "
                f"{', '.join(non_ready_sources)}。"
            )
        if not_ready_for_ai_sources:
            flags.append("onchain_source_not_ready_for_ai_present")
            notes.append(
                "当前仍有 onchain source 虽然最近任务成功，但 latest 快照还不适合直接作为 AI 的链上证据: "
                f"{', '.join(not_ready_for_ai_sources)}。"
            )

        if not entities:
            flags.append("onchain_context_empty")
            if raw_row_count > 0 and ai_excluded_source_count > 0:
                notes.append(
                    "当前 onchain 虽然已有真实已落库快照，但它们全部来自尚未达到 AI-ready 门槛的 source，"
                    "当前没有任何可直接给 AI 使用的链上证据。"
                )
            else:
                notes.append("当前 onchain bundle 没有任何最新快照，AI 不能把链上背景视为已覆盖。")
            return flags, notes

        group_specs = (
            (
                "exchange_flow_missing",
                ("exchange_netflow",),
                "部分资产缺少交易所净流数据，AI 无法判断币是否正在离开交易所或回流待卖。",
            ),
            (
                "whale_activity_missing",
                ("whale_transfer_count",),
                "部分资产缺少鲸鱼异动数据，AI 无法识别大额链上转账是否正在放大波动风险。",
            ),
            (
                "stablecoin_flow_missing",
                ("stablecoin_exchange_inflow",),
                "部分稳定币资产缺少流入交易所数据，AI 无法判断潜在买盘弹药是否正在进入场内。",
            ),
            (
                "bridge_flow_missing",
                ("bridge_netflow",),
                "部分跨链观察对象缺少桥净流数据，AI 无法判断资金是否在链之间迁移。",
            ),
            (
                "exchange_reserve_missing",
                ("exchange_reserve_balance", "exchange_reserve_change_24h"),
                "部分资产缺少交易所储备结构，AI 无法判断可售库存是否正在变化。",
            ),
            (
                "protocol_tvl_missing",
                ("protocol_tvl", "protocol_tvl_change_24h"),
                "部分协议缺少 TVL 结构，AI 无法判断链上资金黏性和协议吸引力变化。",
            ),
            (
                "network_usage_missing",
                ("active_addresses", "transaction_count", "fees_paid"),
                "部分链缺少网络使用度结构，AI 无法判断链上活跃度是否真实提升。",
            ),
            (
                "staking_flow_missing",
                ("staking_netflow",),
                "部分资产缺少质押净流数据，AI 无法判断流通筹码是否继续锁定或释放。",
            ),
        )
        for flag_prefix, candidate_fields, note in group_specs:
            required_fields = tuple(
                field_name
                for field_name in candidate_fields
                if field_name in expected_factor_set
            )
            if not required_fields:
                continue
            missing_count = self._missing_entity_count(entities, required_fields)
            if missing_count:
                flags.append(f"{flag_prefix}_for_{missing_count}_entities")
                notes.append(note)

        if (
            not requested_entity_keys
            and expected_entity_count > 1
            and observed_entity_count <= 1
        ):
            flags.append("onchain_cross_entity_comparison_weak")
            notes.append("当前 onchain bundle 只覆盖极少数实体，AI 很难做横向链上比较。")
        return flags, notes

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        expected_entity_identities: list[tuple[str, str]],
        requested_entity_keys: list[str] | None = None,
        requested_factor_ids: list[str] | None = None,
        requested_source_names: list[str] | None = None,
    ) -> dict[str, object]:
        entity_type_counts: dict[str, int] = {}
        entity_keys_by_type: dict[str, list[str]] = {}
        for entity_type, entity_key in expected_entity_identities:
            entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1
            entity_keys_by_type.setdefault(entity_type, []).append(entity_key)
        entity_keys_by_type = {
            entity_type: sorted(keys)
            for entity_type, keys in entity_keys_by_type.items()
        }
        scope_kind = (
            "filtered"
            if requested_entity_keys or requested_factor_ids or requested_source_names
            else "default"
        )
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = "sufficient"
            for entity_type, minimum_count in cls.MINIMUM_MARKET_BREADTH_THRESHOLDS.items():
                if int(entity_type_counts.get(entity_type) or 0) < minimum_count:
                    breadth_status = "limited"
                    break
        return {
            "scope_kind": scope_kind,
            "entity_type_counts": entity_type_counts,
            "entity_keys_by_type": entity_keys_by_type,
            "minimum_entity_type_counts_for_market_breadth": dict(
                cls.MINIMUM_MARKET_BREADTH_THRESHOLDS
            ),
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    def load_latest_context_bundle(
        self,
        entity_keys: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> dict:
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        normalized_source_names = self._normalize_source_names(
            factor_ids=normalized_factor_ids,
        )
        sql = """
            SELECT factor_id, category, factor_type, entity_type, entity_key,
                   interval, observation_time, value, unit, quality_flag,
                   dimensions_key, dimensions_json, config_version, source_name,
                   source_symbol, raw_payload_json, collected_at, updated_at
            FROM latest_onchain_timeseries
        """
        clauses: list[str] = []
        params: list[str] = []
        if normalized_entity_keys:
            placeholders = ",".join("?" for _ in normalized_entity_keys)
            clauses.append(f"entity_key IN ({placeholders})")
            params.extend(normalized_entity_keys)
        if normalized_factor_ids:
            placeholders = ",".join("?" for _ in normalized_factor_ids)
            clauses.append(f"factor_id IN ({placeholders})")
            params.extend(normalized_factor_ids)
        if clauses:
            sql += f" WHERE {' AND '.join(clauses)}"
        sql += " ORDER BY entity_key, factor_id, observation_time DESC"

        rows = [dict(row) for row in self.db.fetch_all(sql, tuple(params))]
        for row in rows:
            row["dimensions"] = self._loads_json(row.get("dimensions_json"))
            row["raw_payload"] = self._loads_json(row.get("raw_payload_json"))

        source_coverage = self.load_source_coverage(
            source_names=normalized_source_names,
            factor_ids=normalized_factor_ids,
            entity_keys=normalized_entity_keys,
        )
        coverage_rows = source_coverage.get("sources", [])
        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=rows,
            coverage_rows=coverage_rows,
        )
        filtered_rows = [
            row
            for row in rows
            if str(row["source_name"]) in ai_ready_source_names
        ]
        rows_by_entity: dict[tuple[str, str], list[dict]] = {}
        for row in filtered_rows:
            rows_by_entity.setdefault(
                (str(row["entity_type"]), str(row["entity_key"])),
                [],
            ).append(row)

        factor_definitions = load_onchain_factors(
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
            enabled_only=False,
        )
        expected_factor_ids = [
            factor.factor_id
            for factor in factor_definitions
        ]
        source_factor_map: dict[str, set[str]] = {}
        for factor in factor_definitions:
            source_factor_map.setdefault(factor.source_name, set()).add(factor.factor_id)
        expected_entity_rows = load_onchain_entities(
            source_names=normalized_source_names,
            entity_keys=normalized_entity_keys,
        )
        expected_entity_identities = sorted(
            {
                (
                    str(row["entity_type"]),
                    str(row["entity_key"]),
                )
                for row in expected_entity_rows
            }
        )
        configured_universe_summary = self._build_configured_universe_summary(
            expected_entity_identities=expected_entity_identities,
            requested_entity_keys=normalized_entity_keys,
            requested_factor_ids=normalized_factor_ids,
            requested_source_names=normalized_source_names if normalized_factor_ids else None,
        )
        expected_factor_ids_by_entity: dict[tuple[str, str], set[str]] = {}
        for row in expected_entity_rows:
            entity_identity = (
                str(row["entity_type"]),
                str(row["entity_key"]),
            )
            expected_factor_ids_by_entity.setdefault(entity_identity, set()).update(
                source_factor_map.get(str(row["source_name"]), set())
            )
        observed_factor_ids = {
            str(row["factor_id"])
            for row in filtered_rows
        }
        raw_observed_factor_ids = {
            str(row["factor_id"])
            for row in rows
        }
        quality_summary = summarize_quality_flag_counts(filtered_rows)
        raw_quality_summary = summarize_quality_flag_counts(rows)
        source_counts = self._count_rows_by_source(filtered_rows)
        raw_source_counts = self._count_rows_by_source(rows)
        entities: list[dict] = []
        all_timestamps: list[datetime] = []
        for (entity_type, entity_key), entity_rows in rows_by_entity.items():
            latest_times = [
                datetime.fromisoformat(str(row["observation_time"]))
                for row in entity_rows
            ]
            all_timestamps.extend(latest_times)
            metric_map = {
                str(row["factor_id"]): row["value"]
                for row in entity_rows
            }
            expected_entity_factor_ids = sorted(
                expected_factor_ids_by_entity.get((entity_type, entity_key), set())
            )
            entity_quality_summary = summarize_quality_flag_counts(entity_rows)
            entities.append(
                {
                    "entity_type": entity_type,
                    "entity_key": entity_key,
                    "observation_time": max(latest_times).isoformat() if latest_times else None,
                    "quality_flag": self._pick_entity_quality_flag(
                        entity_rows,
                        [
                            "exchange_netflow",
                            "bridge_netflow",
                            "protocol_tvl",
                            "active_addresses",
                        ],
                    ),
                    "quality_breakdown": entity_quality_summary["breakdown"],
                    "quality_ready_ratio": entity_quality_summary["ready_ratio"],
                    "observed_factor_count": len(metric_map),
                    "expected_factor_count": len(expected_entity_factor_ids),
                    "expected_factor_ids": expected_entity_factor_ids,
                    "available_factor_ids": sorted(metric_map),
                    "missing_factor_ids": [
                        factor_id
                        for factor_id in expected_entity_factor_ids
                        if factor_id not in metric_map
                    ],
                    "source_names": sorted(
                        {
                            str(row["source_name"])
                            for row in entity_rows
                        }
                    ),
                    "metrics": [
                        {
                            "factor_id": row["factor_id"],
                            "value": row["value"],
                            "unit": row["unit"],
                            "interval": row["interval"],
                            "quality_flag": row["quality_flag"],
                            "source_name": row["source_name"],
                            "dimensions": row["dimensions"],
                        }
                        for row in entity_rows
                    ],
                    "metric_map": metric_map,
                }
            )

        def _top_entity(factor_id: str, reverse: bool = True):
            candidates = []
            for entity in entities:
                value = entity["metric_map"].get(factor_id)
                if value is None:
                    continue
                candidates.append(
                    {
                        "entity_key": entity["entity_key"],
                        "entity_type": entity["entity_type"],
                        "value": value,
                    }
                )
            if not candidates:
                return None
            return sorted(
                candidates,
                key=lambda item: float(item["value"]),
                reverse=reverse,
            )[0]

        source_health = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "expected_point_count": row["expected_point_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "data_quality_flags": row["data_quality_flags"],
                "quality_notes": row["quality_notes"],
            }
            for row in coverage_rows
        ]
        coverage_by_source = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "expected_point_count": row["expected_point_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
            }
            for row in coverage_rows
        ]
        data_quality_flags, quality_notes = self._build_context_quality(
            entities=entities,
            raw_row_count=len(rows),
            ai_excluded_source_count=len(ai_excluded_sources),
            expected_entity_identities=expected_entity_identities,
            expected_factor_ids=expected_factor_ids,
            observed_factor_ids=observed_factor_ids,
            quality_summary=quality_summary,
            coverage_rows=coverage_rows,
            requested_entity_keys=normalized_entity_keys,
            configured_universe_summary=configured_universe_summary,
        )
        observed_entity_identities = {
            (
                str(entity["entity_type"]),
                str(entity["entity_key"]),
            )
            for entity in entities
        }
        missing_entities = [
            {
                "entity_type": entity_type,
                "entity_key": entity_key,
            }
            for entity_type, entity_key in expected_entity_identities
            if (entity_type, entity_key) not in observed_entity_identities
        ]
        missing_entity_keys = [
            entity_key
            for entity_key in sorted(
                {
                    str(item["entity_key"])
                    for item in missing_entities
                }
            )
        ]
        missing_factor_ids = [
            factor_id
            for factor_id in expected_factor_ids
            if factor_id not in observed_factor_ids
        ]
        raw_observed_entity_identities = {
            (
                str(row["entity_type"]),
                str(row["entity_key"]),
            )
            for row in rows
        }
        raw_latest_observation_time = max(
            (
                datetime.fromisoformat(str(row["observation_time"]))
                for row in rows
                if row.get("observation_time")
            ),
            default=None,
        )
        return {
            "as_of": max(all_timestamps).isoformat() if all_timestamps else None,
            "raw_as_of": raw_latest_observation_time.isoformat() if raw_latest_observation_time else None,
            "row_count": len(filtered_rows),
            "raw_row_count": len(rows),
            "entity_count": len(entities),
            "raw_entity_count": len(raw_observed_entity_identities),
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
                "expected_entity_count": len(expected_entity_identities),
                "observed_entity_count": len(entities),
                "raw_observed_entity_count": len(raw_observed_entity_identities),
                "expected_factor_count": len(expected_factor_ids),
                "observed_factor_count": len(observed_factor_ids),
                "raw_observed_factor_count": len(raw_observed_factor_ids),
                "expected_point_count": (
                    sum(
                        len(factor_ids)
                        for factor_ids in expected_factor_ids_by_entity.values()
                    )
                    if expected_factor_ids_by_entity
                    else None
                ),
                "observed_point_count": len(filtered_rows),
                "raw_observed_point_count": len(rows),
                "missing_entity_count": len(missing_entities),
                "missing_entities": missing_entities,
                "missing_entity_keys": missing_entity_keys,
                "missing_factor_ids": missing_factor_ids,
                "ready_for_ai_source_count": source_coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": source_coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
                "coverage_by_source": coverage_by_source,
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
                "source_count": source_coverage.get("source_count", 0),
                "ready_source_count": source_coverage.get("ready_source_count", 0),
                "problem_source_count": source_coverage.get("problem_source_count", 0),
                "stale_source_count": source_coverage.get("stale_source_count", 0),
                "ready_for_ai_source_count": source_coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": source_coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
            },
            "source_health": source_health,
            "entities": entities,
            "leaders": {
                "largest_exchange_inflow": _top_entity("exchange_netflow", reverse=True),
                "largest_exchange_outflow": _top_entity("exchange_netflow", reverse=False),
                "largest_whale_activity": _top_entity("whale_transfer_count", reverse=True),
                "largest_stablecoin_exchange_inflow": _top_entity(
                    "stablecoin_exchange_inflow",
                    reverse=True,
                ),
                "largest_bridge_netflow": _top_entity("bridge_netflow", reverse=True),
                "largest_protocol_tvl": _top_entity("protocol_tvl", reverse=True),
            },
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
        }

    def load_source_coverage(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict:
        normalized_source_names = (
            self._normalize_source_names(
                source_names=source_names,
                factor_ids=factor_ids,
            )
            if source_names or factor_ids
            else None
        )
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        sources = load_onchain_sources(
            source_names=normalized_source_names,
            enabled_only=False,
        )
        if not sources:
            health_summary = summarize_health_rows([])
            return {
                "generated_at": self._utc_now_naive().isoformat(),
                "source_count": 0,
                "stale_source_count": 0,
                "ready_for_ai_source_count": 0,
                "not_ready_for_ai_source_count": 0,
                **health_summary,
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
                COUNT(
                    DISTINCT COALESCE(entity_type, '') || '::' || COALESCE(entity_key, '')
                ) AS latest_entity_count,
                COUNT(DISTINCT factor_id) AS latest_factor_count,
                MAX(observation_time) AS latest_observation_time
            FROM latest_onchain_timeseries
            {latest_where_sql}
            GROUP BY source_name
            """,
            tuple(latest_params),
        )
        latest_map = {
            str(row["source_name"]): dict(row)
            for row in latest_rows
        }
        quality_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                quality_flag,
                COUNT(*) AS point_count
            FROM latest_onchain_timeseries
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

        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'onchain_data'
                  AND source_name IN ({placeholders})
                GROUP BY source_name
            ) AS latest
                ON runs.id = latest.latest_id
            """,
            tuple(source_name_list),
        )
        run_map = {
            str(row["source_name"]): dict(row)
            for row in run_rows
        }

        entity_registry_rows = load_onchain_entities(
            source_names=normalized_source_names,
            entity_keys=normalized_entity_keys,
        )
        expected_entity_identities_by_source: dict[str, set[tuple[str, str]]] = {}
        for row in entity_registry_rows:
            source_name = str(row["source_name"])
            expected_entity_identities_by_source.setdefault(source_name, set()).add(
                (
                    str(row["entity_type"]),
                    str(row["entity_key"]),
                )
            )
        expected_entity_counts = {
            source_name: len(entity_identities)
            for source_name, entity_identities in expected_entity_identities_by_source.items()
        }
        factor_registry_rows = load_onchain_factors(
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
            enabled_only=False,
        )
        expected_factor_counts: dict[str, int] = {}
        for factor in factor_registry_rows:
            expected_factor_counts[factor.source_name] = (
                expected_factor_counts.get(factor.source_name, 0) + 1
            )

        rows: list[dict] = []
        now = self._utc_now_naive()
        for source in sources:
            latest_meta = latest_map.get(source.source_name, {})
            run_meta = run_map.get(source.source_name, {})
            expected_factor_count = expected_factor_counts.get(source.source_name, 0)
            latest_factor_count = int(latest_meta.get("latest_factor_count") or 0)
            expected_entity_count = expected_entity_counts.get(source.source_name, 0)
            latest_entity_count = int(latest_meta.get("latest_entity_count") or 0)
            expected_point_count = self._expected_point_count(
                expected_entity_count=expected_entity_count,
                expected_factor_count=expected_factor_count,
            )
            quality_summary = summarize_quality_flag_counts(
                quality_counts_map.get(source.source_name, {})
            )
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = (
                datetime.fromisoformat(last_run_finished_at)
                if last_run_finished_at
                else None
            )
            interval_seconds = {
                "exchange_flow": ONCHAIN_CONFIG["exchange_flow_interval_seconds"],
                "whale_activity": ONCHAIN_CONFIG["whale_activity_interval_seconds"],
                "stablecoin_flow": ONCHAIN_CONFIG["stablecoin_flow_interval_seconds"],
                "bridge_netflow": ONCHAIN_CONFIG["bridge_netflow_interval_seconds"],
                "exchange_reserve": ONCHAIN_CONFIG["exchange_reserve_interval_seconds"],
                "protocol_tvl": ONCHAIN_CONFIG["protocol_tvl_interval_seconds"],
                "network_usage": ONCHAIN_CONFIG["network_usage_interval_seconds"],
                "staking_flow": ONCHAIN_CONFIG["staking_flow_interval_seconds"],
            }.get(source.source_name, 3600)
            is_stale = last_run_dt is None or (
                now - last_run_dt
            ).total_seconds() > interval_seconds * 3
            configuration_ready = bool(source.endpoint)
            health_status = resolve_source_health_status(
                enabled=bool(source.enabled),
                configuration_ready=configuration_ready,
                last_run_status=run_meta.get("status"),
                latest_point_count=int(latest_meta.get("latest_point_count") or 0),
                is_stale=is_stale,
            )
            data_quality_flags: list[str] = []
            quality_notes: list[str] = []
            if expected_factor_count and latest_factor_count < expected_factor_count:
                data_quality_flags.append("factor_coverage_incomplete")
                quality_notes.append("当前已落库 factor 数少于设计目标，AI 看到的链上结构仍不完整。")
            if expected_entity_count and latest_entity_count < expected_entity_count:
                data_quality_flags.append("entity_coverage_incomplete")
                quality_notes.append("当前实体覆盖少于注册表目标，AI 只看到了部分链上观察对象。")
            if expected_point_count and int(latest_meta.get("latest_point_count") or 0) < expected_point_count:
                data_quality_flags.append("point_coverage_incomplete")
                quality_notes.append("当前 entity x factor 矩阵还没有补齐，AI 看到的链上快照仍是残缺矩阵。")
            if quality_summary["partial_count"]:
                data_quality_flags.append("partial_points_present")
                quality_notes.append("latest 快照里存在 partial 链上样本，说明部分实体只完成了部分标准化。")
            if quality_summary["fallback_count"]:
                data_quality_flags.append("fallback_points_present")
                quality_notes.append("latest 快照里存在 fallback 链上样本，说明部分实体来自降级路径或历史近似值。")
            if quality_summary["stale_count"]:
                data_quality_flags.append("stale_points_present")
                quality_notes.append("latest 快照里存在 stale 链上样本，即使最近任务成功也不应等同于实时链上状态。")
            if quality_summary["unknown_count"]:
                data_quality_flags.append("unknown_quality_flag_present")
                quality_notes.append("latest 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")
            is_ready_for_ai = self._is_source_ready_for_ai(
                health_status=health_status,
                expected_entity_count=expected_entity_count,
                latest_entity_count=latest_entity_count,
                expected_factor_count=expected_factor_count,
                latest_factor_count=latest_factor_count,
                expected_point_count=expected_point_count,
                latest_point_count=int(latest_meta.get("latest_point_count") or 0),
                quality_summary=quality_summary,
            )
            if health_status == "ready" and not is_ready_for_ai:
                quality_notes.append(
                    "最近一次链上任务虽然成功，但 latest 快照仍未达到可直接供 AI 做市场判断的质量门槛。"
                )
            rows.append(
                {
                    "source_name": source.source_name,
                    "name": source.name,
                    "collector_key": source.collector_key,
                    "factor_id": source.factor_id,
                    "entity_type": source.entity_type,
                    "default_interval": source.default_interval,
                    "enabled": source.enabled,
                    "endpoint": source.endpoint,
                    "configuration_ready": configuration_ready,
                    "expected_entity_count": expected_entity_count,
                    "expected_factor_count": expected_factor_count,
                    "expected_point_count": expected_point_count,
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
                    "data_quality_flags": data_quality_flags,
                    "latest_quality_flag_breakdown": quality_summary["breakdown"],
                    "latest_ok_point_count": quality_summary["ok_count"],
                    "latest_partial_point_count": quality_summary["partial_count"],
                    "latest_fallback_point_count": quality_summary["fallback_count"],
                    "latest_stale_point_count": quality_summary["stale_count"],
                    "latest_unknown_quality_point_count": quality_summary["unknown_count"],
                    "latest_non_ok_point_count": quality_summary["non_ok_count"],
                    "latest_quality_ready_ratio": quality_summary["ready_ratio"],
                    "quality_notes": quality_notes,
                }
            )

        rows.sort(
            key=lambda item: (
                item["health_status"] != "ready",
                not item["is_ready_for_ai"],
                item["is_stale"],
                item["source_name"],
            )
        )
        health_summary = summarize_health_rows(rows)
        ready_for_ai_source_count = sum(1 for item in rows if item["is_ready_for_ai"])
        return {
            "generated_at": now.isoformat(),
            "source_count": len(rows),
            "stale_source_count": sum(1 for item in rows if item["is_stale"]),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
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
        local_service = OnchainDataService(
            client=self.client,
            db=local_db,
        )
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
        enabled_sources = {
            source.source_name
            for source in load_onchain_sources()
        }

        if "exchange_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["exchange_flow_interval_seconds"],
                id="onchain_exchange_flow",
                name="链上交易所净流采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["exchange_flow_interval_seconds"]),
                kwargs={
                    "source_name": "exchange_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "whale_activity" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["whale_activity_interval_seconds"],
                id="onchain_whale_activity",
                name="链上鲸鱼异动采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["whale_activity_interval_seconds"]),
                kwargs={
                    "source_name": "whale_activity",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "stablecoin_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["stablecoin_flow_interval_seconds"],
                id="onchain_stablecoin_flow",
                name="稳定币流入交易所采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["stablecoin_flow_interval_seconds"]),
                kwargs={
                    "source_name": "stablecoin_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "bridge_netflow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["bridge_netflow_interval_seconds"],
                id="onchain_bridge_netflow",
                name="桥资金净流采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["bridge_netflow_interval_seconds"]),
                kwargs={
                    "source_name": "bridge_netflow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "exchange_reserve" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["exchange_reserve_interval_seconds"],
                id="onchain_exchange_reserve",
                name="交易所储备采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["exchange_reserve_interval_seconds"]),
                kwargs={
                    "source_name": "exchange_reserve",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "protocol_tvl" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["protocol_tvl_interval_seconds"],
                id="onchain_protocol_tvl",
                name="协议 TVL 采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["protocol_tvl_interval_seconds"]),
                kwargs={
                    "source_name": "protocol_tvl",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "network_usage" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["network_usage_interval_seconds"],
                id="onchain_network_usage",
                name="链使用率采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["network_usage_interval_seconds"]),
                kwargs={
                    "source_name": "network_usage",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "staking_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["staking_flow_interval_seconds"],
                id="onchain_staking_flow",
                name="质押净流采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["staking_flow_interval_seconds"]),
                kwargs={
                    "source_name": "staking_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "market_sentiment" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["market_sentiment_interval_seconds"],
                id="onchain_market_sentiment",
                name="市场情绪指数采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["market_sentiment_interval_seconds"]),
                kwargs={
                    "source_name": "market_sentiment",
                    "entity_keys": entity_keys,
                    "interval": interval or "1d",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "global_market" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["global_market_interval_seconds"],
                id="onchain_global_market",
                name="全球市场数据采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["global_market_interval_seconds"]),
                kwargs={
                    "source_name": "global_market",
                    "entity_keys": entity_keys,
                    "interval": interval or "1h",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "defi_yields" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["defi_yields_interval_seconds"],
                id="onchain_defi_yields",
                name="DeFi 收益率采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["defi_yields_interval_seconds"]),
                kwargs={
                    "source_name": "defi_yields",
                    "entity_keys": entity_keys,
                    "interval": interval or "1d",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        return scheduler

    def build_async_scheduler(
        self,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ):
        """构建 AsyncIOScheduler — 利用 asyncio 事件循环调度采集任务。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        enabled_sources = {
            source.source_name
            for source in load_onchain_sources()
        }

        if "exchange_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["exchange_flow_interval_seconds"],
                id="onchain_exchange_flow",
                name="链上交易所净流采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["exchange_flow_interval_seconds"]),
                kwargs={
                    "source_name": "exchange_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "whale_activity" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["whale_activity_interval_seconds"],
                id="onchain_whale_activity",
                name="链上鲸鱼异动采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["whale_activity_interval_seconds"]),
                kwargs={
                    "source_name": "whale_activity",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "stablecoin_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["stablecoin_flow_interval_seconds"],
                id="onchain_stablecoin_flow",
                name="稳定币流入交易所采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["stablecoin_flow_interval_seconds"]),
                kwargs={
                    "source_name": "stablecoin_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "bridge_netflow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["bridge_netflow_interval_seconds"],
                id="onchain_bridge_netflow",
                name="桥资金净流采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["bridge_netflow_interval_seconds"]),
                kwargs={
                    "source_name": "bridge_netflow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "exchange_reserve" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["exchange_reserve_interval_seconds"],
                id="onchain_exchange_reserve",
                name="交易所储备采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["exchange_reserve_interval_seconds"]),
                kwargs={
                    "source_name": "exchange_reserve",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "protocol_tvl" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["protocol_tvl_interval_seconds"],
                id="onchain_protocol_tvl",
                name="协议 TVL 采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["protocol_tvl_interval_seconds"]),
                kwargs={
                    "source_name": "protocol_tvl",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "network_usage" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["network_usage_interval_seconds"],
                id="onchain_network_usage",
                name="链使用率采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["network_usage_interval_seconds"]),
                kwargs={
                    "source_name": "network_usage",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "staking_flow" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["staking_flow_interval_seconds"],
                id="onchain_staking_flow",
                name="质押净流采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["staking_flow_interval_seconds"]),
                kwargs={
                    "source_name": "staking_flow",
                    "entity_keys": entity_keys,
                    "interval": interval or ONCHAIN_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "market_sentiment" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["market_sentiment_interval_seconds"],
                id="onchain_market_sentiment",
                name="市场情绪指数采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["market_sentiment_interval_seconds"]),
                kwargs={
                    "source_name": "market_sentiment",
                    "entity_keys": entity_keys,
                    "interval": interval or "1d",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "global_market" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["global_market_interval_seconds"],
                id="onchain_global_market",
                name="全球市场数据采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["global_market_interval_seconds"]),
                kwargs={
                    "source_name": "global_market",
                    "entity_keys": entity_keys,
                    "interval": interval or "1h",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        if "defi_yields" in enabled_sources:
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=ONCHAIN_CONFIG["defi_yields_interval_seconds"],
                id="onchain_defi_yields",
                name="DeFi 收益率采集(async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, ONCHAIN_CONFIG["defi_yields_interval_seconds"]),
                kwargs={
                    "source_name": "defi_yields",
                    "entity_keys": entity_keys,
                    "interval": interval or "1d",
                    "lookback_hours": lookback_hours or ONCHAIN_CONFIG["default_lookback_hours"],
                },
            )
        return scheduler

    def close(self):
        self.db.close()
