import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from config.settings import EVENT_CALENDAR_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import resolve_source_health_status, summarize_health_rows
from data_layer.event_calendar_data.client import EventCalendarClient
from data_layer.event_calendar_data.collector import EventCalendarCollector
from data_layer.event_calendar_data.sources import load_event_calendar_sources


class EventCalendarDataService:
    """事件日历模块统一编排入口。"""

    EVENT_HORIZON_TARGETS = {
        "macro": 14,
        "etf": 14,
        "unlock": 14,
        "upgrade": 14,
    }
    AI_READY_MIN_UPCOMING_EVENT_COUNT = 2
    HIGH_IMPORTANCE_THRESHOLD = 0.8
    MINIMUM_EVENT_TYPE_COUNT_FOR_MARKET_BREADTH = 4
    MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH = 4
    EVENT_MARKET_BREADTH_GROUP_SPECS = {
        "macro_liquidity": {"macro"},
        "regulatory_etf": {"etf"},
        "token_supply": {"unlock"},
        "protocol_upgrade": {"upgrade"},
    }
    AI_EXCLUDED_SOURCE_REASON = "source_not_ai_ready"

    def __init__(
        self,
        client: EventCalendarClient | None = None,
        db: DBManager | None = None,
        collector: EventCalendarCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or EventCalendarClient()
        self.collector = collector or EventCalendarCollector(self.client, self.db)

    def init_storage(self):
        self.db.init_market_data_tables()

    def collect_once(
        self,
        lookahead_days: int | None = None,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> dict[str, int]:
        sources = load_event_calendar_sources(
            source_names=source_names,
            event_types=event_types,
        )
        normalized_symbols = {
            value.strip().upper()
            for value in (symbols or [])
            if value.strip()
        }

        total_events = 0
        for source in sources:
            total_events += len(
                self._collect_source_once(
                    source=source,
                    lookahead_days=lookahead_days,
                    normalized_symbols=normalized_symbols,
                )
            )
        return {"event_count": total_events}

    def _collect_source_once(
        self,
        *,
        source,
        lookahead_days: int | None = None,
        normalized_symbols: set[str] | None = None,
    ) -> list:
        started_at = self._utc_now_naive()
        status = "success"
        message = None
        events = []
        try:
            if not source.endpoint:
                status = "unconfigured"
                message = f"事件源 {source.name} 未配置 endpoint"
            else:
                events = self.collector.collect_source(
                    source=source,
                    lookahead_days=lookahead_days,
                    normalized_symbols=normalized_symbols,
                )
                if events:
                    self.collector.save_to_db(events)
                if not events:
                    status = "empty"
        except Exception as exc:
            status = "error"
            message = f"{type(exc).__name__}: {exc}"
            logger.error(f"事件源采集失败 [{source.name}]: {message}")
        finally:
            finished_at = self._utc_now_naive()
            self.db.record_collection_run(
                module_name="event_calendar_data",
                source_name=source.name,
                job_name="event_calendar_events",
                status=status,
                item_count=len(events),
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
                duration_seconds=(finished_at - started_at).total_seconds(),
                message=message,
                metadata_json=json.dumps(
                    {
                        "event_type": source.event_type,
                        "lookahead_days": lookahead_days,
                        "symbols": sorted(normalized_symbols or set()),
                        "source_url": source.endpoint,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        return events

    def describe_sources(
        self,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
    ) -> list[dict]:
        return [
            {
                "name": source.name,
                "event_type": source.event_type,
                "adapter": source.adapter,
                "endpoint": source.endpoint,
                "enabled": source.enabled,
                "default_symbol": source.default_symbol,
                "timezone": source.timezone,
                "tags": source.tags,
                "description": source.description,
            }
            for source in load_event_calendar_sources(
                source_names=source_names,
                event_types=event_types,
                enabled_only=False,
            )
        ]

    @staticmethod
    def _append_unique(values: list[str], value: str | None):
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def _is_source_ready_for_ai(
        self,
        *,
        health_status: str,
        upcoming_events: int,
        upcoming_high_importance_events: int,
        farthest_event_horizon_days: float | None,
        minimum_horizon_days: int,
    ) -> bool:
        if health_status != "ready":
            return False
        if int(upcoming_events or 0) <= 0:
            return False
        if farthest_event_horizon_days is None:
            return False
        if float(farthest_event_horizon_days) < float(minimum_horizon_days):
            return False
        if (
            int(upcoming_events or 0) < self.AI_READY_MIN_UPCOMING_EVENT_COUNT
            and int(upcoming_high_importance_events or 0) <= 0
        ):
            return False
        return True

    def _minimum_horizon_days(self, event_type: str) -> int:
        return int(self.EVENT_HORIZON_TARGETS.get(str(event_type or "").strip().lower(), 14))

    def _farthest_event_horizon_days(self, now: datetime, value: str | None) -> float | None:
        scheduled_at = self._parse_timestamp(value)
        if scheduled_at is None:
            return None
        return round(max((scheduled_at - now).total_seconds(), 0.0) / 86400, 4)

    def _build_quality_flags_and_notes(
        self,
        *,
        source,
        horizon_days: int,
        configuration_ready: bool,
        total_events: int,
        upcoming_events: int,
        upcoming_high_importance_events: int,
        is_stale: bool,
        farthest_event_horizon_days: float | None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []
        minimum_horizon_days = self._minimum_horizon_days(source.event_type)

        if not configuration_ready:
            self._append_unique(flags, "unconfigured_source")
            self._append_unique(notes, "当前事件源没有配置真实 endpoint，无法提供可验证的未来事件数据。")
        if total_events <= 0:
            self._append_unique(flags, "no_historical_events")
            self._append_unique(notes, "该事件源还没有任何历史事件入库，AI 无法从这里获得事件先验。")
        if is_stale:
            self._append_unique(flags, "stale_source")
            self._append_unique(notes, "最近一次事件采集已超过调度容忍窗口，这路前瞻事件数据不应视为当前有效。")
        if configuration_ready and upcoming_events <= 0:
            self._append_unique(flags, "no_upcoming_events")
            self._append_unique(
                notes,
                f"未来 {horizon_days} 天内没有可用事件，AI 当前无法从这个来源获得前瞻催化剂信息。",
            )
        if (
            configuration_ready
            and upcoming_events > 0
            and upcoming_events < self.AI_READY_MIN_UPCOMING_EVENT_COUNT
            and upcoming_high_importance_events <= 0
        ):
            self._append_unique(flags, "single_low_signal_upcoming_event")
            self._append_unique(
                notes,
                "当前未来窗口里只有单条低重要度事件，事件深度不足以支撑 AI 把这一路当成稳定催化剂日历。",
            )
        if upcoming_events > 0 and farthest_event_horizon_days is not None:
            if farthest_event_horizon_days < minimum_horizon_days:
                self._append_unique(flags, "thin_upcoming_horizon")
                self._append_unique(
                    notes,
                    f"当前未来事件只延伸到 {farthest_event_horizon_days} 天，低于该类事件建议的 {minimum_horizon_days} 天前瞻视野。",
                )

        if source.event_type == "macro":
            self._append_unique(notes, "宏观事件时间点是 AI 判断风险窗口和跨市场联动的重要前置证据。")
        elif source.event_type == "etf":
            self._append_unique(notes, "ETF 审批和延期节点会显著影响加密市场叙事节奏，建议保持前瞻覆盖。")
        elif source.event_type == "unlock":
            self._append_unique(notes, "解锁事件直接影响潜在卖压评估，缺失会削弱 AI 对供给冲击的判断。")
        elif source.event_type == "upgrade":
            self._append_unique(notes, "升级和治理执行节点会影响预期差与波动窗口，建议持续保持覆盖。")
        return flags, notes

    def load_upcoming_events(
        self,
        horizon_days: int | None = None,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
        statuses: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        sql = """
            SELECT event_key, event_type, title, description, symbol,
                   scheduled_at, timezone, importance_score, source_name, status,
                   source_url, external_id, tags, collected_at, raw_payload_json,
                   created_at, updated_at
            FROM event_calendar_events
            WHERE 1 = 1
        """
        params: list[object] = []
        now = self._utc_now_naive()
        sql += " AND scheduled_at >= ?"
        params.append(now.isoformat())
        if horizon_days is not None:
            horizon_at = now + timedelta(days=int(horizon_days))
            sql += " AND scheduled_at <= ?"
            params.append(horizon_at.isoformat())
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            sql += f" AND event_type IN ({placeholders})"
            params.extend([value.strip().lower() for value in event_types if value.strip()])
        if symbols:
            placeholders = ",".join("?" for _ in symbols)
            sql += f" AND symbol IN ({placeholders})"
            params.extend([value.strip().upper() for value in symbols if value.strip()])
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend([value.strip().lower() for value in statuses if value.strip()])
        sql += " ORDER BY scheduled_at ASC, importance_score DESC, source_name ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]

    @staticmethod
    def _loads_json(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _loads_string_list(cls, value: str | None) -> list[str]:
        payload = cls._loads_json(value)
        if not isinstance(payload, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in payload:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    @staticmethod
    def _top_titles(rows: list[dict], limit: int = 3) -> list[str]:
        seen: set[str] = set()
        titles: list[str] = []
        for row in rows:
            title = str(row.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) >= limit:
                break
        return titles

    @staticmethod
    def _count_rows_by_source(rows: list[dict]) -> dict[str, int]:
        counter: Counter = Counter()
        for row in rows:
            counter[str(row["source_name"])] += 1
        return dict(
            sorted(
                counter.items(),
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
        now: datetime,
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
            next_event_at = min(
                (
                    row["scheduled_at"]
                    for row in source_rows
                    if row.get("scheduled_at")
                ),
                default=None,
            )
            excluded.append(
                {
                    "source_name": source_name,
                    "event_type": coverage_row["event_type"],
                    "excluded_reason": cls.AI_EXCLUDED_SOURCE_REASON,
                    "raw_event_count": len(source_rows),
                    "raw_high_importance_event_count": sum(
                        1
                        for row in source_rows
                        if float(row.get("importance_score") or 0.0) >= cls.HIGH_IMPORTANCE_THRESHOLD
                    ),
                    "raw_next_event_at": next_event_at,
                    "raw_farthest_event_horizon_days": max(
                        (
                            round(
                                max((row["scheduled_at_dt"] - now).total_seconds(), 0.0) / 86400,
                                4,
                            )
                            for row in source_rows
                            if row.get("scheduled_at_dt") is not None
                        ),
                        default=None,
                    ),
                    "health_status": coverage_row["health_status"],
                    "is_ready_for_ai": coverage_row["is_ready_for_ai"],
                    "configuration_ready": coverage_row["configuration_ready"],
                    "is_stale": coverage_row["is_stale"],
                    "upcoming_events": coverage_row["upcoming_events"],
                    "upcoming_high_importance_events": coverage_row["upcoming_high_importance_events"],
                    "minimum_horizon_days": coverage_row["minimum_horizon_days"],
                    "farthest_event_horizon_days": coverage_row["farthest_event_horizon_days"],
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        configured_sources: list,
        requested_event_types: list[str] | None = None,
        requested_symbols: list[str] | None = None,
    ) -> dict[str, object]:
        configured_source_names = sorted(
            {
                str(source.name)
                for source in configured_sources
                if str(source.name).strip()
            }
        )
        configured_event_types = sorted(
            {
                str(source.event_type).strip().lower()
                for source in configured_sources
                if str(source.event_type).strip()
            }
        )
        configured_default_symbols = sorted(
            {
                str(source.default_symbol).strip().upper()
                for source in configured_sources
                if str(source.default_symbol).strip()
            }
        )
        event_type_source_counts: dict[str, int] = {}
        for source in configured_sources:
            event_type = str(source.event_type or "").strip().lower()
            if not event_type:
                continue
            event_type_source_counts[event_type] = event_type_source_counts.get(event_type, 0) + 1
        configured_event_type_set = set(configured_event_types)
        required_semantic_groups = list(cls.EVENT_MARKET_BREADTH_GROUP_SPECS)
        covered_semantic_groups = [
            group_name
            for group_name, candidate_event_types in cls.EVENT_MARKET_BREADTH_GROUP_SPECS.items()
            if configured_event_type_set & set(candidate_event_types)
        ]
        missing_semantic_groups = [
            group_name
            for group_name in required_semantic_groups
            if group_name not in covered_semantic_groups
        ]
        scope_kind = (
            "filtered"
            if requested_event_types or requested_symbols
            else "default"
        )
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = (
                "sufficient"
                if (
                    len(configured_source_names) >= cls.MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH
                    and len(configured_event_types) >= cls.MINIMUM_EVENT_TYPE_COUNT_FOR_MARKET_BREADTH
                    and not missing_semantic_groups
                )
                else "limited"
            )
        return {
            "scope_kind": scope_kind,
            "configured_source_names": configured_source_names,
            "configured_event_types": configured_event_types,
            "configured_default_symbols": configured_default_symbols,
            "source_count": len(configured_source_names),
            "event_type_count": len(configured_event_types),
            "default_symbol_count": len(configured_default_symbols),
            "event_type_source_counts": event_type_source_counts,
            "minimum_source_count_for_market_breadth": cls.MINIMUM_SOURCE_COUNT_FOR_MARKET_BREADTH,
            "minimum_event_type_count_for_market_breadth": (
                cls.MINIMUM_EVENT_TYPE_COUNT_FOR_MARKET_BREADTH
            ),
            "required_semantic_groups_for_market_breadth": required_semantic_groups,
            "covered_semantic_groups": covered_semantic_groups,
            "missing_semantic_groups": missing_semantic_groups,
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    def _format_upcoming_event(self, row: dict, now: datetime) -> dict:
        scheduled_at_dt = row.get("scheduled_at_dt")
        hours_until_event = None
        days_until_event = None
        if scheduled_at_dt is not None:
            delta_seconds = max((scheduled_at_dt - now).total_seconds(), 0.0)
            hours_until_event = round(delta_seconds / 3600, 4)
            days_until_event = round(delta_seconds / 86400, 4)
        return {
            "event_key": row["event_key"],
            "event_type": row["event_type"],
            "title": row["title"],
            "description": row.get("description"),
            "symbol": row["symbol"],
            "scheduled_at": row["scheduled_at"],
            "timezone": row.get("timezone"),
            "importance_score": row.get("importance_score"),
            "source_name": row["source_name"],
            "status": row["status"],
            "source_url": row.get("source_url"),
            "external_id": row.get("external_id"),
            "tags": row.get("tags_list") or [],
            "collected_at": row.get("collected_at"),
            "hours_until_event": hours_until_event,
            "days_until_event": days_until_event,
        }

    def _build_upcoming_context_quality(
        self,
        *,
        horizon_days: int,
        coverage_rows: list[dict],
        event_count: int,
        raw_event_count: int,
        configured_event_types: set[str],
        observed_event_types: set[str],
        next_24h_count: int,
        next_7d_count: int,
        high_importance_count: int,
        asset_specific_symbol_count: int,
        farthest_horizon_days: float | None,
        configured_universe_summary: dict[str, object] | None = None,
        symbol_filter_active: bool = False,
        ai_excluded_source_count: int = 0,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []

        non_ready_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("health_status") != "ready"
        ]
        unconfigured_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("configuration_ready")
        ]
        stale_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("is_stale")
        ]

        if non_ready_sources:
            self._append_unique(flags, "event_calendar_source_not_ready_present")
            self._append_unique(
                notes,
                "当前仍有未 ready 的事件源: "
                f"{', '.join(non_ready_sources[:6])}"
                f"{' ...' if len(non_ready_sources) > 6 else ''}。",
            )
        if unconfigured_sources:
            self._append_unique(flags, "event_calendar_unconfigured_source_present")
            self._append_unique(
                notes,
                "部分事件类型尚未配置真实上游 endpoint，AI 的未来催化剂视野仍然有结构性缺口。"
            )
        if stale_sources:
            self._append_unique(flags, "event_calendar_stale_source_present")
            self._append_unique(
                notes,
                "部分事件源已经 stale，未来事件时间表不应被视为完全最新。"
            )
        if (
            configured_universe_summary
            and configured_universe_summary.get("scope_kind") == "default"
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            self._append_unique(flags, "event_calendar_configured_market_breadth_limited")
            missing_groups = configured_universe_summary.get("missing_semantic_groups") or []
            self._append_unique(
                notes,
                "当前 event calendar 默认配置宇宙只覆盖 "
                f"{int(configured_universe_summary.get('event_type_count') or 0)} 类事件/"
                f"{int(configured_universe_summary.get('source_count') or 0)} 路来源，"
                "更适合作为局部催化剂视角；"
                "缺少的关键前瞻维度有: "
                f"{', '.join(missing_groups[:8])}"
                f"{' ...' if len(missing_groups) > 8 else ''}。",
            )

        if event_count <= 0:
            self._append_unique(flags, "event_calendar_context_empty")
            if raw_event_count > 0 and ai_excluded_source_count > 0:
                self._append_unique(
                    notes,
                    f"未来 {horizon_days} 天虽然还有真实已落库事件，但它们全部来自尚未达到 AI-ready 门槛的事件源，当前没有任何可直接给 AI 使用的前瞻催化剂输入。"
                )
            else:
                self._append_unique(
                    notes,
                    f"未来 {horizon_days} 天没有任何已落库事件，AI 当前缺少前瞻催化剂输入。"
                )
            return flags, notes

        if not symbol_filter_active:
            missing_event_types = sorted(configured_event_types - observed_event_types)
            if missing_event_types:
                self._append_unique(flags, "event_calendar_event_types_incomplete")
                self._append_unique(
                    notes,
                    "当前 future bundle 缺少部分已配置事件类型: "
                    f"{', '.join(missing_event_types)}。"
                )
                for event_type in missing_event_types:
                    self._append_unique(flags, f"event_calendar_missing_{event_type}_coverage")

            if len(observed_event_types) <= 1 and len(configured_event_types) > 1:
                self._append_unique(flags, "event_calendar_single_event_type_only")
                self._append_unique(
                    notes,
                    "当前未来事件几乎只剩单一事件类型，AI 很难平衡宏观、监管、升级和供给催化剂。"
                )

        if next_24h_count <= 0:
            self._append_unique(flags, "event_calendar_no_next_24h_events")
            self._append_unique(
                notes,
                "未来 24 小时没有任何事件，短线催化剂时间表偏空。"
            )

        next_7d_threshold = max(2, len(configured_event_types))
        if next_7d_count < next_7d_threshold:
            self._append_unique(flags, "event_calendar_next_7d_sparse")
            self._append_unique(
                notes,
                f"未来 7 天只有 {next_7d_count} 条事件，低于当前建议阈值 {next_7d_threshold} 条。"
            )

        if farthest_horizon_days is not None and farthest_horizon_days < min(14, horizon_days):
            self._append_unique(flags, "event_calendar_future_horizon_thin")
            self._append_unique(
                notes,
                f"当前事件视野最远只覆盖到 {farthest_horizon_days} 天后，前瞻窗口仍偏短。"
            )

        if high_importance_count <= 0:
            self._append_unique(flags, "event_calendar_high_importance_events_missing")
            self._append_unique(
                notes,
                "当前 future bundle 没有高重要度事件，AI 很难识别强催化剂窗口。"
            )

        if not symbol_filter_active and asset_specific_symbol_count <= 0:
            self._append_unique(flags, "event_calendar_asset_specific_events_missing")
            self._append_unique(
                notes,
                "当前未来事件全部是 MARKET 级别，没有明确落到具体资产的催化剂。"
            )
        return flags, notes

    def load_source_coverage(
        self,
        horizon_days: int = 90,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
    ) -> dict:
        sources = load_event_calendar_sources(
            source_names=source_names,
            event_types=event_types,
            enabled_only=False,
        )
        now_dt = self._utc_now_naive()
        if not sources:
            return {
                "generated_at": now_dt.isoformat(),
                "source_count": 0,
                "sources": [],
            }

        source_name_list = [source.name for source in sources]
        placeholders = ",".join("?" for _ in source_name_list)
        now = now_dt.isoformat()
        horizon_at = (now_dt + timedelta(days=horizon_days)).isoformat()

        event_rows = self.db.fetch_all(
            f"""
            SELECT
                source_name,
                COUNT(*) AS total_events,
                SUM(
                    CASE
                        WHEN scheduled_at >= ? AND scheduled_at <= ? AND status IN ('scheduled', 'updated')
                        THEN 1 ELSE 0
                    END
                ) AS upcoming_events,
                SUM(
                    CASE
                        WHEN scheduled_at >= ? AND scheduled_at <= ? AND status IN ('scheduled', 'updated')
                             AND COALESCE(importance_score, 0) >= ?
                        THEN 1 ELSE 0
                    END
                ) AS upcoming_high_importance_events,
                MAX(collected_at) AS last_collected_at,
                MAX(scheduled_at) AS farthest_scheduled_at
            FROM event_calendar_events
            WHERE source_name IN ({placeholders})
            GROUP BY source_name
            """,
            (
                now,
                horizon_at,
                now,
                horizon_at,
                float(self.HIGH_IMPORTANCE_THRESHOLD),
                *source_name_list,
            ),
        )
        event_map = {
            str(row["source_name"]): dict(row)
            for row in event_rows
        }

        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'event_calendar_data'
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

        rows: list[dict] = []
        for source in sources:
            event_meta = event_map.get(source.name, {})
            run_meta = run_map.get(source.name, {})
            last_run_dt = self._parse_timestamp(run_meta.get("finished_at"))
            is_stale = last_run_dt is None or (
                now_dt - last_run_dt
            ).total_seconds() > EVENT_CALENDAR_CONFIG["interval_seconds"] * 3
            configuration_ready = bool(str(source.endpoint or "").strip())
            total_events = int(event_meta.get("total_events") or 0)
            upcoming_events = int(event_meta.get("upcoming_events") or 0)
            upcoming_high_importance_events = int(
                event_meta.get("upcoming_high_importance_events") or 0
            )
            health_status = resolve_source_health_status(
                enabled=bool(source.enabled),
                configuration_ready=configuration_ready,
                last_run_status=run_meta.get("status"),
                latest_point_count=upcoming_events,
                is_stale=is_stale,
            )
            farthest_event_horizon_days = self._farthest_event_horizon_days(
                now_dt,
                event_meta.get("farthest_scheduled_at"),
            )
            minimum_horizon_days = self._minimum_horizon_days(source.event_type)
            data_quality_flags, quality_notes = self._build_quality_flags_and_notes(
                source=source,
                horizon_days=horizon_days,
                configuration_ready=configuration_ready,
                total_events=total_events,
                upcoming_events=upcoming_events,
                upcoming_high_importance_events=upcoming_high_importance_events,
                is_stale=is_stale,
                farthest_event_horizon_days=farthest_event_horizon_days,
            )
            is_ready_for_ai = self._is_source_ready_for_ai(
                health_status=health_status,
                upcoming_events=upcoming_events,
                upcoming_high_importance_events=upcoming_high_importance_events,
                farthest_event_horizon_days=farthest_event_horizon_days,
                minimum_horizon_days=minimum_horizon_days,
            )
            if health_status == "ready" and not is_ready_for_ai:
                self._append_unique(
                    quality_notes,
                    "最近一次事件采集虽然成功，但未来事件视野仍未达到可直接供 AI 做交易前瞻判断的质量门槛。",
                )
            rows.append(
                {
                    "source_name": source.name,
                    "name": source.name,
                    "event_type": source.event_type,
                    "adapter": source.adapter,
                    "endpoint": source.endpoint,
                    "enabled": source.enabled,
                    "configuration_ready": configuration_ready,
                    "coverage_expectation": "forward_event_calendar",
                    "minimum_horizon_days": minimum_horizon_days,
                    "default_symbol": source.default_symbol,
                    "timezone": source.timezone,
                    "tags": source.tags,
                    "description": source.description,
                    "total_events": total_events,
                    "upcoming_events": upcoming_events,
                    "upcoming_high_importance_events": upcoming_high_importance_events,
                    "upcoming_event_density": round(upcoming_events / max(horizon_days, 1), 4),
                    "last_collected_at": event_meta.get("last_collected_at"),
                    "farthest_scheduled_at": event_meta.get("farthest_scheduled_at"),
                    "farthest_event_horizon_days": farthest_event_horizon_days,
                    "last_run_status": run_meta.get("status"),
                    "last_run_item_count": int(run_meta.get("item_count") or 0),
                    "last_run_finished_at": run_meta.get("finished_at"),
                    "last_run_message": run_meta.get("message"),
                    "last_run_metadata": self._loads_json(run_meta.get("metadata_json")),
                    "is_stale": is_stale,
                    "health_status": health_status,
                    "is_ready_for_ai": is_ready_for_ai,
                    "data_quality_flags": data_quality_flags,
                    "quality_notes": quality_notes,
                }
            )

        rows.sort(
            key=lambda item: (
                item["health_status"] != "ready",
                not item["is_ready_for_ai"],
                item["is_stale"],
                -(item["upcoming_events"] or 0),
                item["source_name"],
            )
        )
        health_summary = summarize_health_rows(rows)
        ready_for_ai_source_count = sum(1 for item in rows if item["is_ready_for_ai"])
        return {
            "generated_at": now_dt.isoformat(),
            "source_count": len(rows),
            "total_event_count": sum(item["total_events"] for item in rows),
            "upcoming_event_count": sum(item["upcoming_events"] for item in rows),
            "stale_source_count": sum(1 for item in rows if item["is_stale"]),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
            **health_summary,
            "sources": rows,
        }

    def load_upcoming_context_bundle(
        self,
        horizon_days: int = 30,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
        statuses: list[str] | None = None,
        limit: int = 20,
    ) -> dict:
        now = self._utc_now_naive()
        query_horizon_days = max(int(horizon_days or 30), 30)
        effective_statuses = statuses or ["scheduled", "updated"]
        configured_sources = load_event_calendar_sources(
            event_types=event_types,
            enabled_only=False,
        )
        configured_universe_summary = self._build_configured_universe_summary(
            configured_sources=configured_sources,
            requested_event_types=event_types,
            requested_symbols=symbols,
        )
        coverage = self.load_source_coverage(
            horizon_days=query_horizon_days,
            event_types=event_types,
        )
        coverage_rows = coverage.get("sources", [])

        parsed_rows: list[dict] = []
        for row in self.load_upcoming_events(
            horizon_days=query_horizon_days,
            event_types=event_types,
            symbols=symbols,
            statuses=effective_statuses,
            limit=None,
        ):
            row_dict = dict(row)
            scheduled_at_dt = self._parse_timestamp(row_dict.get("scheduled_at"))
            parsed_rows.append(
                {
                    **row_dict,
                    "scheduled_at_dt": scheduled_at_dt,
                    "tags_list": self._loads_string_list(row_dict.get("tags")),
                    "raw_payload": self._loads_json(row_dict.get("raw_payload_json")),
                }
            )

        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=parsed_rows,
            coverage_rows=coverage_rows,
            now=now,
        )
        raw_parsed_rows = list(parsed_rows)
        parsed_rows = [
            row
            for row in raw_parsed_rows
            if str(row["source_name"]) in ai_ready_source_names
        ]

        source_counts: Counter = Counter()
        event_type_counts: Counter = Counter()
        symbol_counts: Counter = Counter()
        symbol_rows_map: dict[str, list[dict]] = {}
        event_type_rows_map: dict[str, list[dict]] = {}

        for row in parsed_rows:
            source_counts[str(row["source_name"])] += 1
            event_type_counts[str(row["event_type"])] += 1
            symbol_counts[str(row["symbol"])] += 1
            symbol_rows_map.setdefault(str(row["symbol"]), []).append(row)
            event_type_rows_map.setdefault(str(row["event_type"]), []).append(row)

        raw_source_counts = self._count_rows_by_source(raw_parsed_rows)
        raw_event_type_counts: Counter = Counter(
            str(row["event_type"])
            for row in raw_parsed_rows
        )

        next_24h_rows = [
            row
            for row in parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(hours=24)
        ]
        next_7d_rows = [
            row
            for row in parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(days=7)
        ]
        next_30d_rows = [
            row
            for row in parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(days=30)
        ]
        high_importance_rows = [
            row
            for row in parsed_rows
            if float(row.get("importance_score") or 0.0) >= 0.8
        ]
        raw_next_24h_rows = [
            row
            for row in raw_parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(hours=24)
        ]
        raw_next_7d_rows = [
            row
            for row in raw_parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(days=7)
        ]
        raw_next_30d_rows = [
            row
            for row in raw_parsed_rows
            if row.get("scheduled_at_dt") is not None
            and row["scheduled_at_dt"] <= now + timedelta(days=30)
        ]
        high_importance_rows.sort(
            key=lambda item: (
                -float(item.get("importance_score") or 0.0),
                item.get("scheduled_at") or "",
                item["title"],
            )
        )

        configured_event_types = {
            str(row["event_type"])
            for row in coverage_rows
            if row.get("configuration_ready")
        }
        observed_event_types = set(event_type_counts)
        farthest_horizon_days = max(
            (
                round(max((row["scheduled_at_dt"] - now).total_seconds(), 0.0) / 86400, 4)
                for row in parsed_rows
                if row.get("scheduled_at_dt") is not None
            ),
            default=None,
        )
        raw_farthest_horizon_days = max(
            (
                round(max((row["scheduled_at_dt"] - now).total_seconds(), 0.0) / 86400, 4)
                for row in raw_parsed_rows
                if row.get("scheduled_at_dt") is not None
            ),
            default=None,
        )
        source_health = [
            {
                "source_name": row["source_name"],
                "event_type": row["event_type"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "configuration_ready": row["configuration_ready"],
                "upcoming_events": row["upcoming_events"],
                "upcoming_high_importance_events": row["upcoming_high_importance_events"],
                "total_events": row["total_events"],
                "minimum_horizon_days": row["minimum_horizon_days"],
                "farthest_event_horizon_days": row["farthest_event_horizon_days"],
                "last_run_status": row["last_run_status"],
                "is_stale": row["is_stale"],
                "data_quality_flags": row["data_quality_flags"],
                "quality_notes": row["quality_notes"],
            }
            for row in coverage_rows
        ]
        coverage_by_source = [
            {
                "source_name": row["source_name"],
                "event_type": row["event_type"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "configuration_ready": row["configuration_ready"],
                "upcoming_events": row["upcoming_events"],
                "upcoming_high_importance_events": row["upcoming_high_importance_events"],
                "minimum_horizon_days": row["minimum_horizon_days"],
                "farthest_event_horizon_days": row["farthest_event_horizon_days"],
            }
            for row in coverage_rows
        ]
        data_quality_flags, quality_notes = self._build_upcoming_context_quality(
            horizon_days=query_horizon_days,
            coverage_rows=coverage_rows,
            event_count=len(parsed_rows),
            raw_event_count=len(raw_parsed_rows),
            configured_event_types=configured_event_types,
            observed_event_types=observed_event_types,
            next_24h_count=len(next_24h_rows),
            next_7d_count=len(next_7d_rows),
            high_importance_count=len(high_importance_rows),
            asset_specific_symbol_count=sum(
                1
                for symbol in symbol_counts
                if symbol != "MARKET"
            ),
            farthest_horizon_days=farthest_horizon_days,
            configured_universe_summary=configured_universe_summary,
            symbol_filter_active=bool(symbols),
            ai_excluded_source_count=len(ai_excluded_sources),
        )

        event_type_universe = sorted(
            configured_event_types
            | {
                str(row["event_type"])
                for row in coverage_rows
            }
            | observed_event_types
        )

        return {
            "as_of": now.isoformat(),
            "row_count": len(parsed_rows),
            "event_count": len(parsed_rows),
            "raw_event_count": len(raw_parsed_rows),
            "source_counts": self._count_rows_by_source(parsed_rows),
            "raw_source_counts": raw_source_counts,
            "ai_ready_source_names": sorted(ai_ready_source_names),
            "ai_excluded_source_names": [
                str(item["source_name"])
                for item in ai_excluded_sources
            ],
            "ai_excluded_sources": ai_excluded_sources,
            "configured_universe_summary": configured_universe_summary,
            "coverage_summary": {
                "horizon_days": query_horizon_days,
                "selected_source_count": coverage.get("source_count", 0),
                "observed_source_count": len(source_counts),
                "raw_observed_source_count": len(raw_source_counts),
                "ready_source_count": coverage.get("ready_source_count", 0),
                "problem_source_count": coverage.get("problem_source_count", 0),
                "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
                "configured_event_types": sorted(configured_event_types),
                "observed_event_types": sorted(observed_event_types),
                "raw_observed_event_types": sorted(raw_event_type_counts),
                "missing_event_types": (
                    []
                    if symbols
                    else sorted(
                        configured_event_types
                        - {
                            str(row["event_type"])
                            for row in coverage_rows
                            if row.get("is_ready_for_ai")
                        }
                    )
                ),
                "event_count_next_24h": len(next_24h_rows),
                "event_count_next_7d": len(next_7d_rows),
                "event_count_next_30d": len(next_30d_rows),
                "raw_event_count_next_24h": len(raw_next_24h_rows),
                "raw_event_count_next_7d": len(raw_next_7d_rows),
                "raw_event_count_next_30d": len(raw_next_30d_rows),
                "farthest_event_horizon_days": farthest_horizon_days,
                "raw_farthest_event_horizon_days": raw_farthest_horizon_days,
                "ai_excluded_source_names": [
                    str(item["source_name"])
                    for item in ai_excluded_sources
                ],
                "coverage_by_source": coverage_by_source,
            },
            "source_health_summary": {
                "source_count": coverage.get("source_count", 0),
                "ready_source_count": coverage.get("ready_source_count", 0),
                "problem_source_count": coverage.get("problem_source_count", 0),
                "stale_source_count": coverage.get("stale_source_count", 0),
                "unconfigured_source_count": coverage.get("unconfigured_source_count", 0),
                "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
            },
            "source_health": source_health,
            "upcoming_events": [
                self._format_upcoming_event(row, now)
                for row in parsed_rows[: max(int(limit), 0)]
            ],
            "next_24h": {
                "event_count": len(next_24h_rows),
                "events": [
                    self._format_upcoming_event(row, now)
                    for row in next_24h_rows[: max(int(limit), 0)]
                ],
            },
            "next_7d": {
                "event_count": len(next_7d_rows),
                "events": [
                    self._format_upcoming_event(row, now)
                    for row in next_7d_rows[: max(int(limit), 0)]
                ],
            },
            "next_30d": {
                "event_count": len(next_30d_rows),
                "events": [
                    self._format_upcoming_event(row, now)
                    for row in next_30d_rows[: max(int(limit), 0)]
                ],
            },
            "high_importance_events": [
                self._format_upcoming_event(row, now)
                for row in high_importance_rows[: max(int(limit), 0)]
            ],
            "by_event_type": [
                {
                    "event_type": event_type,
                    "event_count": len(event_type_rows_map.get(event_type) or []),
                    "high_importance_event_count": sum(
                        1
                        for row in (event_type_rows_map.get(event_type) or [])
                        if float(row.get("importance_score") or 0.0) >= 0.8
                    ),
                    "source_count": len(
                        {
                            str(row["source_name"])
                            for row in (event_type_rows_map.get(event_type) or [])
                        }
                    ),
                    "next_event_at": (
                        min(
                            (
                                row["scheduled_at"]
                                for row in (event_type_rows_map.get(event_type) or [])
                                if row.get("scheduled_at")
                            ),
                            default=None,
                        )
                    ),
                }
                for event_type in sorted(
                    event_type_universe,
                    key=lambda item: (
                        -(event_type_counts.get(item) or 0),
                        item,
                    ),
                )
            ],
            "symbol_watchlist": [
                {
                    "symbol": symbol,
                    "event_count": len(rows),
                    "high_importance_event_count": sum(
                        1
                        for row in rows
                        if float(row.get("importance_score") or 0.0) >= 0.8
                    ),
                    "next_event_at": min(
                        (
                            row["scheduled_at"]
                            for row in rows
                            if row.get("scheduled_at")
                        ),
                        default=None,
                    ),
                    "event_types": sorted(
                        {
                            str(row["event_type"])
                            for row in rows
                        }
                    ),
                    "source_names": sorted(
                        {
                            str(row["source_name"])
                            for row in rows
                        }
                    ),
                    "top_titles": self._top_titles(rows),
                }
                for symbol, rows in sorted(
                    symbol_rows_map.items(),
                    key=lambda item: (
                        -len(item[1]),
                        -max(
                            float(row.get("importance_score") or 0.0)
                            for row in item[1]
                        ),
                        item[0],
                    ),
                )
            ],
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
        }

    def _run_scheduled_collect(
        self,
        lookahead_days: int | None = None,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
    ):
        local_db = DBManager(self.db.db_path)
        local_service = EventCalendarDataService(client=self.client, db=local_db)
        try:
            return local_service.collect_once(
                lookahead_days=lookahead_days,
                source_names=source_names,
                event_types=event_types,
                symbols=symbols,
            )
        finally:
            local_service.close()

    def build_scheduler(
        self,
        lookahead_days: int | None = None,
        source_names: list[str] | None = None,
        event_types: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self._run_scheduled_collect,
            "interval",
            seconds=EVENT_CALENDAR_CONFIG["interval_seconds"],
            id="event_calendar_events",
            name="事件日历采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(300, EVENT_CALENDAR_CONFIG["interval_seconds"]),
            kwargs={
                "lookahead_days": (
                    lookahead_days
                    if lookahead_days is not None
                    else EVENT_CALENDAR_CONFIG["lookahead_days"]
                ),
                "source_names": source_names,
                "event_types": event_types,
                "symbols": symbols,
            },
        )
        return scheduler

    def close(self):
        self.db.close()
