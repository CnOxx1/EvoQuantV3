import json
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from config.settings import TOKENOMICS_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import (
    is_quality_summary_ai_ready,
    resolve_source_health_status,
    summarize_health_rows,
    summarize_quality_flag_counts,
)
from data_layer.tokenomics_data.circulating_supply import CirculatingSupplyCollector
from data_layer.tokenomics_data.client import TokenomicsDataClient
from data_layer.tokenomics_data.models import TokenUnlockEvent
from data_layer.tokenomics_data.sources import (
    load_tokenomics_entities,
    load_tokenomics_factors,
    load_tokenomics_sources,
    load_treasury_wallet_groups,
)
from data_layer.tokenomics_data.staking_ratio import StakingRatioCollector
from data_layer.tokenomics_data.treasury_wallet_flow import TreasuryWalletFlowCollector
from data_layer.tokenomics_data.unlock_realization import UnlockRealizationCollector
from data_layer.tokenomics_data.unlock_schedule import UnlockScheduleCollector


class TokenomicsDataService:
    """Tokenomics 数据模块统一编排入口。"""

    MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH = 6
    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    REGISTRY_BLOCKED_BUNDLE_REASON = "registry_not_ai_ready"

    def __init__(
        self,
        client: TokenomicsDataClient | None = None,
        db: DBManager | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or TokenomicsDataClient()
        self.circulating_supply_collector = CirculatingSupplyCollector(self.client, self.db)
        self.unlock_schedule_collector = UnlockScheduleCollector(self.client, self.db)
        self.unlock_realization_collector = UnlockRealizationCollector(self.client, self.db)
        self.treasury_wallet_flow_collector = TreasuryWalletFlowCollector(self.client, self.db)
        self.staking_ratio_collector = StakingRatioCollector(self.client, self.db)

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
    def _is_source_ready_for_ai(
        *,
        health_status: str,
        expected_entity_count: int,
        latest_entity_count: int,
        expected_factor_count: int,
        latest_factor_count: int,
        quality_summary: dict[str, object],
        registry_ready: bool = True,
    ) -> bool:
        if health_status != "ready":
            return False
        if not registry_ready:
            return False
        if expected_entity_count > 0 and latest_entity_count < expected_entity_count:
            return False
        if expected_factor_count > 0 and latest_factor_count < expected_factor_count:
            return False
        return is_quality_summary_ai_ready(quality_summary)

    @staticmethod
    def _source_registry_status(
        source_name: str,
        entity_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        if source_name != "treasury_wallet_flow":
            return {
                "registry_required": False,
                "registry_ready": True,
                "registry_record_count": len(entity_rows),
                "registry_ready_entity_count": len(entity_rows),
                "registry_unready_entity_count": 0,
                "registry_quality_notes": [],
            }

        registry_required = True
        registry_record_count = len(entity_rows)
        registry_ready_entity_count = sum(
            1
            for row in entity_rows
            if row.get("wallet_group_ready_for_ai")
        )
        registry_unready_entity_count = max(
            0,
            registry_record_count - registry_ready_entity_count,
        )
        registry_ready = (
            registry_record_count > 0
            and registry_unready_entity_count == 0
        )
        registry_quality_notes: list[str] = []
        if registry_record_count == 0:
            registry_quality_notes.append(
                "treasury wallet registry 当前为空，无法确认任何钱包组口径。"
            )
        elif registry_unready_entity_count > 0:
            registry_quality_notes.append(
                "部分 treasury wallet group 仍未达到 verified + address_count>0 + source_refs 完整的门槛。"
            )
        for row in entity_rows:
            for note in row.get("wallet_group_quality_notes") or []:
                if note not in registry_quality_notes:
                    registry_quality_notes.append(str(note))
        return {
            "registry_required": registry_required,
            "registry_ready": registry_ready,
            "registry_record_count": registry_record_count,
            "registry_ready_entity_count": registry_ready_entity_count,
            "registry_unready_entity_count": registry_unready_entity_count,
            "registry_quality_notes": registry_quality_notes,
        }

    def init_storage(self):
        self.db.init_market_data_tables()
        self.sync_factor_catalog()

    def sync_factor_catalog(self):
        factors = load_tokenomics_factors(enabled_only=False)
        if not factors:
            return
        sql = """
            INSERT INTO tokenomics_factor_catalog (
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

    def save_unlock_events(self, events: list[TokenUnlockEvent]):
        if not events:
            return
        sql = """
            INSERT INTO token_unlock_events (
                asset, event_type, scheduled_at, unlock_amount, unlock_value_usd,
                unlock_pct_float, beneficiary_group, status, source_name, source_url,
                raw_payload_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset, event_type, scheduled_at, source_name)
            DO UPDATE SET
                unlock_amount=excluded.unlock_amount,
                unlock_value_usd=excluded.unlock_value_usd,
                unlock_pct_float=excluded.unlock_pct_float,
                beneficiary_group=excluded.beneficiary_group,
                status=excluded.status,
                source_url=excluded.source_url,
                raw_payload_json=excluded.raw_payload_json,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
        """
        self.db.execute_many(sql, [event.to_db_tuple() for event in events])
        self.db.commit()

    def _normalize_source_names(
        self,
        source_names: list[str] | None = None,
        factor_ids: list[str] | None = None,
    ) -> list[str]:
        if source_names:
            return [source_name.strip().lower() for source_name in source_names if source_name.strip()]
        if factor_ids:
            factors = load_tokenomics_factors(factor_ids=factor_ids, enabled_only=False)
            seen: set[str] = set()
            ordered: list[str] = []
            for factor in factors:
                if factor.source_name in seen:
                    continue
                seen.add(factor.source_name)
                ordered.append(factor.source_name)
            return ordered
        return [source.source_name for source in load_tokenomics_sources()]

    def _collect_for_source(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
        interval: str | None = None,
        lookback_hours: int | None = None,
    ) -> tuple[list, list[TokenUnlockEvent]]:
        if source_name == "circulating_supply":
            return (
                self.circulating_supply_collector.collect(
                    entity_keys=entity_keys,
                    interval=interval,
                    lookback_hours=lookback_hours,
                ),
                [],
            )
        if source_name == "unlock_schedule":
            points = self.unlock_schedule_collector.fetch_recent_points(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
            if points:
                self.unlock_schedule_collector.save_to_db(points)
            events = self.unlock_schedule_collector.fetch_unlock_events(
                entity_keys=entity_keys,
                interval=interval,
                lookback_hours=lookback_hours,
            )
            if events:
                self.save_unlock_events(events)
            return points, events
        if source_name == "unlock_realization":
            return (
                self.unlock_realization_collector.collect(
                    entity_keys=entity_keys,
                    interval=interval,
                    lookback_hours=lookback_hours,
                ),
                [],
            )
        if source_name == "treasury_wallet_flow":
            return (
                self.treasury_wallet_flow_collector.collect(
                    entity_keys=entity_keys,
                    interval=interval,
                    lookback_hours=lookback_hours,
                ),
                [],
            )
        if source_name == "staking_ratio":
            return (
                self.staking_ratio_collector.collect(
                    entity_keys=entity_keys,
                    interval=interval,
                    lookback_hours=lookback_hours,
                ),
                [],
            )
        raise ValueError(f"未知 tokenomics source: {source_name}")

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
            for source in load_tokenomics_sources(
                source_names=selected_source_names,
                enabled_only=False,
            )
        }
        summary: dict[str, int] = {}
        total_points = 0
        total_events = 0
        for source_name in selected_source_names:
            started_at = self._utc_now_naive()
            status = "success"
            message = None
            points = []
            events: list[TokenUnlockEvent] = []
            try:
                source_definition = source_definitions.get(source_name)
                if source_definition and source_definition.enabled and not source_definition.endpoint:
                    status = "unconfigured"
                    message = f"tokenomics 来源 {source_name} 未配置 endpoint"
                else:
                    points, events = self._collect_for_source(
                        source_name=source_name,
                        entity_keys=entity_keys,
                        interval=interval,
                        lookback_hours=lookback_hours,
                    )
                    if not points and not events:
                        status = "empty"
                    total_points += len(points)
                    total_events += len(events)
                summary[source_name] = len(points)
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                summary[source_name] = 0
                logger.error(f"tokenomics 来源采集失败 [{source_name}]: {message}")
            finally:
                finished_at = self._utc_now_naive()
                self.db.record_collection_run(
                    module_name="tokenomics_data",
                    source_name=source_name,
                    job_name="tokenomics_timeseries",
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
                            "event_count": len(events),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
        summary["total_points"] = total_points
        summary["total_events"] = total_events
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
                    "primary_factor_id": source.primary_factor_id,
                    "entity_type": source.entity_type,
                    "default_interval": source.default_interval,
                    "enabled": source.enabled,
                    "endpoint": source.endpoint,
                    "description": source.description,
                }
                for source in load_tokenomics_sources(
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
                for factor in load_tokenomics_factors(
                    factor_ids=factor_ids,
                    source_names=source_names,
                    enabled_only=False,
                )
            ],
            "entities": load_tokenomics_entities(
                source_names=source_names,
                entity_keys=entity_keys,
            ),
        }

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
    def _entity_quality_flag(
        row_map: dict[str, dict],
        preferred_factor_ids: list[str],
    ) -> str:
        for factor_id in preferred_factor_ids:
            row = row_map.get(factor_id)
            if row is not None:
                return str(row.get("quality_flag") or "ok")
        for row in row_map.values():
            return str(row.get("quality_flag") or "ok")
        return "ok"

    @staticmethod
    def _missing_entity_count(
        entities: list[dict],
        required_fields: tuple[str, ...],
    ) -> int:
        return sum(
            1
            for entity in entities
            if any(entity.get(field_name) is None for field_name in required_fields)
        )

    @staticmethod
    def _count_rows_by_source(rows: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            source_name = str(row["source_name"])
            counts[source_name] = counts.get(source_name, 0) + 1
        return counts

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

    @classmethod
    def _blocked_bundle_source_names(
        cls,
        coverage_rows: list[dict],
    ) -> set[str]:
        return {
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("is_ready_for_ai")
        }

    @classmethod
    def _build_ai_excluded_sources(
        cls,
        *,
        raw_rows: list[dict],
        coverage_rows: list[dict],
    ) -> list[dict]:
        blocked_source_names = cls._blocked_bundle_source_names(coverage_rows)
        if not blocked_source_names:
            return []
        raw_rows_by_source: dict[str, list[dict]] = {}
        for row in raw_rows:
            raw_rows_by_source.setdefault(str(row["source_name"]), []).append(row)
        excluded: list[dict] = []
        for coverage_row in coverage_rows:
            source_name = str(coverage_row["source_name"])
            if source_name not in blocked_source_names:
                continue
            source_rows = raw_rows_by_source.get(source_name, [])
            excluded_reason = (
                cls.REGISTRY_BLOCKED_BUNDLE_REASON
                if coverage_row.get("registry_required") and not coverage_row.get("registry_ready")
                else cls.AI_EXCLUDED_SOURCE_REASON
            )
            excluded.append(
                {
                    "source_name": source_name,
                    "excluded_reason": excluded_reason,
                    "raw_row_count": len(source_rows),
                    "raw_factor_ids": sorted(
                        {
                            str(row["factor_id"])
                            for row in source_rows
                        }
                    ),
                    "registry_required": bool(coverage_row.get("registry_required")),
                    "registry_ready": bool(coverage_row.get("registry_ready")),
                    "registry_record_count": int(coverage_row.get("registry_record_count") or 0),
                    "registry_ready_entity_count": int(
                        coverage_row.get("registry_ready_entity_count") or 0
                    ),
                    "registry_unready_entity_count": int(
                        coverage_row.get("registry_unready_entity_count") or 0
                    ),
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    def _load_upcoming_unlock_events(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[dict]:
        sql = """
            SELECT asset, event_type, scheduled_at, unlock_amount, unlock_value_usd,
                   unlock_pct_float, beneficiary_group, status, source_name, source_url,
                   raw_payload_json, collected_at
            FROM token_unlock_events
            WHERE scheduled_at >= ?
        """
        params: list[str] = [self._utc_now_naive().isoformat()]
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        if normalized_entity_keys:
            placeholders = ",".join("?" for _ in normalized_entity_keys)
            sql += f" AND asset IN ({placeholders})"
            params.extend(normalized_entity_keys)
        sql += """
            ORDER BY scheduled_at ASC,
                     COALESCE(unlock_value_usd, 0) DESC,
                     asset ASC
        """
        events: list[dict] = []
        for row in self.db.fetch_all(sql, tuple(params)):
            row_dict = dict(row)
            events.append(
                {
                    **row_dict,
                    "raw_payload": self._loads_json(row_dict.get("raw_payload_json")),
                }
            )
        return events

    @staticmethod
    def _build_unlock_horizon_summary(
        events: list[dict],
        now: datetime,
    ) -> dict:
        horizon_specs = (
            ("next_24h", 1),
            ("next_7d", 7),
            ("next_30d", 30),
        )
        summary: dict[str, dict] = {}
        for horizon_key, horizon_days in horizon_specs:
            cutoff = now.timestamp() + horizon_days * 86400
            selected = []
            for event in events:
                scheduled_at = str(event.get("scheduled_at") or "").strip()
                if not scheduled_at:
                    continue
                scheduled_dt = datetime.fromisoformat(scheduled_at)
                if scheduled_dt.timestamp() <= cutoff:
                    selected.append(event)
            total_unlock_value_usd = sum(
                float(item.get("unlock_value_usd") or 0.0)
                for item in selected
            )
            max_unlock_value_usd = max(
                (float(item.get("unlock_value_usd") or 0.0) for item in selected),
                default=0.0,
            )
            assets = sorted(
                {
                    str(item["asset"])
                    for item in selected
                    if item.get("asset")
                }
            )
            summary[horizon_key] = {
                "event_count": len(selected),
                "asset_count": len(assets),
                "assets": assets,
                "total_unlock_value_usd": total_unlock_value_usd,
                "max_unlock_value_usd": max_unlock_value_usd,
            }
        return summary

    def _build_context_quality(
        self,
        *,
        entities: list[dict],
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
        expected_factor_id_set = set(expected_factor_ids)
        observed_entity_count = len(entities)
        expected_entity_count = len(expected_entity_keys)
        observed_factor_count = len(observed_factor_ids)
        expected_factor_count = len(expected_factor_ids)

        if not entities:
            flags.append("tokenomics_context_empty")
            notes.append("当前 tokenomics bundle 没有任何可直接给 AI 使用的最新快照，供给侧证据暂不可直接消费。")

        if expected_entity_count and observed_entity_count < expected_entity_count:
            flags.append("tokenomics_entity_coverage_incomplete")
            notes.append(
                "当前 tokenomics bundle 只覆盖了 "
                f"{observed_entity_count}/{expected_entity_count} 个目标资产，AI 看到的供给侧横截面仍不完整。"
            )

        if expected_factor_count and observed_factor_count < expected_factor_count:
            missing_factor_ids = [
                factor_id
                for factor_id in expected_factor_ids
                if factor_id not in observed_factor_ids
            ]
            flags.append("tokenomics_factor_coverage_incomplete")
            notes.append(
                "当前 tokenomics bundle 缺少部分设计内因子: "
                f"{', '.join(missing_factor_ids[:6])}"
                f"{' ...' if len(missing_factor_ids) > 6 else ''}。"
            )

        if quality_summary["partial_count"]:
            flags.append("tokenomics_partial_present")
            notes.append("latest tokenomics 快照里存在 partial 样本，说明部分供给字段尚未完整。")
        if quality_summary["fallback_count"]:
            flags.append("tokenomics_fallback_present")
            notes.append("latest tokenomics 快照里存在 fallback 样本，说明部分供给字段来自降级路径或近似值。")
        if quality_summary["stale_count"]:
            flags.append("tokenomics_stale_present")
            notes.append("latest tokenomics 快照里存在 stale 样本，不应把这些字段视为当前最新供给状态。")
        if quality_summary["unknown_count"]:
            flags.append("tokenomics_unknown_quality_flag_present")
            notes.append("latest tokenomics 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")

        if (
            configured_universe_summary
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            flags.append("tokenomics_configured_market_breadth_limited")
            asset_count = int(configured_universe_summary.get("asset_entity_count") or 0)
            minimum_count = int(
                configured_universe_summary.get(
                    "minimum_asset_entity_count_for_market_breadth"
                )
                or 0
            )
            notes.append(
                "当前 tokenomics 默认资产宇宙只覆盖 "
                f"{asset_count} 个资产，仍偏向核心执行资产，"
                f"未达到用于更广供给 breadth 判断的建议门槛 {minimum_count}。"
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
            flags.append("tokenomics_source_not_ready_present")
            notes.append(
                "当前仍有未 ready 的 tokenomics source: "
                f"{', '.join(non_ready_sources)}。"
            )
        if not_ready_for_ai_sources:
            flags.append("tokenomics_source_not_ready_for_ai_present")
            notes.append(
                "当前仍有 tokenomics source 虽然可运行，但还不适合直接作为 AI 供给侧证据: "
                f"{', '.join(not_ready_for_ai_sources)}。"
            )

        treasury_factor_ids = {
            "treasury_wallet_inflow",
            "treasury_wallet_outflow",
            "foundation_wallet_netflow",
        }
        if treasury_factor_ids & expected_factor_id_set:
            treasury_registry_rows = load_treasury_wallet_groups(expected_entity_keys)
            treasury_registry_unready = [
                row
                for row in treasury_registry_rows
                if not row.get("is_ready_for_ai")
            ]
            if treasury_registry_rows and treasury_registry_unready:
                flags.append("treasury_wallet_registry_not_ai_ready")
                affected_assets = [
                    str(row["entity_key"])
                    for row in treasury_registry_unready
                ]
                notes.append(
                    "部分 treasury wallet group 仍未达到可核验门槛，相关钱包流数据只能视为补充证据: "
                    f"{', '.join(affected_assets[:6])}"
                    f"{' ...' if len(affected_assets) > 6 else ''}。"
                )

        group_specs = (
            (
                "circulating_supply_structure_missing",
                ("circulating_supply", "float_supply", "inflation_rate_annualized"),
                "部分资产缺少 circulating / float / inflation 结构，AI 无法判断真实流通盘与新增供给压力。",
            ),
            (
                "unlock_pressure_missing",
                (
                    "scheduled_unlock_usd_7d",
                    "scheduled_unlock_pct_float_7d",
                    "scheduled_unlock_usd_30d",
                ),
                "部分资产缺少未来解锁压力结构，AI 无法完整判断近期与月度抛压窗口。",
            ),
            (
                "realized_unlock_missing",
                ("realized_unlock_usd_24h",),
                "部分资产缺少已实现解锁数据，AI 无法区分计划解锁和已经落地的真实供给释放。",
            ),
            (
                "treasury_flow_missing",
                (
                    "treasury_wallet_inflow",
                    "treasury_wallet_outflow",
                    "foundation_wallet_netflow",
                ),
                "部分资产缺少基金会/国库钱包流向，AI 无法判断项目方是否在真实转移筹码。",
            ),
            (
                "staking_evidence_missing",
                ("staking_ratio", "staking_ratio_change_7d"),
                "部分资产缺少质押率结构，AI 无法判断可流通供给是否继续被锁定或释放。",
            ),
        )
        for flag_prefix, candidate_fields, note in group_specs:
            required_fields = tuple(
                field_name
                for field_name in candidate_fields
                if field_name in expected_factor_id_set
            )
            if not required_fields:
                continue
            missing_count = (
                expected_entity_count
                if expected_entity_count and not entities
                else self._missing_entity_count(entities, required_fields)
            )
            if missing_count:
                flags.append(f"{flag_prefix}_for_{missing_count}_entities")
                notes.append(note)

        if (
            not requested_entity_keys
            and expected_entity_count > 1
            and observed_entity_count <= 1
        ):
            flags.append("tokenomics_cross_asset_comparison_weak")
            notes.append("当前 tokenomics bundle 只覆盖极少数资产，AI 很难做横向供给压力比较。")
        return flags, notes

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        expected_entity_keys: list[str],
        requested_entity_keys: list[str] | None = None,
        requested_factor_ids: list[str] | None = None,
        requested_source_names: list[str] | None = None,
    ) -> dict[str, object]:
        scope_kind = (
            "filtered"
            if requested_entity_keys or requested_factor_ids or requested_source_names
            else "default"
        )
        asset_count = len(expected_entity_keys)
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = (
                "sufficient"
                if asset_count >= cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH
                else "limited"
            )
        return {
            "scope_kind": scope_kind,
            "tracked_entity_keys": list(expected_entity_keys),
            "asset_entity_count": asset_count,
            "minimum_asset_entity_count_for_market_breadth": (
                cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH
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
        normalized_source_names = (
            self._normalize_source_names(factor_ids=normalized_factor_ids)
            if normalized_factor_ids
            else None
        )
        sql = """
            SELECT factor_id, category, factor_type, entity_type, entity_key,
                   interval, observation_time, value, unit, quality_flag,
                   dimensions_key, dimensions_json, config_version, source_name,
                   source_symbol, raw_payload_json, collected_at, updated_at
            FROM latest_tokenomics_timeseries
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
        raw_rows: list[dict] = []
        for row in self.db.fetch_all(sql, tuple(params)):
            row_dict = dict(row)
            raw_rows.append(
                {
                    **row_dict,
                    "observation_time_dt": datetime.fromisoformat(str(row_dict["observation_time"])),
                    "dimensions": self._loads_json(row_dict.get("dimensions_json")) or {},
                    "raw_payload": self._loads_json(row_dict.get("raw_payload_json")) or {},
                }
            )
        expected_factor_ids = [
            factor.factor_id
            for factor in load_tokenomics_factors(
                factor_ids=normalized_factor_ids,
                source_names=normalized_source_names,
                enabled_only=False,
            )
        ]
        expected_entity_keys = sorted(
            {
                str(row["entity_key"])
                for row in load_tokenomics_entities(
                    source_names=normalized_source_names,
                    entity_keys=normalized_entity_keys,
                )
            }
        )
        configured_universe_summary = self._build_configured_universe_summary(
            expected_entity_keys=expected_entity_keys,
            requested_entity_keys=normalized_entity_keys,
            requested_factor_ids=normalized_factor_ids,
            requested_source_names=normalized_source_names if normalized_factor_ids else None,
        )
        source_coverage = self.load_source_coverage(
            source_names=normalized_source_names,
            factor_ids=normalized_factor_ids,
            entity_keys=normalized_entity_keys,
        )
        coverage_rows = source_coverage.get("sources", [])
        ai_ready_source_names = sorted(
            {
                str(row["source_name"])
                for row in coverage_rows
                if row.get("is_ready_for_ai")
            }
        )
        ai_excluded_source_names = self._blocked_bundle_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=raw_rows,
            coverage_rows=coverage_rows,
        )
        rows = [
            row
            for row in raw_rows
            if str(row["source_name"]) not in ai_excluded_source_names
        ]
        rows_by_entity: dict[str, dict[str, dict]] = {}
        for row in rows:
            rows_by_entity.setdefault(str(row["entity_key"]), {})[str(row["factor_id"])] = row
        latest_observation_time = self._latest_observation_time(rows)
        raw_latest_observation_time = self._latest_observation_time(raw_rows)
        observed_factor_ids = {
            str(row["factor_id"])
            for row in rows
        }
        quality_summary = summarize_quality_flag_counts(rows)
        raw_quality_summary = summarize_quality_flag_counts(raw_rows)
        source_counts = self._count_rows_by_source(rows)
        raw_source_counts = self._count_rows_by_source(raw_rows)
        entities = []
        for entity_key, row_map in rows_by_entity.items():
            quality_breakdown = summarize_quality_flag_counts(row_map.values())
            entities.append(
                {
                    "entity_key": entity_key,
                    "observation_time": max(
                        row["observation_time_dt"]
                        for row in row_map.values()
                    ).isoformat(),
                    "quality_flag": self._entity_quality_flag(
                        row_map,
                        [
                            "scheduled_unlock_usd_7d",
                            "circulating_supply",
                            "staking_ratio",
                        ],
                    ),
                    "quality_breakdown": quality_breakdown["breakdown"],
                    "quality_ready_ratio": quality_breakdown["ready_ratio"],
                    "observed_factor_count": len(row_map),
                    "expected_factor_count": len(expected_factor_ids),
                    "available_factor_ids": sorted(row_map),
                    "missing_factor_ids": [
                        factor_id
                        for factor_id in expected_factor_ids
                        if factor_id not in row_map
                    ],
                    "source_names": sorted(
                        {
                            str(row["source_name"])
                            for row in row_map.values()
                        }
                    ),
                    "circulating_supply": (row_map.get("circulating_supply") or {}).get("value"),
                    "float_supply": (row_map.get("float_supply") or {}).get("value"),
                    "inflation_rate_annualized": (
                        (row_map.get("inflation_rate_annualized") or {}).get("value")
                    ),
                    "scheduled_unlock_usd_7d": (
                        (row_map.get("scheduled_unlock_usd_7d") or {}).get("value")
                    ),
                    "scheduled_unlock_pct_float_7d": (
                        (row_map.get("scheduled_unlock_pct_float_7d") or {}).get("value")
                    ),
                    "scheduled_unlock_usd_30d": (
                        (row_map.get("scheduled_unlock_usd_30d") or {}).get("value")
                    ),
                    "realized_unlock_usd_24h": (
                        (row_map.get("realized_unlock_usd_24h") or {}).get("value")
                    ),
                    "treasury_wallet_inflow": (
                        (row_map.get("treasury_wallet_inflow") or {}).get("value")
                    ),
                    "treasury_wallet_outflow": (
                        (row_map.get("treasury_wallet_outflow") or {}).get("value")
                    ),
                    "foundation_wallet_netflow": (
                        (row_map.get("foundation_wallet_netflow") or {}).get("value")
                    ),
                    "staking_ratio": (row_map.get("staking_ratio") or {}).get("value"),
                    "staking_ratio_change_7d": (
                        (row_map.get("staking_ratio_change_7d") or {}).get("value")
                    ),
                }
            )
        entities.sort(
            key=lambda item: (
                -abs(float(item["scheduled_unlock_usd_7d"] or 0.0)),
                item["entity_key"],
            )
        )
        source_health = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "registry_required": row["registry_required"],
                "registry_ready": row["registry_ready"],
                "registry_record_count": row["registry_record_count"],
                "registry_ready_entity_count": row["registry_ready_entity_count"],
                "registry_unready_entity_count": row["registry_unready_entity_count"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "data_quality_flags": row["data_quality_flags"],
                "quality_notes": row["quality_notes"],
            }
            for row in source_coverage.get("sources", [])
        ]
        coverage_by_source = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "registry_required": row["registry_required"],
                "registry_ready": row["registry_ready"],
                "registry_record_count": row["registry_record_count"],
                "registry_ready_entity_count": row["registry_ready_entity_count"],
                "registry_unready_entity_count": row["registry_unready_entity_count"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "data_quality_flags": row["data_quality_flags"],
            }
            for row in source_coverage.get("sources", [])
        ]
        data_quality_flags, quality_notes = self._build_context_quality(
            entities=entities,
            expected_entity_keys=expected_entity_keys,
            expected_factor_ids=expected_factor_ids,
            observed_factor_ids=observed_factor_ids,
            quality_summary=quality_summary,
            coverage_rows=coverage_rows,
            requested_entity_keys=normalized_entity_keys,
            configured_universe_summary=configured_universe_summary,
        )
        raw_upcoming_unlock_events = self._load_upcoming_unlock_events(
            entity_keys=normalized_entity_keys,
        )
        upcoming_unlock_events = [
            event
            for event in raw_upcoming_unlock_events
            if str(event["source_name"]) not in ai_excluded_source_names
        ]
        unlock_horizon_summary = self._build_unlock_horizon_summary(
            upcoming_unlock_events,
            self._utc_now_naive(),
        )
        raw_unlock_horizon_summary = self._build_unlock_horizon_summary(
            raw_upcoming_unlock_events,
            self._utc_now_naive(),
        )
        unlock_event_source_counts: dict[str, int] = {}
        for event in upcoming_unlock_events:
            source_name = str(event["source_name"])
            unlock_event_source_counts[source_name] = (
                unlock_event_source_counts.get(source_name, 0) + 1
            )
        raw_unlock_event_source_counts: dict[str, int] = {}
        for event in raw_upcoming_unlock_events:
            source_name = str(event["source_name"])
            raw_unlock_event_source_counts[source_name] = (
                raw_unlock_event_source_counts.get(source_name, 0) + 1
            )
        missing_entity_keys = [
            entity_key
            for entity_key in expected_entity_keys
            if entity_key not in rows_by_entity
        ]
        raw_observed_entity_keys = {
            str(row["entity_key"])
            for row in raw_rows
        }
        missing_factor_ids = [
            factor_id
            for factor_id in expected_factor_ids
            if factor_id not in observed_factor_ids
        ]
        return {
            "as_of": latest_observation_time.isoformat() if latest_observation_time else None,
            "raw_as_of": (
                raw_latest_observation_time.isoformat()
                if raw_latest_observation_time
                else None
            ),
            "row_count": len(rows),
            "raw_row_count": len(raw_rows),
            "entity_count": len(entities),
            "raw_entity_count": len(raw_observed_entity_keys),
            "source_counts": source_counts,
            "raw_source_counts": raw_source_counts,
            "ai_ready_source_names": ai_ready_source_names,
            "ai_excluded_source_names": sorted(ai_excluded_source_names),
            "ai_excluded_sources": ai_excluded_sources,
            "configured_universe_summary": configured_universe_summary,
            "coverage_summary": {
                "expected_entity_count": len(expected_entity_keys),
                "observed_entity_count": len(entities),
                "raw_observed_entity_count": len(raw_observed_entity_keys),
                "expected_factor_count": len(expected_factor_ids),
                "observed_factor_count": len(observed_factor_ids),
                "raw_observed_factor_count": len(
                    {
                        str(row["factor_id"])
                        for row in raw_rows
                    }
                ),
                "expected_point_count": (
                    len(expected_entity_keys) * len(expected_factor_ids)
                    if expected_entity_keys and expected_factor_ids
                    else None
                ),
                "observed_point_count": len(rows),
                "raw_observed_point_count": len(raw_rows),
                "missing_entity_keys": missing_entity_keys,
                "missing_factor_ids": missing_factor_ids,
                "ai_excluded_source_names": sorted(ai_excluded_source_names),
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
            "upcoming_unlock_event_count": len(upcoming_unlock_events),
            "raw_upcoming_unlock_event_count": len(raw_upcoming_unlock_events),
            "unlock_event_source_counts": unlock_event_source_counts,
            "raw_unlock_event_source_counts": raw_unlock_event_source_counts,
            "unlock_horizon_summary": unlock_horizon_summary,
            "raw_unlock_horizon_summary": raw_unlock_horizon_summary,
            "upcoming_unlock_events": upcoming_unlock_events[:20],
            "unlock_watchlist": entities[:5],
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
            "entities": entities,
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
        sources = load_tokenomics_sources(
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
            FROM latest_tokenomics_timeseries
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
            FROM latest_tokenomics_timeseries
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
                WHERE module_name = 'tokenomics_data'
                  AND source_name IN ({placeholders})
                GROUP BY source_name
            ) AS latest
                ON runs.id = latest.latest_id
            """,
            tuple(source_name_list),
        )
        run_map = {str(row["source_name"]): dict(row) for row in run_rows}
        entity_registry_rows = load_tokenomics_entities(
            source_names=normalized_source_names,
            entity_keys=normalized_entity_keys,
        )
        entity_registry_rows_by_source: dict[str, list[dict[str, object]]] = {}
        for row in entity_registry_rows:
            entity_registry_rows_by_source.setdefault(
                str(row["source_name"]),
                [],
            ).append(row)
        expected_entity_counts: dict[str, int] = {}
        for row in entity_registry_rows:
            source_name = str(row["source_name"])
            expected_entity_counts[source_name] = expected_entity_counts.get(source_name, 0) + 1
        factor_registry_rows = load_tokenomics_factors(
            factor_ids=normalized_factor_ids,
            source_names=normalized_source_names,
            enabled_only=False,
        )
        expected_factor_counts: dict[str, int] = {}
        for factor in factor_registry_rows:
            expected_factor_counts[factor.source_name] = (
                expected_factor_counts.get(factor.source_name, 0) + 1
            )
        interval_map = {
            "circulating_supply": TOKENOMICS_CONFIG["circulating_supply_interval_seconds"],
            "unlock_schedule": TOKENOMICS_CONFIG["unlock_schedule_interval_seconds"],
            "unlock_realization": TOKENOMICS_CONFIG["unlock_realization_interval_seconds"],
            "treasury_wallet_flow": TOKENOMICS_CONFIG["treasury_wallet_flow_interval_seconds"],
            "staking_ratio": TOKENOMICS_CONFIG["staking_ratio_interval_seconds"],
        }
        rows = []
        now = self._utc_now_naive()
        for source in sources:
            latest_meta = latest_map.get(source.source_name, {})
            run_meta = run_map.get(source.source_name, {})
            expected_entity_count = expected_entity_counts.get(source.source_name, 0)
            expected_factor_count = expected_factor_counts.get(source.source_name, 0)
            latest_entity_count = int(latest_meta.get("latest_entity_count") or 0)
            latest_factor_count = int(latest_meta.get("latest_factor_count") or 0)
            quality_summary = summarize_quality_flag_counts(
                quality_counts_map.get(source.source_name, {})
            )
            source_entity_rows = entity_registry_rows_by_source.get(source.source_name, [])
            registry_status = self._source_registry_status(
                source.source_name,
                source_entity_rows,
            )
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = (last_run_finished_at if isinstance(last_run_finished_at, datetime) else datetime.fromisoformat(last_run_finished_at)) if last_run_finished_at else None
            interval_seconds = interval_map.get(source.source_name, 3600)
            is_stale = last_run_dt is None or (now - last_run_dt).total_seconds() > interval_seconds * 3
            configuration_ready = bool(source.endpoint)
            health_status = resolve_source_health_status(
                enabled=bool(source.enabled),
                configuration_ready=configuration_ready,
                last_run_status=run_meta.get("status"),
                latest_point_count=int(latest_meta.get("latest_point_count") or 0),
                is_stale=is_stale,
            )
            is_ready_for_ai = self._is_source_ready_for_ai(
                health_status=health_status,
                expected_entity_count=expected_entity_count,
                latest_entity_count=latest_entity_count,
                expected_factor_count=expected_factor_count,
                latest_factor_count=latest_factor_count,
                quality_summary=quality_summary,
                registry_ready=bool(registry_status["registry_ready"]),
            )
            data_quality_flags: list[str] = []
            quality_notes: list[str] = []
            if latest_factor_count and expected_factor_count and latest_factor_count < expected_factor_count:
                data_quality_flags.append("factor_coverage_incomplete")
                quality_notes.append("当前已落库 factor 数少于设计目标，AI 看到的 tokenomics 结构仍不完整。")
            if latest_entity_count and expected_entity_count and latest_entity_count < expected_entity_count:
                data_quality_flags.append("entity_coverage_incomplete")
                quality_notes.append("当前实体覆盖少于注册表目标，AI 只看到了部分资产的供给侧证据。")
            if registry_status["registry_required"] and not registry_status["registry_ready"]:
                data_quality_flags.append("registry_not_ai_ready")
                quality_notes.extend(
                    str(note)
                    for note in registry_status["registry_quality_notes"]
                    if str(note)
                )
            if health_status == "ready" and not is_ready_for_ai:
                quality_notes.append(
                    "当前 source 虽然最近运行成功，但 latest 快照仍未达到可直接给 AI 使用的质量门槛。"
                )
            if quality_summary["partial_count"]:
                data_quality_flags.append("partial_points_present")
                quality_notes.append("latest 快照里存在 partial tokenomics 样本，说明部分供给侧字段尚未完整。")
            if quality_summary["fallback_count"]:
                data_quality_flags.append("fallback_points_present")
                quality_notes.append("latest 快照里存在 fallback tokenomics 样本，说明部分字段来自降级路径或近似值。")
            if quality_summary["stale_count"]:
                data_quality_flags.append("stale_points_present")
                quality_notes.append("latest 快照里存在 stale tokenomics 样本，不应视为当前最新供给状态。")
            if quality_summary["unknown_count"]:
                data_quality_flags.append("unknown_quality_flag_present")
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
                    "configuration_ready": configuration_ready,
                    "registry_required": registry_status["registry_required"],
                    "registry_ready": registry_status["registry_ready"],
                    "registry_record_count": registry_status["registry_record_count"],
                    "registry_ready_entity_count": registry_status["registry_ready_entity_count"],
                    "registry_unready_entity_count": registry_status["registry_unready_entity_count"],
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
                    "data_quality_flags": data_quality_flags,
                    "quality_notes": quality_notes,
                }
            )
        rows.sort(key=lambda item: (item["health_status"] != "ready", item["is_stale"], item["source_name"]))
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
        local_service = TokenomicsDataService(client=self.client, db=local_db)
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
        enabled_sources = {source.source_name for source in load_tokenomics_sources()}
        source_config = {
            "circulating_supply": TOKENOMICS_CONFIG["circulating_supply_interval_seconds"],
            "unlock_schedule": TOKENOMICS_CONFIG["unlock_schedule_interval_seconds"],
            "unlock_realization": TOKENOMICS_CONFIG["unlock_realization_interval_seconds"],
            "treasury_wallet_flow": TOKENOMICS_CONFIG["treasury_wallet_flow_interval_seconds"],
            "staking_ratio": TOKENOMICS_CONFIG["staking_ratio_interval_seconds"],
        }
        source_titles = {
            "circulating_supply": "流通盘采集",
            "unlock_schedule": "未来解锁计划采集",
            "unlock_realization": "已实现解锁采集",
            "treasury_wallet_flow": "基金会钱包流向采集",
            "staking_ratio": "质押率采集",
        }
        for source_name, interval_seconds in source_config.items():
            if source_name not in enabled_sources:
                continue
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=interval_seconds,
                id=f"tokenomics_{source_name}",
                name=source_titles[source_name],
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, interval_seconds),
                kwargs={
                    "source_name": source_name,
                    "entity_keys": entity_keys,
                    "interval": interval or TOKENOMICS_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or TOKENOMICS_CONFIG["default_lookback_hours"],
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
        enabled_sources = {source.source_name for source in load_tokenomics_sources()}
        source_config = {
            "circulating_supply": TOKENOMICS_CONFIG["circulating_supply_interval_seconds"],
            "unlock_schedule": TOKENOMICS_CONFIG["unlock_schedule_interval_seconds"],
            "unlock_realization": TOKENOMICS_CONFIG["unlock_realization_interval_seconds"],
            "treasury_wallet_flow": TOKENOMICS_CONFIG["treasury_wallet_flow_interval_seconds"],
            "staking_ratio": TOKENOMICS_CONFIG["staking_ratio_interval_seconds"],
        }
        source_titles = {
            "circulating_supply": "流通盘采集(async)",
            "unlock_schedule": "未来解锁计划采集(async)",
            "unlock_realization": "已实现解锁采集(async)",
            "treasury_wallet_flow": "基金会钱包流向采集(async)",
            "staking_ratio": "质押率采集(async)",
        }
        for source_name, interval_seconds in source_config.items():
            if source_name not in enabled_sources:
                continue
            scheduler.add_job(
                self._run_source_job,
                "interval",
                seconds=interval_seconds,
                id=f"tokenomics_{source_name}",
                name=source_titles[source_name],
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(120, interval_seconds),
                kwargs={
                    "source_name": source_name,
                    "entity_keys": entity_keys,
                    "interval": interval or TOKENOMICS_CONFIG["default_interval"],
                    "lookback_hours": lookback_hours or TOKENOMICS_CONFIG["default_lookback_hours"],
                },
            )
        return scheduler

    def close(self):
        self.db.close()
