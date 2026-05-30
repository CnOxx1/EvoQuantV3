import json
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import MACRO_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import (
    is_quality_summary_ai_ready,
    resolve_source_health_status,
    summarize_health_rows,
    summarize_quality_flag_counts,
)
from data_layer.macro_data.client import MacroDataClient
from data_layer.macro_data.market import MacroMarketCollector
from data_layer.macro_data.rates import MacroRateCollector
from data_layer.macro_data.sources import load_macro_factors


class MacroDataService:
    """宏观数据模块统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    MINIMUM_FACTOR_COUNT_FOR_MARKET_BREADTH = 12
    MINIMUM_CATEGORY_COUNT_FOR_MARKET_BREADTH = 8
    MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH = 2
    MINIMUM_MARKET_REGION_COUNT_FOR_MARKET_BREADTH = 2
    MACRO_EVIDENCE_GROUP_SPECS = (
        (
            "dollar_anchor",
            "any",
            ("dxy",),
            "缺少美元主锚，AI 对全球流动性收紧/放松的判断会变弱。",
            True,
        ),
        (
            "front_end_rates",
            "any",
            ("ust_3m_yield", "ust_2y_yield", "fed_funds_upper"),
            "缺少前端利率锚，AI 难以判断现金收益率和政策预期对加密估值的压制程度。",
            True,
        ),
        (
            "rates_curve",
            "all",
            ("ust_2y_yield", "ust_10y_yield"),
            "缺少 2Y/10Y 利率曲线，AI 无法稳定识别政策预期和增长预期的分化。",
            True,
        ),
        (
            "long_duration",
            "any",
            ("ust_30y_yield",),
            "缺少 30Y 长端利率，AI 难以补充识别期限溢价和远端通胀定价变化。",
            False,
        ),
        (
            "real_rates",
            "any",
            ("ust_10y_real_yield",),
            "缺少 10Y 真实利率，AI 难以判断加密等风险资产的真实贴现压力。",
            True,
        ),
        (
            "inflation_expectation",
            "any",
            ("us_10y_breakeven_inflation",),
            "缺少 10Y 盈亏平衡通胀率，AI 难以拆解名义利率变化里有多少来自通胀预期。",
            True,
        ),
        (
            "credit_stress",
            "any",
            ("us_bbb_oas", "us_high_yield_oas"),
            "缺少信用利差，AI 看不到传统信用市场对风险偏好的提前收缩或修复。",
            True,
        ),
        (
            "equity_risk",
            "any",
            ("nasdaq_100", "sp500"),
            "缺少美股风险偏好锚，AI 难以判断加密与传统风险资产是否同向共振。",
            True,
        ),
        (
            "volatility_risk",
            "any",
            ("vix",),
            "缺少 VIX，AI 看不到传统市场的显性风险厌恶抬升。",
            True,
        ),
        (
            "defensive_asset",
            "any",
            ("gold_spot",),
            "缺少黄金代理，AI 无法交叉验证避险资产是否同步走强。",
            True,
        ),
        (
            "energy_shock",
            "any",
            ("wti_crude",),
            "缺少原油代理，AI 对通胀与地缘冲击的识别会变弱。",
            True,
        ),
        (
            "policy_rate",
            "any",
            ("fed_funds_upper",),
            "缺少联邦基金目标区间上沿，AI 难以稳定锚定当前政策利率水平。",
            False,
        ),
    )

    def __init__(
        self,
        client: MacroDataClient | None = None,
        db: DBManager | None = None,
        market_collector: MacroMarketCollector | None = None,
        rate_collector: MacroRateCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or MacroDataClient()
        self.market_collector = market_collector or MacroMarketCollector(self.client, self.db)
        self.rate_collector = rate_collector or MacroRateCollector(self.client, self.db)

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
                    "raw_factor_count": len(
                        {
                            str(row["factor_id"])
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
            "yahoo_finance": MACRO_CONFIG["market_interval_seconds"],
            "fred": MACRO_CONFIG["level_interval_seconds"],
        }.get(source_name, 86400)

    @staticmethod
    def _factor_rank(row: dict) -> tuple:
        interval_rank = {"1h": 2, "1d": 1}.get(str(row.get("interval") or ""), 0)
        observation_time = row.get("observation_time") or ""
        return (interval_rank, observation_time)

    def _run_collection_job(
        self,
        *,
        source_name: str,
        job_name: str,
        func,
        metadata: dict[str, object] | None = None,
        db: DBManager | None = None,
    ):
        target_db = db or self.db
        started_at = self._utc_now_naive()
        status = "success"
        message = None
        item_count = 0
        result = None
        captured_exception = None
        try:
            result = func()
            item_count = self._count_collection_items(result)
            if item_count == 0:
                status = "empty"
        except Exception as exc:
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            captured_exception = exc

        finished_at = self._utc_now_naive()
        target_db.record_collection_run(
            module_name="macro_data",
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

    @staticmethod
    def _build_factor_meta() -> dict[str, dict]:
        return {
            factor.factor_id: {
                "name": factor.name,
                "category": factor.category,
                "factor_type": factor.factor_type,
                "default_interval": factor.default_interval,
                "source_name": factor.source_name,
                "source_symbol": factor.source_symbol,
                "enabled": factor.enabled,
                "staleness_ttl_seconds": factor.staleness_ttl_seconds,
                "market_region": factor.market_region,
                "market_session": factor.market_session,
            }
            for factor in load_macro_factors(enabled_only=False)
        }

    @staticmethod
    def _normalize_factor_ids(factor_ids: list[str] | None) -> list[str]:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for raw_factor_id in factor_ids or []:
            factor_id = str(raw_factor_id).strip()
            if not factor_id:
                continue
            if factor_id in seen_ids:
                continue
            seen_ids.add(factor_id)
            normalized_ids.append(factor_id)
        return normalized_ids

    @classmethod
    def _load_expected_factors(
        cls,
        factor_ids: list[str] | None = None,
    ):
        normalized_factor_ids = cls._normalize_factor_ids(factor_ids)
        if normalized_factor_ids:
            return load_macro_factors(
                enabled_only=False,
                factor_ids=normalized_factor_ids,
            )
        return load_macro_factors(enabled_only=True)

    @staticmethod
    def _configured_group_is_covered(
        configured_factor_ids: set[str],
        mode: str,
        candidate_factor_ids: tuple[str, ...],
    ) -> bool:
        if mode == "all":
            return all(
                factor_id in configured_factor_ids
                for factor_id in candidate_factor_ids
            )
        return any(
            factor_id in configured_factor_ids
            for factor_id in candidate_factor_ids
        )

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        expected_factors: list,
        requested_factor_ids: list[str] | None = None,
    ) -> dict[str, object]:
        scope_kind = "filtered" if requested_factor_ids else "default"
        configured_factor_ids = sorted(
            {
                str(factor.factor_id)
                for factor in expected_factors
                if str(factor.factor_id).strip()
            }
        )
        configured_categories = sorted(
            {
                str(factor.category)
                for factor in expected_factors
                if str(factor.category).strip()
            }
        )
        configured_source_names = sorted(
            {
                str(factor.source_name)
                for factor in expected_factors
                if str(factor.source_name).strip()
            }
        )
        configured_market_regions = sorted(
            {
                str(factor.market_region)
                for factor in expected_factors
                if str(factor.market_region).strip()
            }
        )
        configured_market_sessions = sorted(
            {
                str(factor.market_session)
                for factor in expected_factors
                if str(factor.market_session).strip()
            }
        )
        configured_factor_id_set = set(configured_factor_ids)
        required_semantic_groups = [
            group_name
            for group_name, _mode, _candidate_factor_ids, _note, required_for_breadth in cls.MACRO_EVIDENCE_GROUP_SPECS
            if required_for_breadth
        ]
        covered_semantic_groups = [
            group_name
            for group_name, mode, candidate_factor_ids, _note, required_for_breadth in cls.MACRO_EVIDENCE_GROUP_SPECS
            if required_for_breadth
            and cls._configured_group_is_covered(
                configured_factor_id_set,
                mode,
                candidate_factor_ids,
            )
        ]
        missing_semantic_groups = [
            group_name
            for group_name in required_semantic_groups
            if group_name not in covered_semantic_groups
        ]
        factor_count = len(configured_factor_ids)
        category_count = len(configured_categories)
        source_count = len(configured_source_names)
        market_region_count = len(configured_market_regions)
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = (
                "sufficient"
                if (
                    factor_count >= cls.MINIMUM_FACTOR_COUNT_FOR_MARKET_BREADTH
                    and category_count >= cls.MINIMUM_CATEGORY_COUNT_FOR_MARKET_BREADTH
                    and source_count >= cls.MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH
                    and market_region_count >= cls.MINIMUM_MARKET_REGION_COUNT_FOR_MARKET_BREADTH
                    and not missing_semantic_groups
                )
                else "limited"
            )
        return {
            "scope_kind": scope_kind,
            "configured_factor_ids": configured_factor_ids,
            "configured_categories": configured_categories,
            "configured_source_names": configured_source_names,
            "configured_market_regions": configured_market_regions,
            "configured_market_sessions": configured_market_sessions,
            "factor_count": factor_count,
            "category_count": category_count,
            "source_count": source_count,
            "market_region_count": market_region_count,
            "market_session_count": len(configured_market_sessions),
            "minimum_factor_count_for_market_breadth": cls.MINIMUM_FACTOR_COUNT_FOR_MARKET_BREADTH,
            "minimum_category_count_for_market_breadth": cls.MINIMUM_CATEGORY_COUNT_FOR_MARKET_BREADTH,
            "minimum_source_count_for_market_breadth": cls.MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH,
            "minimum_market_region_count_for_market_breadth": cls.MINIMUM_MARKET_REGION_COUNT_FOR_MARKET_BREADTH,
            "required_semantic_groups_for_market_breadth": required_semantic_groups,
            "covered_semantic_groups": covered_semantic_groups,
            "missing_semantic_groups": missing_semantic_groups,
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    @classmethod
    def _build_context_quality(
        cls,
        *,
        rows: list[dict],
        raw_row_count: int,
        ai_excluded_source_count: int,
        expected_factor_ids: list[str],
        quality_summary: dict[str, object],
        coverage_rows: list[dict],
        configured_universe_summary: dict[str, object] | None = None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []
        observed_factor_ids = {
            str(row["factor_id"])
            for row in rows
        }
        expected_factor_id_set = set(expected_factor_ids)

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
        if non_ready_sources:
            flags.append("macro_source_not_ready_present")
            notes.append(
                "当前仍有未 ready 的 macro source: "
                f"{', '.join(non_ready_sources)}。"
            )
        if not_ready_for_ai_sources:
            flags.append("macro_source_not_ready_for_ai_present")
            notes.append(
                "当前仍有 macro source 虽然最近运行成功，但 latest 快照还不适合直接作为 AI 的宏观锚点: "
                f"{', '.join(not_ready_for_ai_sources)}。"
            )

        if (
            configured_universe_summary
            and configured_universe_summary.get("scope_kind") == "default"
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            flags.append("macro_configured_market_breadth_limited")
            missing_groups = configured_universe_summary.get("missing_semantic_groups") or []
            notes.append(
                "当前 macro 默认配置宇宙只启用了 "
                f"{int(configured_universe_summary.get('factor_count') or 0)} 个因子/"
                f"{int(configured_universe_summary.get('category_count') or 0)} 个类别，"
                "AI 看到的是裁剪后的宏观世界观；"
                "缺少的关键维度有: "
                f"{', '.join(missing_groups[:8])}"
                f"{' ...' if len(missing_groups) > 8 else ''}。"
            )

        if expected_factor_ids and missing_factor_ids:
            flags.append("macro_factor_coverage_incomplete")
            notes.append(
                "当前 macro bundle 缺少部分设计内因子: "
                f"{', '.join(missing_factor_ids[:8])}"
                f"{' ...' if len(missing_factor_ids) > 8 else ''}。"
            )

        if not rows:
            flags.append("macro_context_empty")
            if raw_row_count > 0 and ai_excluded_source_count > 0:
                notes.append(
                    "当前 macro 虽然已有真实已落库快照，但它们全部来自尚未达到 AI-ready 门槛的 source，"
                    "当前没有任何可直接给 AI 使用的宏观锚点。"
                )
            else:
                notes.append("当前 macro bundle 没有任何最新快照，AI 不能把宏观背景视为已覆盖。")
            return flags, notes

        if quality_summary["partial_count"]:
            flags.append("macro_partial_present")
            notes.append("latest macro 快照里存在 partial 样本，说明部分宏观观测仍未完整确认。")
        if quality_summary["fallback_count"]:
            flags.append("macro_fallback_present")
            notes.append("latest macro 快照里存在 fallback 样本，说明部分宏观字段来自降级路径。")
        if quality_summary["stale_count"]:
            flags.append("macro_stale_present")
            notes.append("latest macro 快照里存在 stale 样本，不应把这些字段视为当前最新宏观状态。")
        if quality_summary["unknown_count"]:
            flags.append("macro_unknown_quality_flag_present")
            notes.append("latest macro 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")

        for group_name, mode, candidate_factor_ids, note, _required_for_breadth in cls.MACRO_EVIDENCE_GROUP_SPECS:
            relevant_factor_ids = [
                factor_id
                for factor_id in candidate_factor_ids
                if factor_id in expected_factor_id_set
            ]
            if not relevant_factor_ids:
                continue
            if mode == "all":
                is_missing = any(
                    factor_id not in observed_factor_ids
                    for factor_id in relevant_factor_ids
                )
            else:
                is_missing = not any(
                    factor_id in observed_factor_ids
                    for factor_id in relevant_factor_ids
                )
            if not is_missing:
                continue
            flags.append(f"missing_{group_name}")
            notes.append(note)
        return flags, notes

    def init_storage(self):
        self.db.init_market_data_tables()
        self.sync_factor_catalog()

    def sync_factor_catalog(self):
        factors = load_macro_factors(enabled_only=False)
        if not factors:
            return

        sql = """
            INSERT INTO macro_factor_catalog (
                factor_id, name, category, factor_type, description,
                default_interval, unit, currency, source_name, source_symbol,
                source_priority, market_region, market_session,
                staleness_ttl_seconds, is_intraday_enabled, enabled,
                raw_meta_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                factor_type=excluded.factor_type,
                description=excluded.description,
                default_interval=excluded.default_interval,
                unit=excluded.unit,
                currency=excluded.currency,
                source_name=excluded.source_name,
                source_symbol=excluded.source_symbol,
                source_priority=excluded.source_priority,
                market_region=excluded.market_region,
                market_session=excluded.market_session,
                staleness_ttl_seconds=excluded.staleness_ttl_seconds,
                is_intraday_enabled=excluded.is_intraday_enabled,
                enabled=excluded.enabled,
                raw_meta_json=excluded.raw_meta_json,
                updated_at=excluded.updated_at
        """
        self.db.execute_many(sql, [factor.to_catalog_tuple() for factor in factors])
        self.db.commit()

    def bootstrap(
        self,
        factor_ids: list[str] | None = None,
        market_history_days: int | None = None,
        daily_history_years: int | None = None,
        continue_on_error: bool = False,
    ) -> dict[str, int]:
        self.sync_factor_catalog()
        market_points = self.market_collector.bootstrap_history(
            factor_ids=factor_ids,
            market_history_days=market_history_days,
            daily_history_years=daily_history_years,
            continue_on_error=continue_on_error,
        )
        if market_points:
            self.market_collector.save_to_db(market_points)

        rate_points = self.rate_collector.bootstrap_history(
            factor_ids=factor_ids,
            daily_history_years=daily_history_years,
            continue_on_error=continue_on_error,
        )
        if rate_points:
            self.rate_collector.save_to_db(rate_points)
        return {
            "market_points": len(market_points),
            "rate_points": len(rate_points),
        }

    def collect_once(self, factor_ids: list[str] | None = None):
        self.sync_factor_catalog()
        market_points = self._run_collection_job(
            source_name="yahoo_finance",
            job_name="macro_market_timeseries",
            func=lambda: self.market_collector.collect(factor_ids=factor_ids),
            metadata={
                "factor_ids": factor_ids or [],
                "source_kind": "market_price",
            },
        ) or []
        rate_points = self._run_collection_job(
            source_name="fred",
            job_name="macro_level_timeseries",
            func=lambda: self.rate_collector.collect(
                factor_ids=factor_ids,
                continue_on_error=True,
            ),
            metadata={
                "factor_ids": factor_ids or [],
                "source_kind": "macro_level",
            },
        ) or []
        return {
            "market_points": len(market_points),
            "rate_points": len(rate_points),
        }

    def load_latest_context(
        self,
        factor_ids: list[str] | None = None,
        interval: str | None = None,
    ) -> list[dict]:
        sql = """
            SELECT factor_id, factor_type, interval, observation_time, value,
                   open, high, low, close, unit, currency, source_name,
                   source_symbol, source_priority, quality_flag, is_market_open,
                   collected_at, updated_at
            FROM latest_macro_timeseries
        """
        clauses: list[str] = []
        params: list[str] = []
        if factor_ids:
            placeholders = ",".join("?" for _ in factor_ids)
            clauses.append(f"factor_id IN ({placeholders})")
            params.extend(factor_ids)
        if interval:
            clauses.append("interval = ?")
            params.append(interval)
        if clauses:
            sql = f"{sql} WHERE {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY factor_id, interval"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]

    def load_latest_context_bundle(
        self,
        factor_ids: list[str] | None = None,
        interval: str | None = None,
    ) -> dict:
        normalized_factor_ids = self._normalize_factor_ids(factor_ids)
        rows = self.load_latest_context(factor_ids=factor_ids, interval=interval)
        meta_map = self._build_factor_meta()
        expected_factors = self._load_expected_factors(normalized_factor_ids)
        expected_factor_ids = [
            factor.factor_id
            for factor in expected_factors
        ]
        configured_universe_summary = self._build_configured_universe_summary(
            expected_factors=expected_factors,
            requested_factor_ids=normalized_factor_ids or None,
        )
        preferred_rows: dict[str, dict] = {}
        for row in rows:
            factor_id = str(row["factor_id"])
            previous = preferred_rows.get(factor_id)
            if previous is None or self._factor_rank(row) >= self._factor_rank(previous):
                preferred_rows[factor_id] = row
        raw_selected_rows = list(preferred_rows.values())
        raw_selected_rows.sort(key=lambda item: str(item["factor_id"]))
        coverage = self.load_source_coverage(
            factor_ids=normalized_factor_ids or None,
        )
        coverage_rows = coverage.get("sources", [])
        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=raw_selected_rows,
            coverage_rows=coverage_rows,
        )
        selected_rows = [
            row
            for row in raw_selected_rows
            if str(row["source_name"]) in ai_ready_source_names
        ]
        observed_factor_ids = {
            str(row["factor_id"])
            for row in selected_rows
        }
        raw_observed_factor_ids = {
            str(row["factor_id"])
            for row in raw_selected_rows
        }
        quality_summary = summarize_quality_flag_counts(selected_rows)
        raw_quality_summary = summarize_quality_flag_counts(raw_selected_rows)
        source_health = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
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
                "expected_factor_count": row["expected_factor_count"],
                "latest_factor_count": row["latest_factor_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "data_quality_flags": row["data_quality_flags"],
            }
            for row in coverage_rows
        ]
        data_quality_flags, quality_notes = self._build_context_quality(
            rows=selected_rows,
            raw_row_count=len(raw_selected_rows),
            ai_excluded_source_count=len(ai_excluded_sources),
            expected_factor_ids=expected_factor_ids,
            quality_summary=quality_summary,
            coverage_rows=coverage_rows,
            configured_universe_summary=configured_universe_summary,
        )
        latest_observation_time = max(
            (row.get("observation_time") for row in selected_rows if row.get("observation_time")),
            default=None,
        )
        raw_latest_observation_time = max(
            (
                row.get("observation_time")
                for row in raw_selected_rows
                if row.get("observation_time")
            ),
            default=None,
        )
        source_counts = self._count_rows_by_source(selected_rows)
        raw_source_counts = self._count_rows_by_source(raw_selected_rows)
        context_rows = [
            {
                **row,
                "name": meta_map.get(str(row["factor_id"]), {}).get("name"),
                "category": meta_map.get(str(row["factor_id"]), {}).get("category"),
                "market_region": meta_map.get(str(row["factor_id"]), {}).get("market_region"),
                "market_session": meta_map.get(str(row["factor_id"]), {}).get("market_session"),
            }
            for row in selected_rows
        ]
        expected_categories = sorted(
            {
                str(factor.category)
                for factor in expected_factors
                if str(factor.category).strip()
            }
        )
        observed_categories = sorted(
            {
                str(meta_map.get(factor_id, {}).get("category"))
                for factor_id in observed_factor_ids
                if meta_map.get(factor_id, {}).get("category")
            }
        )
        raw_observed_categories = sorted(
            {
                str(meta_map.get(factor_id, {}).get("category"))
                for factor_id in raw_observed_factor_ids
                if meta_map.get(factor_id, {}).get("category")
            }
        )
        missing_factor_ids = [
            factor_id
            for factor_id in expected_factor_ids
            if factor_id not in observed_factor_ids
        ]
        missing_categories = [
            category
            for category in expected_categories
            if category not in observed_categories
        ]
        filtered_preferred_rows = {
            str(row["factor_id"]): row
            for row in selected_rows
        }
        return {
            "as_of": latest_observation_time,
            "raw_as_of": raw_latest_observation_time,
            "row_count": len(selected_rows),
            "raw_row_count": len(raw_selected_rows),
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
                "expected_factor_count": len(expected_factor_ids),
                "observed_factor_count": len(observed_factor_ids),
                "raw_observed_factor_count": len(raw_observed_factor_ids),
                "expected_point_count": len(expected_factor_ids) if expected_factor_ids else None,
                "observed_point_count": len(selected_rows),
                "raw_observed_point_count": len(raw_selected_rows),
                "expected_category_count": len(expected_categories),
                "observed_category_count": len(observed_categories),
                "raw_observed_category_count": len(raw_observed_categories),
                "missing_factor_ids": missing_factor_ids,
                "missing_categories": missing_categories,
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
            "source_health": source_health,
            "leaders": {
                "highest_dxy": filtered_preferred_rows.get("dxy"),
                "highest_vix": filtered_preferred_rows.get("vix"),
                "highest_ust_3m_yield": filtered_preferred_rows.get("ust_3m_yield"),
                "highest_ust_2y_yield": filtered_preferred_rows.get("ust_2y_yield"),
                "highest_ust_10y_yield": filtered_preferred_rows.get("ust_10y_yield"),
                "highest_ust_30y_yield": filtered_preferred_rows.get("ust_30y_yield"),
                "highest_ust_10y_real_yield": filtered_preferred_rows.get("ust_10y_real_yield"),
                "highest_us_10y_breakeven_inflation": filtered_preferred_rows.get(
                    "us_10y_breakeven_inflation"
                ),
                "highest_us_bbb_oas": filtered_preferred_rows.get("us_bbb_oas"),
                "highest_us_high_yield_oas": filtered_preferred_rows.get("us_high_yield_oas"),
                "highest_fed_funds_upper": filtered_preferred_rows.get("fed_funds_upper"),
            },
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
            "factors": context_rows,
        }

    def load_source_coverage(
        self,
        factor_ids: list[str] | None = None,
    ) -> dict:
        normalized_factor_id_list = self._normalize_factor_ids(factor_ids)
        normalized_factor_ids = set(normalized_factor_id_list)
        factors = self._load_expected_factors(normalized_factor_id_list)
        if normalized_factor_ids:
            source_names = []
            seen_sources: set[str] = set()
            for factor in factors:
                if factor.source_name in seen_sources:
                    continue
                seen_sources.add(factor.source_name)
                source_names.append(factor.source_name)
        else:
            source_names = ["yahoo_finance", "fred"]
        source_factor_counts: dict[str, int] = {}
        for factor in factors:
            source_factor_counts[factor.source_name] = source_factor_counts.get(factor.source_name, 0) + 1

        latest_where_clauses: list[str] = []
        latest_params: list[str] = []
        if normalized_factor_id_list:
            placeholders = ",".join("?" for _ in normalized_factor_id_list)
            latest_where_clauses.append(f"factor_id IN ({placeholders})")
            latest_params.extend(normalized_factor_id_list)
        latest_where_sql = ""
        if latest_where_clauses:
            latest_where_sql = f" WHERE {' AND '.join(latest_where_clauses)}"

        latest_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                COUNT(*) AS latest_point_count,
                COUNT(DISTINCT factor_id) AS latest_factor_count,
                MAX(observation_time) AS latest_observation_time
            FROM latest_macro_timeseries
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
            FROM latest_macro_timeseries
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
            """
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'macro_data'
                GROUP BY source_name
            ) AS latest
                ON runs.id = latest.latest_id
            """
        )
        run_map = {str(row["source_name"]): dict(row) for row in run_rows}

        rows: list[dict] = []
        now = self._utc_now_naive()
        source_titles = {
            "yahoo_finance": "Macro Market Price Source",
            "fred": "Macro Rates, Inflation and Credit Source",
        }
        semantic_scopes = {
            "yahoo_finance": "risk_assets_and_safe_havens",
            "fred": "policy_rates_curve_inflation_credit",
        }
        for source_name in source_names:
            latest_meta = latest_map.get(source_name, {})
            run_meta = run_map.get(source_name, {})
            expected_factor_count = source_factor_counts.get(source_name, 0)
            latest_point_count = int(latest_meta.get("latest_point_count") or 0)
            latest_factor_count = int(latest_meta.get("latest_factor_count") or 0)
            quality_summary = summarize_quality_flag_counts(
                quality_counts_map.get(source_name, {})
            )
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = (
                datetime.fromisoformat(last_run_finished_at)
                if last_run_finished_at
                else None
            )
            is_stale = (
                last_run_dt is None
                or (now - last_run_dt).total_seconds() > self._source_interval_seconds(source_name) * 3
            )
            health_status = resolve_source_health_status(
                enabled=expected_factor_count > 0,
                configuration_ready=True,
                last_run_status=run_meta.get("status"),
                latest_point_count=latest_point_count,
                is_stale=is_stale,
            )
            is_ready_for_ai = (
                health_status == "ready"
                and (
                    not expected_factor_count
                    or latest_factor_count >= expected_factor_count
                )
                and is_quality_summary_ai_ready(quality_summary)
            )
            data_quality_flags: list[str] = []
            quality_notes: list[str] = []
            if latest_factor_count and expected_factor_count and latest_factor_count < expected_factor_count:
                data_quality_flags.append("factor_coverage_incomplete")
                quality_notes.append("当前已落库 factor 数少于设计目标，AI 看到的宏观背景仍不完整。")
            if source_name == "yahoo_finance":
                quality_notes.append("风险资产、避险资产和波动率代理应尽量同时完整，避免 AI 只看到单边宏观锚点。")
            if source_name == "fred":
                quality_notes.append("政策利率、收益率曲线、真实利率、通胀预期和信用利差是识别宏观 regime 的关键证据，建议不要长期缺失。")
            if health_status == "ready" and not is_ready_for_ai:
                quality_notes.append(
                    "当前 source 虽然最近运行成功，但 latest 快照缺少可直接使用的 ok 宏观样本，AI 不应把它视为完整宏观锚点。"
                )
            if quality_summary["partial_count"]:
                data_quality_flags.append("partial_points_present")
                quality_notes.append("latest 快照里包含 partial 宏观样本，部分时间点可能仍在等待最终确认。")
            if quality_summary["fallback_count"]:
                data_quality_flags.append("fallback_points_present")
                quality_notes.append("latest 快照里包含 fallback 宏观样本，说明部分因子来自降级路径。")
            if quality_summary["stale_count"]:
                data_quality_flags.append("stale_points_present")
                quality_notes.append("latest 快照里包含 stale 宏观样本，即使最近任务成功，AI 也不应把这些因子视为同等可靠。")
            if quality_summary["unknown_count"]:
                data_quality_flags.append("unknown_quality_flag_present")
                quality_notes.append("latest 快照里存在未知 quality_flag，说明质量标记语义还未完全标准化。")
            rows.append(
                {
                    "source_name": source_name,
                    "name": source_titles[source_name],
                    "semantic_scope": semantic_scopes[source_name],
                    "enabled": expected_factor_count > 0,
                    "configuration_ready": True,
                    "expected_factor_count": expected_factor_count,
                    "latest_factor_count": latest_factor_count,
                    "latest_point_count": latest_point_count,
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
        health_summary = summarize_health_rows(rows)
        ready_for_ai_source_count = sum(1 for item in rows if item["is_ready_for_ai"])
        return {
            "generated_at": now.isoformat(),
            "source_count": len(rows),
            "stale_source_count": sum(1 for item in rows if item["is_stale"]),
            "total_latest_point_count": sum(item["latest_point_count"] for item in rows),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
            **health_summary,
            "sources": rows,
        }

    def _run_market_job(self, factor_ids: list[str] | None = None):
        local_db = DBManager(self.db.db_path)
        local_collector = MacroMarketCollector(self.client, local_db)
        try:
            return self._run_collection_job(
                source_name="yahoo_finance",
                job_name="macro_market_timeseries",
                func=lambda: local_collector.collect(factor_ids=factor_ids),
                metadata={
                    "factor_ids": factor_ids or [],
                    "source_kind": "market_price",
                    "mode": "scheduler",
                },
                db=local_db,
            )
        finally:
            local_db.close()

    def _run_rate_job(self, factor_ids: list[str] | None = None):
        local_db = DBManager(self.db.db_path)
        local_collector = MacroRateCollector(self.client, local_db)
        try:
            return self._run_collection_job(
                source_name="fred",
                job_name="macro_level_timeseries",
                func=lambda: local_collector.collect(
                    factor_ids=factor_ids,
                    continue_on_error=True,
                ),
                metadata={
                    "factor_ids": factor_ids or [],
                    "source_kind": "macro_level",
                    "mode": "scheduler",
                },
                db=local_db,
            )
        finally:
            local_db.close()

    def build_scheduler(
        self,
        factor_ids: list[str] | None = None,
    ) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self._run_market_job,
            "interval",
            seconds=MACRO_CONFIG["market_interval_seconds"],
            id="macro_market",
            name="宏观市场行情采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, MACRO_CONFIG["market_interval_seconds"]),
            kwargs={"factor_ids": factor_ids},
        )
        scheduler.add_job(
            self._run_rate_job,
            "interval",
            seconds=MACRO_CONFIG["level_interval_seconds"],
            id="macro_rates",
            name="宏观利率因子采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(300, MACRO_CONFIG["level_interval_seconds"]),
            kwargs={"factor_ids": factor_ids},
        )
        return scheduler

    def close(self):
        self.db.close()
