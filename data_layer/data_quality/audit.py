from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from database.db_manager import DBManager


@dataclass(frozen=True)
class EvidenceBandSpec:
    band_name: str
    module_name: str
    description: str
    required: bool
    latest_tables: tuple[str, ...]
    history_tables: tuple[str, ...]
    minimum_ai_ready_sources: int = 1


DEFAULT_EVIDENCE_BAND_SPECS: tuple[EvidenceBandSpec, ...] = (
    EvidenceBandSpec(
        band_name="exchange",
        module_name="exchange_data",
        description="交易所微观结构、价格、盘口、资金费率与 basis 快照。",
        required=True,
        latest_tables=(
            "latest_tickers",
            "latest_funding_rates",
            "latest_orderbook_snapshots",
            "latest_basis_snapshots",
        ),
        history_tables=(
            "tickers",
            "funding_rates",
            "orderbook_snapshots",
            "basis_snapshots",
        ),
    ),
    EvidenceBandSpec(
        band_name="macro",
        module_name="macro_data",
        description="跨市场宏观利率、美元、风险偏好与商品背景。",
        required=True,
        latest_tables=("latest_macro_timeseries",),
        history_tables=("macro_timeseries",),
    ),
    EvidenceBandSpec(
        band_name="news",
        module_name="news_data",
        description="公开新闻、监管、治理与项目公告文本流。",
        required=True,
        latest_tables=("news_articles",),
        history_tables=("news_articles",),
    ),
    EvidenceBandSpec(
        band_name="event_calendar",
        module_name="event_calendar_data",
        description="未来宏观、ETF、解锁与升级催化剂日历。",
        required=True,
        latest_tables=("event_calendar_events",),
        history_tables=("event_calendar_events",),
    ),
    EvidenceBandSpec(
        band_name="onchain",
        module_name="onchain_data",
        description="链上资金流、储备、桥流、TVL、网络活跃度。",
        required=True,
        latest_tables=("latest_onchain_timeseries",),
        history_tables=("onchain_timeseries",),
    ),
    EvidenceBandSpec(
        band_name="tokenomics",
        module_name="tokenomics_data",
        description="供给变化、解锁压力、基金会钱包流与质押率。",
        required=True,
        latest_tables=("latest_tokenomics_timeseries", "token_unlock_events"),
        history_tables=("tokenomics_timeseries", "token_unlock_events"),
    ),
    EvidenceBandSpec(
        band_name="options",
        module_name="options_data",
        description="隐含波动率、gamma、墙位、期权持仓与流向。",
        required=True,
        latest_tables=("latest_options_timeseries",),
        history_tables=("options_timeseries",),
    ),
    EvidenceBandSpec(
        band_name="alternative",
        module_name="alternative_data",
        description="稳定币供给、搜索热度、GitHub 活跃度等补充特征。",
        required=False,
        latest_tables=("latest_alternative_timeseries",),
        history_tables=("alternative_timeseries",),
    ),
    EvidenceBandSpec(
        band_name="perpetual_dex",
        module_name="perpetual_dex_data",
        description="dYdX/Hyperliquid/GMX 永续 DEX funding 和成交量。",
        required=False,
        latest_tables=("perp_dex_funding",),
        history_tables=("perp_dex_funding", "perp_dex_volume"),
    ),
    EvidenceBandSpec(
        band_name="onchain_address",
        module_name="onchain_address_data",
        description="Arkham/Etherscan 巨鲸地址画像和资金流。",
        required=False,
        latest_tables=("whale_moves",),
        history_tables=("address_flows", "whale_moves"),
    ),
    EvidenceBandSpec(
        band_name="dex_liquidity",
        module_name="dex_liquidity_data",
        description="Uniswap V3/Curve 池 TVL 和 tick 流动性分布。",
        required=False,
        latest_tables=("dex_pools",),
        history_tables=("dex_pools", "dex_liquidity_events"),
    ),
    EvidenceBandSpec(
        band_name="gas_network",
        module_name="gas_network_data",
        description="以太坊 Gas 价格、网络拥堵和 Gas 尖刺。",
        required=False,
        latest_tables=("gas_prices",),
        history_tables=("gas_prices", "network_congestion", "gas_spikes"),
    ),
    EvidenceBandSpec(
        band_name="governance",
        module_name="governance_data",
        description="Snapshot/Tally DAO 治理提案和投票。",
        required=False,
        latest_tables=("governance_proposals",),
        history_tables=("governance_proposals", "governance_votes", "governance_activity"),
    ),
)


def resolve_evidence_band_status(
    *,
    has_latest_rows: bool,
    has_history_rows: bool,
    ready_for_ai_source_count: int,
    minimum_ai_ready_sources: int,
    unconfigured_source_count: int = 0,
    stale_source_count: int = 0,
) -> str:
    if ready_for_ai_source_count >= minimum_ai_ready_sources and has_latest_rows:
        return "ready"
    if unconfigured_source_count > 0 and not has_latest_rows:
        return "unconfigured"
    if stale_source_count > 0 and has_latest_rows:
        return "stale"
    if has_latest_rows or has_history_rows:
        return "insufficient"
    return "missing"


def build_market_world_summary(
    bands: list[dict[str, object]],
) -> dict[str, object]:
    required_bands = [band for band in bands if bool(band.get("required"))]
    optional_bands = [band for band in bands if not bool(band.get("required"))]
    required_ready_bands = [
        band for band in required_bands if bool(band.get("is_band_ready_for_ai"))
    ]
    missing_or_unconfigured_required = [
        band
        for band in required_bands
        if str(band.get("band_status")) in {"missing", "unconfigured"}
    ]
    insufficient_required = [
        band
        for band in required_bands
        if not bool(band.get("is_band_ready_for_ai"))
        and str(band.get("band_status")) == "insufficient"
    ]

    if len(required_ready_bands) == len(required_bands):
        world_model_status = "ready"
    elif missing_or_unconfigured_required:
        world_model_status = "blocked"
    else:
        world_model_status = "partial"

    critical_gap_bands = [
        band
        for band in required_bands
        if not bool(band.get("is_band_ready_for_ai"))
    ]

    return {
        "world_model_status": world_model_status,
        "is_market_data_ready_for_ai": world_model_status == "ready",
        "required_band_count": len(required_bands),
        "required_ready_band_count": len(required_ready_bands),
        "optional_band_count": len(optional_bands),
        "optional_ready_band_count": sum(
            1 for band in optional_bands if bool(band.get("is_band_ready_for_ai"))
        ),
        "critical_gap_count": len(critical_gap_bands),
        "critical_gap_band_names": [
            str(band["band_name"])
            for band in critical_gap_bands
        ],
        "blocked_band_names": [
            str(band["band_name"])
            for band in missing_or_unconfigured_required
        ],
        "partial_band_names": [
            str(band["band_name"])
            for band in insufficient_required
        ],
    }


class DataLayerAuditService:
    """跨模块真实数据就绪审计。"""

    DEFAULT_AUDIT_SCOPE = "market_world_model"
    DEFAULT_MODULE_NAME = "data_quality"
    DEFAULT_JOB_NAME = "market_world_audit"

    @staticmethod
    def _build_default_service_factories() -> dict[str, Callable[[DBManager], object]]:
        def build_exchange_service(db: DBManager):
            from data_layer.exchange_data.service import ExchangeDataService

            return ExchangeDataService(db=db)

        def build_macro_service(db: DBManager):
            from data_layer.macro_data.service import MacroDataService

            return MacroDataService(db=db)

        def build_news_service(db: DBManager):
            from data_layer.news_data.service import NewsDataService

            return NewsDataService(db=db)

        def build_event_calendar_service(db: DBManager):
            from data_layer.event_calendar_data.service import EventCalendarDataService

            return EventCalendarDataService(db=db)

        def build_onchain_service(db: DBManager):
            from data_layer.onchain_data.service import OnchainDataService

            return OnchainDataService(db=db)

        def build_tokenomics_service(db: DBManager):
            from data_layer.tokenomics_data.service import TokenomicsDataService

            return TokenomicsDataService(db=db)

        def build_options_service(db: DBManager):
            from data_layer.options_data.service import OptionsDataService

            return OptionsDataService(db=db)

        def build_alternative_service(db: DBManager):
            from data_layer.alternative_data.service import AlternativeDataService

            return AlternativeDataService(db=db)

        def build_asset_readiness_service(db: DBManager):
            from logic_layer.asset_readiness.service import AssetReadinessService

            return AssetReadinessService(db=db)

        def build_perpetual_dex_service(db: DBManager):
            from data_layer.perpetual_dex_data.service import PerpDexDataService

            return PerpDexDataService(db=db)

        def build_onchain_address_service(db: DBManager):
            from data_layer.onchain_address_data.service import OnchainAddressService

            return OnchainAddressService(db=db)

        def build_dex_liquidity_service(db: DBManager):
            from data_layer.dex_liquidity_data.service import DexLiquidityService

            return DexLiquidityService(db=db)

        def build_gas_network_service(db: DBManager):
            from data_layer.gas_network_data.service import GasNetworkService

            return GasNetworkService(db=db)

        def build_governance_service(db: DBManager):
            from data_layer.governance_data.service import GovernanceDataService

            return GovernanceDataService(db=db)

        return {
            "exchange_data": build_exchange_service,
            "macro_data": build_macro_service,
            "news_data": build_news_service,
            "event_calendar_data": build_event_calendar_service,
            "onchain_data": build_onchain_service,
            "tokenomics_data": build_tokenomics_service,
            "options_data": build_options_service,
            "alternative_data": build_alternative_service,
            "asset_readiness": build_asset_readiness_service,
            "perpetual_dex_data": build_perpetual_dex_service,
            "onchain_address_data": build_onchain_address_service,
            "dex_liquidity_data": build_dex_liquidity_service,
            "gas_network_data": build_gas_network_service,
            "governance_data": build_governance_service,
        }

    def __init__(
        self,
        db: DBManager | None = None,
        service_factories: Mapping[str, Callable[[DBManager], object]] | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.service_factories = self._build_default_service_factories()
        if service_factories:
            self.service_factories.update(service_factories)

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def init_storage(self):
        self.db.init_analytics_tables()

    def _table_exists(self, table_name: str) -> bool:
        import os
        if os.getenv("DB_BACKEND", "sqlite") == "postgres":
            # PostgreSQL: 查询 information_schema
            row = self.db.fetch_one(
                """
                SELECT COUNT(*) AS count FROM information_schema.tables
                WHERE table_name = ?
                """,
                (table_name,),
            )
        else:
            row = self.db.fetch_one(
                """
                SELECT COUNT(*) AS count FROM (
                    SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name = ?
                    UNION ALL
                    SELECT name FROM sqlite_temp_master WHERE type = 'view' AND name = ?
                )
                """,
                (table_name, table_name),
            )
        return bool(row and int(row["count"] or 0) > 0)

    def _safe_table_count(self, table_name: str) -> int:
        import os
        if os.getenv("DB_BACKEND", "sqlite") == "postgres":
            # PostgreSQL: 尝试跨 schema 查询
            for schema in ("exchange_data", "market_data", "analytics"):
                try:
                    row = self.db.fetch_one(
                        f"SELECT COUNT(*) AS count FROM {schema}.{table_name}"
                    )
                    if row:
                        return int(row["count"] or 0)
                except Exception:
                    continue
            return 0
        else:
            if not self._table_exists(table_name):
                return 0
            row = self.db.fetch_one(f"SELECT COUNT(*) AS count FROM {table_name}")
            return int(row["count"] or 0) if row else 0

    @staticmethod
    def _top_quality_notes(coverage: Mapping[str, object]) -> list[str]:
        notes = coverage.get("quality_notes") or []
        if not isinstance(notes, list):
            return []
        return [
            str(note).strip()
            for note in notes
            if str(note).strip()
        ][:6]

    @staticmethod
    def _top_data_quality_flags(coverage: Mapping[str, object]) -> list[str]:
        flags = coverage.get("data_quality_flags") or []
        if not isinstance(flags, list):
            return []
        return [
            str(flag).strip()
            for flag in flags
            if str(flag).strip()
        ]

    def _load_module_coverage(self, module_name: str) -> Mapping[str, object]:
        factory = self.service_factories.get(module_name)
        if factory is None:
            return {}
        service = factory(None)
        try:
            loader = getattr(service, "load_source_coverage", None)
            if not callable(loader):
                return {}
            return loader()
        except Exception:
            return {}
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
            elif hasattr(service, "db"):
                service.db.close()

    def _load_asset_readiness_summary(
        self,
        audit_payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        factory = self.service_factories.get("asset_readiness")
        if factory is None:
            return {}
        service = factory(None)
        try:
            payload = service.build_latest_context_bundle(
                audit_payload=dict(audit_payload or {}),
            )
        except Exception:
            payload = {}
        finally:
            close = getattr(service, "close", None)
            if callable(close):
                close()
            elif hasattr(service, "db"):
                service.db.close()

        return {
            "asset_count": int(payload.get("asset_count") or 0),
            "ready_asset_count": int(payload.get("ready_asset_count") or 0),
            "partial_asset_count": int(payload.get("partial_asset_count") or 0),
            "thin_asset_count": int(payload.get("thin_asset_count") or 0),
            "blocked_asset_count": int(payload.get("blocked_asset_count") or 0),
            "average_readiness_score": payload.get("average_readiness_score"),
            "data_quality_flag": payload.get("data_quality_flag"),
            "data_quality_flags": list(payload.get("data_quality_flags") or []),
            "quality_notes": [
                str(note).strip()
                for note in (payload.get("quality_notes") or [])
                if str(note).strip()
            ][:6],
            "top_analysis_candidate_assets": list(
                payload.get("top_analysis_candidate_assets") or []
            )[:10],
        }

    def _build_band_report(self, spec: EvidenceBandSpec) -> dict[str, object]:
        coverage = self._load_module_coverage(spec.module_name)
        latest_table_counts = {
            table_name: self._safe_table_count(table_name)
            for table_name in spec.latest_tables
        }
        history_table_counts = {
            table_name: self._safe_table_count(table_name)
            for table_name in spec.history_tables
        }
        ready_for_ai_source_count = int(coverage.get("ready_for_ai_source_count") or 0)
        unconfigured_source_count = int(coverage.get("unconfigured_source_count") or 0)
        stale_source_count = int(coverage.get("stale_source_count") or 0)
        has_latest_rows = any(count > 0 for count in latest_table_counts.values())
        has_history_rows = any(count > 0 for count in history_table_counts.values())
        band_status = resolve_evidence_band_status(
            has_latest_rows=has_latest_rows,
            has_history_rows=has_history_rows,
            ready_for_ai_source_count=ready_for_ai_source_count,
            minimum_ai_ready_sources=spec.minimum_ai_ready_sources,
            unconfigured_source_count=unconfigured_source_count,
            stale_source_count=stale_source_count,
        )

        blocking_reasons: list[str] = []
        if ready_for_ai_source_count < spec.minimum_ai_ready_sources:
            blocking_reasons.append("no_ai_ready_sources")
        if not has_latest_rows:
            blocking_reasons.append("no_latest_rows")
        if not has_history_rows:
            blocking_reasons.append("no_historical_rows")
        if unconfigured_source_count > 0:
            blocking_reasons.append("unconfigured_sources_present")
        if stale_source_count > 0:
            blocking_reasons.append("stale_sources_present")
        if int(coverage.get("problem_source_count") or 0) > 0:
            blocking_reasons.append("problem_sources_present")

        return {
            "band_name": spec.band_name,
            "module_name": spec.module_name,
            "description": spec.description,
            "required": spec.required,
            "band_status": band_status,
            "is_band_ready_for_ai": (
                ready_for_ai_source_count >= spec.minimum_ai_ready_sources and has_latest_rows
            ),
            "source_count": int(coverage.get("source_count") or 0),
            "ready_source_count": int(coverage.get("ready_source_count") or 0),
            "problem_source_count": int(coverage.get("problem_source_count") or 0),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": int(
                coverage.get("not_ready_for_ai_source_count") or 0
            ),
            "unconfigured_source_count": unconfigured_source_count,
            "stale_source_count": stale_source_count,
            "latest_table_counts": latest_table_counts,
            "history_table_counts": history_table_counts,
            "has_latest_rows": has_latest_rows,
            "has_history_rows": has_history_rows,
            "blocking_reasons": blocking_reasons,
            "data_quality_flags": self._top_data_quality_flags(coverage),
            "quality_notes": self._top_quality_notes(coverage),
        }

    def load_market_world_audit(self) -> dict[str, object]:
        bands = [
            self._build_band_report(spec)
            for spec in DEFAULT_EVIDENCE_BAND_SPECS
        ]
        summary = build_market_world_summary(bands)
        audit_payload = {
            "summary": summary,
            "bands": bands,
        }
        asset_readiness_summary = self._load_asset_readiness_summary(
            audit_payload=audit_payload,
        )
        return {
            "as_of": self._utc_now_naive().isoformat(),
            "summary": summary,
            "bands": bands,
            "asset_readiness_summary": asset_readiness_summary,
        }

    def save_market_world_audit_snapshot(
        self,
        audit: Mapping[str, object] | None = None,
        *,
        audit_scope: str | None = None,
    ) -> dict[str, object]:
        self.init_storage()
        payload = dict(audit or self.load_market_world_audit())
        summary = dict(payload.get("summary") or {})
        bands = list(payload.get("bands") or [])
        asset_readiness_summary = dict(payload.get("asset_readiness_summary") or {})
        scope = str(audit_scope or self.DEFAULT_AUDIT_SCOPE).strip() or self.DEFAULT_AUDIT_SCOPE
        snapshot_time = str(payload.get("as_of") or self._utc_now_naive().isoformat())
        self.db.execute(
            """
            INSERT INTO data_quality_audit_snapshots (
                audit_scope, snapshot_time, world_model_status, is_market_data_ready_for_ai,
                required_band_count, required_ready_band_count,
                optional_band_count, optional_ready_band_count,
                critical_gap_count, critical_gap_band_names_json,
                blocked_band_names_json, partial_band_names_json,
                bands_json, raw_audit_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope,
                snapshot_time,
                summary.get("world_model_status"),
                1 if summary.get("is_market_data_ready_for_ai") else 0,
                int(summary.get("required_band_count") or 0),
                int(summary.get("required_ready_band_count") or 0),
                int(summary.get("optional_band_count") or 0),
                int(summary.get("optional_ready_band_count") or 0),
                int(summary.get("critical_gap_count") or 0),
                json.dumps(
                    summary.get("critical_gap_band_names") or [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    summary.get("blocked_band_names") or [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(
                    summary.get("partial_band_names") or [],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                json.dumps(bands, ensure_ascii=False, separators=(",", ":")),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.db.commit()
        row = self.db.fetch_one(
            """
            SELECT id, audit_scope, snapshot_time, world_model_status,
                   is_market_data_ready_for_ai, critical_gap_count
            FROM data_quality_audit_snapshots
            WHERE audit_scope = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (scope,),
        )
        return dict(row) if row else {
            "audit_scope": scope,
            "snapshot_time": snapshot_time,
            "world_model_status": summary.get("world_model_status"),
        }

    def run_market_world_audit(
        self,
        *,
        audit_scope: str | None = None,
    ) -> dict[str, object]:
        scope = str(audit_scope or self.DEFAULT_AUDIT_SCOPE).strip() or self.DEFAULT_AUDIT_SCOPE
        started_at = self._utc_now_naive()
        status = "success"
        message = None
        audit_payload: dict[str, object] | None = None
        snapshot: dict[str, object] | None = None

        try:
            self.init_storage()
            audit_payload = self.load_market_world_audit()
            snapshot = self.save_market_world_audit_snapshot(
                audit_payload,
                audit_scope=scope,
            )
            summary = dict(audit_payload.get("summary") or {})
            message = (
                "world_model_status="
                f"{summary.get('world_model_status')} "
                f"critical_gap_count={int(summary.get('critical_gap_count') or 0)}"
            )
            return {
                "audit": audit_payload,
                "snapshot": snapshot,
                "summary": summary,
            }
        except Exception as exc:
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            finished_at = self._utc_now_naive()
            summary = dict((audit_payload or {}).get("summary") or {})
            metadata = {
                "audit_scope": scope,
                "world_model_status": summary.get("world_model_status"),
                "is_market_data_ready_for_ai": bool(
                    summary.get("is_market_data_ready_for_ai")
                ),
                "critical_gap_count": int(summary.get("critical_gap_count") or 0),
                "critical_gap_band_names": summary.get("critical_gap_band_names") or [],
                "blocked_band_names": summary.get("blocked_band_names") or [],
                "partial_band_names": summary.get("partial_band_names") or [],
                "required_band_count": int(summary.get("required_band_count") or 0),
                "required_ready_band_count": int(
                    summary.get("required_ready_band_count") or 0
                ),
                "asset_count": int(
                    ((audit_payload or {}).get("asset_readiness_summary") or {}).get("asset_count")
                    or 0
                ),
                "ready_asset_count": int(
                    ((audit_payload or {}).get("asset_readiness_summary") or {}).get(
                        "ready_asset_count"
                    )
                    or 0
                ),
                "partial_asset_count": int(
                    ((audit_payload or {}).get("asset_readiness_summary") or {}).get(
                        "partial_asset_count"
                    )
                    or 0
                ),
                "snapshot_id": snapshot.get("id") if snapshot else None,
            }
            try:
                self.db.record_collection_run(
                    module_name=self.DEFAULT_MODULE_NAME,
                    source_name=scope,
                    job_name=self.DEFAULT_JOB_NAME,
                    status=status,
                    item_count=len((audit_payload or {}).get("bands") or []),
                    started_at=started_at.isoformat(),
                    finished_at=finished_at.isoformat(),
                    duration_seconds=(finished_at - started_at).total_seconds(),
                    message=message,
                    metadata_json=json.dumps(
                        metadata,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            except Exception as record_exc:
                logger.warning(
                    "记录数据质量审计运行台账失败 [{}]: {}",
                    scope,
                    record_exc,
                )

    def build_scheduler(
        self,
        *,
        interval_seconds: int,
        audit_scope: str | None = None,
    ) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        interval_seconds = max(1, int(interval_seconds))
        scope = str(audit_scope or self.DEFAULT_AUDIT_SCOPE).strip() or self.DEFAULT_AUDIT_SCOPE
        scheduler.add_job(
            lambda: self.run_market_world_audit(audit_scope=scope),
            trigger="interval",
            seconds=interval_seconds,
            id=self.DEFAULT_JOB_NAME,
            name="跨模块市场世界模型审计",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(120, interval_seconds),
        )
        return scheduler

    def close(self):
        self.db.close()
