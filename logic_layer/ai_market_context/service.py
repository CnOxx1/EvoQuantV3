from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from database.db_manager import DBManager
from data_layer.alternative_data.service import AlternativeDataService
from data_layer.data_quality.audit import DataLayerAuditService
from data_layer.event_calendar_data.service import EventCalendarDataService
from data_layer.exchange_data.service import ExchangeDataService
from data_layer.news_data.service import NewsDataService
from data_layer.onchain_data.service import OnchainDataService
from data_layer.tokenomics_data.service import TokenomicsDataService
from logic_layer.ai_market_context.models import AIMarketContextSnapshot
from logic_layer.ai_market_context.repository import AIMarketContextRepository
from logic_layer.asset_readiness.service import AssetReadinessService
from logic_layer.macro_context.service import MacroContextService
from logic_layer.market_breadth.service import MarketBreadthService
from logic_layer.market_structure.service import MarketStructureService
from logic_layer.news_sentiment.service import NewsSentimentService
from logic_layer.pipeline_latency.service import PipelineLatencyService


class AIMarketContextService:
    """将多模块 latest 快照重组为 AI 可直接消费的市场上下文。"""

    BLOCKING_CROSS_EXCHANGE_QUALITY_PREFIXES = (
        "missing_ticker",
        "stale_ticker",
        "missing_orderbook",
        "stale_orderbook",
        "missing_bid_ask",
        "cross_exchange_ticker_gap",
        "cross_exchange_orderbook_gap",
    )

    def __init__(
        self,
        db: DBManager | None = None,
        repository: AIMarketContextRepository | None = None,
        exchange_service: ExchangeDataService | None = None,
        news_service: NewsDataService | None = None,
        event_calendar_service: EventCalendarDataService | None = None,
        onchain_service: OnchainDataService | None = None,
        tokenomics_service: TokenomicsDataService | None = None,
        alternative_service: AlternativeDataService | None = None,
        macro_context_service: MacroContextService | None = None,
        audit_service: DataLayerAuditService | None = None,
        market_breadth_service: MarketBreadthService | None = None,
        asset_readiness_service: AssetReadinessService | None = None,
        market_structure_service: MarketStructureService | None = None,
        cross_asset_service=None,
        portfolio_risk_service=None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.repository = repository or AIMarketContextRepository(self.db)
        self.exchange_service = exchange_service or ExchangeDataService(db=self.db)
        self.news_service = news_service or NewsDataService(db=self.db)
        self.event_calendar_service = (
            event_calendar_service or EventCalendarDataService(db=self.db)
        )
        self.onchain_service = onchain_service or OnchainDataService(db=self.db)
        self.tokenomics_service = tokenomics_service or TokenomicsDataService(db=self.db)
        self.alternative_service = alternative_service or AlternativeDataService(db=self.db)
        self.macro_context_service = macro_context_service or MacroContextService(db=self.db)
        self.audit_service = audit_service or DataLayerAuditService(db=self.db)
        self.market_breadth_service = market_breadth_service or MarketBreadthService(db=self.db)
        self.asset_readiness_service = (
            asset_readiness_service or AssetReadinessService(db=self.db)
        )
        self.market_structure_service = (
            market_structure_service or MarketStructureService(db=self.db)
        )
        self.cross_asset_service = cross_asset_service
        self.portfolio_risk_service = portfolio_risk_service
        self._news_sentiment_service = None
        self._pipeline_latency_service = None

    def init_storage(self):
        self.db.init_analytics_tables()

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_asset_from_symbol(symbol: str | None) -> str | None:
        raw_symbol = str(symbol or "").strip().upper()
        if not raw_symbol:
            return None
        if "/" in raw_symbol:
            base, _, quote = raw_symbol.partition("/")
            return base if quote else raw_symbol
        for quote_suffix in ("USDT", "USDC", "FDUSD", "BUSD", "USD"):
            if raw_symbol.endswith(quote_suffix) and len(raw_symbol) > len(quote_suffix):
                return raw_symbol[: -len(quote_suffix)]
        return raw_symbol

    @staticmethod
    def _dedupe_texts(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

    @staticmethod
    def _counter_to_ranked_rows(counter: Counter, field_name: str) -> list[dict]:
        total = sum(counter.values()) or 1
        return [
            {
                field_name: key,
                "count": count,
                "share": round(count / total, 4),
            }
            for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    @classmethod
    def _parse_compound_quality_flags(cls, value) -> list[str]:
        if value is None:
            return []
        raw_items = value if isinstance(value, (list, tuple, set)) else str(value).split("|")
        return [
            text
            for text in cls._dedupe_texts([str(item or "").strip() for item in raw_items])
            if text and text != "ok"
        ]

    @staticmethod
    def _cross_exchange_pair_label(row: dict) -> str | None:
        exchange_a = str(row.get("exchange_a") or "").strip().lower()
        exchange_b = str(row.get("exchange_b") or "").strip().lower()
        if not exchange_a or not exchange_b:
            return None
        return f"{exchange_a}-{exchange_b}"

    @classmethod
    def _is_cross_exchange_row_ai_visible(cls, row: dict) -> bool:
        signal_label = str(row.get("signal_label") or "").strip().lower()
        if signal_label == "data_quality_warning":
            return False
        quality_flags = cls._parse_compound_quality_flags(row.get("data_quality_flag"))
        return not any(
            flag == "cross_exchange_ticker_gap"
            or flag == "cross_exchange_orderbook_gap"
            or flag.startswith(cls.BLOCKING_CROSS_EXCHANGE_QUALITY_PREFIXES)
            for flag in quality_flags
        )

    @classmethod
    def _build_cross_exchange_execution_view(
        cls,
        rows: list[dict],
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows = [dict(row) for row in rows or []]
        visible_rows: list[dict] = []
        excluded_rows: list[dict] = []
        raw_signal_counter: Counter = Counter()
        visible_signal_counter: Counter = Counter()
        excluded_signal_counter: Counter = Counter()
        raw_quality_counter: Counter = Counter()
        excluded_quality_counter: Counter = Counter()
        raw_pairs: set[str] = set()
        visible_pairs: set[str] = set()
        excluded_pairs: set[str] = set()
        raw_actionable_row_count = 0
        visible_actionable_row_count = 0

        for row in raw_rows:
            signal_label = str(row.get("signal_label") or "normal").strip() or "normal"
            raw_signal_counter[signal_label] += 1
            quality_flags = cls._parse_compound_quality_flags(row.get("data_quality_flag"))
            for flag in quality_flags:
                raw_quality_counter[flag] += 1
            pair_label = cls._cross_exchange_pair_label(row)
            if pair_label:
                raw_pairs.add(pair_label)
            if bool(row.get("is_actionable")):
                raw_actionable_row_count += 1

            if cls._is_cross_exchange_row_ai_visible(row):
                visible_rows.append(row)
                visible_signal_counter[signal_label] += 1
                if pair_label:
                    visible_pairs.add(pair_label)
                if bool(row.get("is_actionable")):
                    visible_actionable_row_count += 1
                continue

            excluded_rows.append(row)
            excluded_signal_counter[signal_label] += 1
            if pair_label:
                excluded_pairs.add(pair_label)
            for flag in quality_flags:
                excluded_quality_counter[flag] += 1

        status = "missing"
        if raw_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif raw_rows and visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"

        return visible_rows, raw_rows, {
            "status": status,
            "raw_row_count": len(raw_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(excluded_rows),
            "raw_actionable_row_count": raw_actionable_row_count,
            "visible_actionable_row_count": visible_actionable_row_count,
            "raw_exchange_pair_count": len(raw_pairs),
            "visible_exchange_pair_count": len(visible_pairs),
            "excluded_exchange_pair_count": len(excluded_pairs),
            "raw_exchange_pairs": sorted(raw_pairs),
            "visible_exchange_pairs": sorted(visible_pairs),
            "excluded_exchange_pairs": sorted(excluded_pairs),
            "raw_signal_labels": cls._counter_to_ranked_rows(
                raw_signal_counter,
                "signal_label",
            ),
            "visible_signal_labels": cls._counter_to_ranked_rows(
                visible_signal_counter,
                "signal_label",
            ),
            "excluded_signal_labels": cls._counter_to_ranked_rows(
                excluded_signal_counter,
                "signal_label",
            ),
            "raw_quality_flags": cls._counter_to_ranked_rows(
                raw_quality_counter,
                "data_quality_flag",
            ),
            "excluded_quality_flags": cls._counter_to_ranked_rows(
                excluded_quality_counter,
                "data_quality_flag",
            ),
            "raw_only_due_to_quality_issues": bool(raw_rows and not visible_rows),
        }

    @staticmethod
    def _band_report_map(audit_payload: dict | None) -> dict[str, dict]:
        return {
            str(item.get("band_name")): dict(item)
            for item in ((audit_payload or {}).get("bands") or [])
        }

    @classmethod
    def _filter_news_rows_for_entity(
        cls,
        news_bundle: dict,
        entity_key: str,
    ) -> list[dict]:
        entity = entity_key.upper()
        matched_rows: list[dict] = []
        for row in news_bundle.get("latest_articles") or []:
            symbols = row.get("relevance_symbols") or row.get("relevance_symbols_list") or []
            normalized_symbols = {
                cls._normalize_asset_from_symbol(symbol)
                for symbol in symbols
            }
            if entity in normalized_symbols:
                matched_rows.append(dict(row))
        return matched_rows

    @staticmethod
    def _select_asset_readiness_row(
        asset_readiness_payload: dict | None,
        entity_key: str,
    ) -> dict:
        target = entity_key.upper()
        for item in (asset_readiness_payload or {}).get("assets") or []:
            if str(item.get("asset") or "").upper() == target:
                return dict(item)
        return {
            "asset": target,
            "asset_status": "blocked",
            "readiness_score": 0.0,
            "ready_band_count": 0,
            "limited_band_count": 0,
            "missing_band_count": 0,
            "missing_band_names": [],
            "limited_band_names": [],
            "bands": {},
            "quality_notes": ["当前没有该资产的真实 readiness 画像。"],
        }

    @staticmethod
    def _coverage_score(asset_readiness_row: dict) -> float:
        try:
            return round(float(asset_readiness_row.get("readiness_score") or 0.0), 4)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _quality_flag(
        *,
        coverage_score: float,
        world_status: str,
        asset_status: str,
        breadth_status: str,
    ) -> str:
        if (
            world_status == "ready"
            and asset_status == "ready"
            and breadth_status == "sufficient"
            and coverage_score >= 0.8
        ):
            return "ok"
        if asset_status in {"ready", "partial"} and coverage_score >= 0.45:
            return "partial"
        if world_status == "blocked" and coverage_score <= 0.2:
            return "blocked"
        return "thin"

    def _build_quality_assessment(
        self,
        *,
        entity_key: str,
        audit_payload: dict,
        market_breadth_bundle: dict,
        asset_readiness_row: dict,
        news_rows: list[dict],
        upcoming_events: list[dict],
        macro_visible: bool,
        cross_exchange_quality_summary: dict,
    ) -> tuple[str, list[str], list[str]]:
        audit_summary = dict(audit_payload.get("summary") or {})
        world_status = str(audit_summary.get("world_model_status") or "blocked")
        breadth_status = str(market_breadth_bundle.get("breadth_status") or "thin")
        asset_status = str(asset_readiness_row.get("asset_status") or "blocked")
        coverage_score = self._coverage_score(asset_readiness_row)

        data_quality_flag = self._quality_flag(
            coverage_score=coverage_score,
            world_status=world_status,
            asset_status=asset_status,
            breadth_status=breadth_status,
        )

        data_quality_flags: list[str] = []
        if world_status == "blocked":
            data_quality_flags.append("market_world_model_blocked")
        elif world_status == "partial":
            data_quality_flags.append("market_world_model_partial")

        if asset_status == "blocked":
            data_quality_flags.append("asset_evidence_blocked")
        elif asset_status == "thin":
            data_quality_flags.append("asset_evidence_thin")
        elif asset_status == "partial":
            data_quality_flags.append("asset_evidence_partial")

        if breadth_status == "thin":
            data_quality_flags.append("market_breadth_thin")
        elif breadth_status == "narrow":
            data_quality_flags.append("market_breadth_narrow")

        if not news_rows:
            data_quality_flags.append("news_context_missing")
        if not upcoming_events:
            data_quality_flags.append("event_context_missing")
        if not macro_visible:
            data_quality_flags.append("macro_context_not_ai_ready")
        if bool(cross_exchange_quality_summary.get("raw_only_due_to_quality_issues")):
            data_quality_flags.append("cross_exchange_execution_not_ai_ready")

        quality_notes = [
            note
            for note in (
                list(asset_readiness_row.get("quality_notes") or [])
                + list(market_breadth_bundle.get("quality_notes") or [])
            )
            if str(note or "").strip()
        ]
        critical_gap_band_names = list(audit_summary.get("critical_gap_band_names") or [])
        if critical_gap_band_names:
            quality_notes.append(
                "当前 required 证据带仍存在缺口: " + ", ".join(critical_gap_band_names) + "。"
            )
        if not news_rows:
            quality_notes.append(f"最近 72 小时没有命中 {entity_key.upper()} 的 AI-ready 新闻。")
        if not upcoming_events:
            quality_notes.append(f"未来 30 天没有命中 {entity_key.upper()} 的 AI-ready 事件。")
        if not macro_visible:
            quality_notes.append(
                "宏观上下文虽然可能存在原始快照，但当前宏观证据带未达到 AI-ready，因此已从主视图剥离。"
            )
        cross_exchange_raw_count = int(cross_exchange_quality_summary.get("raw_row_count") or 0)
        cross_exchange_visible_count = int(
            cross_exchange_quality_summary.get("visible_row_count") or 0
        )
        cross_exchange_excluded_count = int(
            cross_exchange_quality_summary.get("excluded_row_count") or 0
        )
        if cross_exchange_raw_count > 0 and cross_exchange_visible_count <= 0:
            quality_notes.append(
                "跨交易所执行上下文存在真实原始快照，但全部因时间错位、盘口陈旧或报价缺失等质量问题未进入 AI 主视图。"
            )
        elif cross_exchange_excluded_count > 0:
            quality_notes.append(
                f"跨交易所执行上下文已过滤 {cross_exchange_excluded_count} 条质量不足的原始对比快照，仅保留 {cross_exchange_visible_count} 条 AI-ready 结果。"
            )

        return data_quality_flag, data_quality_flags, self._dedupe_texts(quality_notes)[:16]

    def _build_data_readiness_section(
        self,
        *,
        audit_payload: dict,
        market_breadth_bundle: dict,
        asset_readiness_row: dict,
        cross_exchange_quality_summary: dict,
    ) -> dict:
        audit_summary = dict(audit_payload.get("summary") or {})
        return {
            "market_world_status": audit_summary.get("world_model_status"),
            "market_world_summary": audit_summary,
            "market_breadth_status": market_breadth_bundle.get("breadth_status"),
            "market_breadth_score": market_breadth_bundle.get("breadth_score"),
            "market_breadth_asset_count": market_breadth_bundle.get("asset_count"),
            "market_breadth_ai_ready_asset_count": market_breadth_bundle.get(
                "ai_ready_asset_count"
            ),
            "market_breadth_data_quality_flag": market_breadth_bundle.get("data_quality_flag"),
            "market_breadth_data_quality_flags": list(
                market_breadth_bundle.get("data_quality_flags") or []
            ),
            "asset_status": asset_readiness_row.get("asset_status"),
            "asset_readiness_score": asset_readiness_row.get("readiness_score"),
            "ready_band_count": asset_readiness_row.get("ready_band_count"),
            "limited_band_count": asset_readiness_row.get("limited_band_count"),
            "missing_band_count": asset_readiness_row.get("missing_band_count"),
            "missing_band_names": list(asset_readiness_row.get("missing_band_names") or []),
            "limited_band_names": list(asset_readiness_row.get("limited_band_names") or []),
            "band_statuses": {
                band_name: {
                    "status": band_detail.get("status"),
                    "weight": band_detail.get("weight"),
                    "weighted_score": band_detail.get("weighted_score"),
                    "notes": list(band_detail.get("notes") or []),
                }
                for band_name, band_detail in ((asset_readiness_row.get("bands") or {}).items())
            },
            "cross_exchange_execution_status": cross_exchange_quality_summary.get("status"),
            "cross_exchange_execution_raw_row_count": cross_exchange_quality_summary.get(
                "raw_row_count"
            ),
            "cross_exchange_execution_visible_row_count": cross_exchange_quality_summary.get(
                "visible_row_count"
            ),
            "cross_exchange_execution_excluded_row_count": cross_exchange_quality_summary.get(
                "excluded_row_count"
            ),
        }

    def build_bundle_for_entity(
        self,
        entity_key: str,
        audit_payload: dict | None = None,
        market_breadth_bundle: dict | None = None,
        asset_readiness_payload: dict | None = None,
    ) -> dict:
        symbol = f"{entity_key.upper()}/USDT"
        resolved_audit_payload = audit_payload or self.audit_service.load_market_world_audit()
        resolved_market_breadth_bundle = (
            market_breadth_bundle or self.market_breadth_service.build_latest_context_bundle()
        )
        resolved_asset_readiness_payload = asset_readiness_payload or (
            self.asset_readiness_service.build_latest_context_bundle(
                asset_keys=[entity_key],
                audit_payload=resolved_audit_payload,
            )
        )
        asset_readiness_row = self._select_asset_readiness_row(
            resolved_asset_readiness_payload,
            entity_key,
        )
        band_reports = self._band_report_map(resolved_audit_payload)

        exchange_bundle = self.exchange_service.load_latest_market_context_bundle(
            symbols=[symbol]
        )
        news_bundle = self.news_service.load_latest_context_bundle(hours=72, limit=200)
        event_bundle = self.event_calendar_service.load_upcoming_context_bundle(
            horizon_days=30,
            symbols=[entity_key.upper()],
            limit=50,
        )
        onchain_bundle = self.onchain_service.load_latest_context_bundle(
            entity_keys=[entity_key]
        )
        tokenomics_bundle = self.tokenomics_service.load_latest_context_bundle(
            entity_keys=[entity_key]
        )
        market_structure_bundle = self.market_structure_service.build_latest_context_bundle(
            asset_keys=[entity_key],
        )
        alternative_bundle = self.alternative_service.load_latest_context_bundle(
            entity_keys=[entity_key, entity_key.lower()],
        )
        macro_bundle = self.macro_context_service.load_latest_context_bundle(interval="1d")
        news_rows = self._filter_news_rows_for_entity(news_bundle, entity_key)
        event_rows = list(event_bundle.get("upcoming_events") or [])
        exchange_comparison_rows = self.repository.fetch_latest_exchange_comparison(symbol)
        (
            visible_cross_exchange_rows,
            raw_cross_exchange_rows,
            cross_exchange_quality_summary,
        ) = self._build_cross_exchange_execution_view(exchange_comparison_rows)
        macro_band_report = band_reports.get("macro") or {}
        macro_visible = bool(macro_band_report.get("is_band_ready_for_ai"))
        visible_macro_bundle = macro_bundle if macro_visible else {}

        bundle = {
            "as_of": self._utc_now_naive().isoformat(),
            "entity_key": entity_key.upper(),
            "market_microstructure": (
                exchange_bundle["symbols"][0] if exchange_bundle.get("symbols") else {}
            ),
            "derivatives_structure": {
                "trade_flow": (
                    exchange_bundle["symbols"][0].get("trade_flow")
                    if exchange_bundle.get("symbols")
                    else []
                ),
                "funding": (
                    exchange_bundle["symbols"][0].get("funding")
                    if exchange_bundle.get("symbols")
                    else []
                ),
                "open_interest": (
                    exchange_bundle["symbols"][0].get("open_interest")
                    if exchange_bundle.get("symbols")
                    else []
                ),
                "liquidations": (
                    exchange_bundle["symbols"][0].get("liquidations")
                    if exchange_bundle.get("symbols")
                    else []
                ),
                "positioning": (
                    exchange_bundle["symbols"][0].get("positioning")
                    if exchange_bundle.get("symbols")
                    else []
                ),
                "basis": (
                    exchange_bundle["symbols"][0].get("basis")
                    if exchange_bundle.get("symbols")
                    else []
                ),
            },
            "cross_exchange_execution": visible_cross_exchange_rows,
            "raw_cross_exchange_execution": raw_cross_exchange_rows,
            "cross_exchange_execution_quality_summary": cross_exchange_quality_summary,
            "market_structure": (
                market_structure_bundle["assets"][0]
                if market_structure_bundle.get("assets")
                else {}
            ),
            "onchain_capital_flow": onchain_bundle,
            "tokenomics_supply_pressure": tokenomics_bundle,
            "macro_regime": visible_macro_bundle,
            "raw_macro_regime": macro_bundle,
            "news_and_events": {
                "recent_news": news_rows,
                "upcoming_events": event_rows,
                "article_count_72h": len(news_rows),
                "source_count_72h": len(
                    {
                        str(item.get("source") or "")
                        for item in news_rows
                        if str(item.get("source") or "").strip()
                    }
                ),
                "event_count_30d": len(event_rows),
                "event_source_count_30d": len(
                    {
                        str(item.get("source_name") or "")
                        for item in event_rows
                        if str(item.get("source_name") or "").strip()
                    }
                ),
                "news_data_quality_flags": list(news_bundle.get("data_quality_flags") or []),
                "event_data_quality_flags": list(event_bundle.get("data_quality_flags") or []),
            },
            "attention_and_builder_activity": alternative_bundle,
            "cross_asset_context": self._build_cross_asset_context(entity_key),
            "portfolio_risk_context": self._build_portfolio_risk_context(),
            "feature_standardization_context": self._build_feature_standardization_context(entity_key),
            "news_sentiment_context": self._build_news_sentiment_context(),
            "pipeline_latency_context": self._build_pipeline_latency_context(),
            "data_readiness": self._build_data_readiness_section(
                audit_payload=resolved_audit_payload,
                market_breadth_bundle=resolved_market_breadth_bundle,
                asset_readiness_row=asset_readiness_row,
                cross_exchange_quality_summary=cross_exchange_quality_summary,
            ),
        }

        coverage_score = self._coverage_score(asset_readiness_row)
        (
            data_quality_flag,
            data_quality_flags,
            quality_notes,
        ) = self._build_quality_assessment(
            entity_key=entity_key,
            audit_payload=resolved_audit_payload,
            market_breadth_bundle=resolved_market_breadth_bundle,
            asset_readiness_row=asset_readiness_row,
            news_rows=news_rows,
            upcoming_events=event_rows,
            macro_visible=macro_visible,
            cross_exchange_quality_summary=cross_exchange_quality_summary,
        )
        bundle["coverage_score"] = coverage_score
        bundle["data_quality_flag"] = data_quality_flag
        bundle["data_quality_flags"] = data_quality_flags
        bundle["quality_notes"] = quality_notes
        bundle["risk_flags"] = self._build_risk_flags(bundle)
        bundle["evidence"] = self._build_evidence(bundle)
        bundle["world_model_index"] = self._compute_world_model_index(
            coverage_score=coverage_score,
            pipeline_latency_context=bundle.get("pipeline_latency_context") or {},
            data_quality_flag=data_quality_flag,
            data_quality_flags=data_quality_flags,
        )
        return bundle

    def _build_risk_flags(self, bundle: dict) -> list[str]:
        flags: list[str] = []
        if str(bundle.get("data_quality_flag") or "") in {"blocked", "thin"}:
            flags.append("insufficient_market_evidence")

        data_readiness = bundle.get("data_readiness") or {}
        if str(data_readiness.get("market_world_status") or "") == "blocked":
            flags.append("market_world_model_blocked")
        if str(data_readiness.get("market_breadth_status") or "") == "thin":
            flags.append("market_breadth_thin")

        # 组合风险标记
        portfolio_ctx = bundle.get("portfolio_risk_context") or {}
        if portfolio_ctx.get("status") == "ready":
            ann_vol = portfolio_ctx.get("annualized_volatility") or 0
            if ann_vol > 1.0:
                flags.append("portfolio_high_volatility")
            div_ratio = portfolio_ctx.get("diversification_ratio") or 0
            if div_ratio < 1.1:
                flags.append("portfolio_low_diversification")

        tokenomics = bundle.get("tokenomics_supply_pressure") or {}
        unlock_watchlist = tokenomics.get("unlock_watchlist") or []
        if unlock_watchlist:
            first = unlock_watchlist[0]
            if float(first.get("scheduled_unlock_usd_7d") or 0.0) > 0:
                flags.append("scheduled_unlock_pressure_present")

        derivatives = bundle.get("derivatives_structure") or {}
        liquidations = derivatives.get("liquidations") or []
        if liquidations:
            liquidation_values = [
                self._safe_float(item.get("total_liquidation_notional"))
                for item in liquidations
            ]
            liquidation_values = [
                value
                for value in liquidation_values
                if value is not None
            ]
            if liquidation_values and max(liquidation_values) > 0:
                flags.append("recent_liquidation_activity_present")

        return flags

    @staticmethod
    def _build_evidence(bundle: dict) -> list[dict]:
        evidence: list[dict] = []

        tokenomics = bundle.get("tokenomics_supply_pressure") or {}
        for item in tokenomics.get("unlock_watchlist") or []:
            evidence.append(
                {
                    "source": "tokenomics_data",
                    "type": "unlock_pressure",
                    "entity_key": item.get("entity_key"),
                    "value": item.get("scheduled_unlock_usd_7d"),
                }
            )

        for item in (bundle.get("news_and_events") or {}).get("recent_news") or []:
            evidence.append(
                {
                    "source": "news_data",
                    "type": "recent_news",
                    "title": item.get("title"),
                    "published_at": item.get("published_at"),
                }
            )

        for item in (bundle.get("news_and_events") or {}).get("upcoming_events") or []:
            evidence.append(
                {
                    "source": "event_calendar_data",
                    "type": "upcoming_event",
                    "title": item.get("title"),
                    "scheduled_at": item.get("scheduled_at"),
                    "symbol": item.get("symbol"),
                }
            )

        return evidence[:20]

    def build_latest_snapshots(
        self,
        entity_keys: list[str],
        persist: bool = True,
    ) -> list[AIMarketContextSnapshot]:
        normalized_entity_keys: list[str] = []
        seen: set[str] = set()
        for entity_key in entity_keys:
            normalized = str(entity_key or "").strip().upper()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_entity_keys.append(normalized)

        audit_payload = self.audit_service.load_market_world_audit()
        market_breadth_bundle = self.market_breadth_service.build_latest_context_bundle()
        asset_readiness_payload = self.asset_readiness_service.build_latest_context_bundle(
            asset_keys=normalized_entity_keys,
            audit_payload=audit_payload,
        )

        snapshots = []
        for entity_key in normalized_entity_keys:
            bundle = self.build_bundle_for_entity(
                entity_key,
                audit_payload=audit_payload,
                market_breadth_bundle=market_breadth_bundle,
                asset_readiness_payload=asset_readiness_payload,
            )
            snapshots.append(
                AIMarketContextSnapshot(
                    entity_key=entity_key,
                    snapshot_time=self._utc_now_naive(),
                    coverage_score=float(bundle["coverage_score"]),
                    data_quality_flag=str(bundle["data_quality_flag"]),
                    bundle=bundle,
                )
            )
        if persist:
            self.repository.save_snapshots(snapshots)
        return snapshots

    def load_latest_context_bundle(
        self,
        entity_keys: list[str] | None = None,
    ) -> dict:
        snapshots = self.repository.load_latest_snapshots(entity_keys=entity_keys)
        return {
            "as_of": self._utc_now_naive().isoformat(),
            "entity_count": len(snapshots),
            "entities": [snapshot["bundle"] for snapshot in snapshots],
        }

    def close(self):
        self.db.close()

    def _build_cross_asset_context(self, entity_key: str) -> dict:
        """构建跨资产分析上下文（相关性 regime、RS 排名、板块轮动）。"""
        try:
            if self.cross_asset_service is None:
                from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService
                self.cross_asset_service = CrossAssetAnalysisService(db=self.db)
            return self.cross_asset_service.load_latest_context_bundle()
        except Exception:
            return {"status": "unavailable"}

    def _build_portfolio_risk_context(self) -> dict:
        """构建组合风险上下文（波动率、集中度、分散化评分）。"""
        try:
            if self.portfolio_risk_service is None:
                from logic_layer.portfolio_risk.service import PortfolioRiskService
                self.portfolio_risk_service = PortfolioRiskService(db=self.db)
            return self.portfolio_risk_service.load_latest_context_bundle()
        except Exception:
            return {"status": "unavailable"}

    def _build_feature_standardization_context(self, entity_key: str) -> dict:
        """构建特征标准化上下文（Z-score、百分位、跨资产排名、复合信号）。"""
        try:
            if not hasattr(self, "_feature_std_service") or self._feature_std_service is None:
                from logic_layer.feature_standardization.service import FeatureStandardizationService
                self._feature_std_service = FeatureStandardizationService(db=self.db)
            bundle = self._feature_std_service.load_latest_context_bundle()
            if bundle.get("status") == "no_data":
                return {"status": "unavailable"}
            # 提取当前资产的标准化信号
            symbol = f"{entity_key}/USDT" if "/" not in entity_key else entity_key
            asset_data = next(
                (a for a in bundle.get("assets", []) if a["symbol"] == symbol),
                None,
            )
            return {
                "status": "ready" if asset_data else "unavailable",
                "as_of": bundle.get("as_of"),
                "asset_signals": asset_data,
                "market_extremes": bundle.get("market_extremes"),
            }
        except Exception:
            return {"status": "unavailable"}

    def _build_news_sentiment_context(self) -> dict:
        """构建新闻情感标注上下文。"""
        try:
            if self._news_sentiment_service is None:
                self._news_sentiment_service = NewsSentimentService(db=self.db)
            return self._news_sentiment_service.load_latest_context_bundle(hours=72)
        except Exception:
            return {"status": "unavailable"}

    def _build_pipeline_latency_context(self) -> dict:
        """构建数据管道延迟上下文。"""
        try:
            if self._pipeline_latency_service is None:
                self._pipeline_latency_service = PipelineLatencyService(db=self.db)
            report = self._pipeline_latency_service.measure_all()
            domains_dict = {}
            for name, dl in report.domains.items():
                domains_dict[name] = {
                    "status": dl.status,
                    "latest_data_time": dl.latest_data_time,
                    "latency_seconds": dl.latency_seconds,
                }
            return {
                "status": "ready",
                "measured_at": report.measured_at,
                "domains": domains_dict,
                "summary": report.summary,
            }
        except Exception:
            return {"status": "unavailable"}

    @staticmethod
    def _compute_world_model_index(
        *,
        coverage_score: float,
        pipeline_latency_context: dict,
        data_quality_flag: str,
        data_quality_flags: list[str],
    ) -> dict:
        """计算世界模型质量指数 WMI = B_t × U_t × H_t。

        B_t (宽度): 基于 asset_readiness coverage_score
        U_t (稳定性): 基于 pipeline_latency 各域新鲜度
        H_t (诚实性): 基于质量门控拦截率
        """
        # B_t: 直接使用 coverage_score (0~1)
        breadth = coverage_score

        # U_t: 基于 pipeline_latency summary
        latency_summary = pipeline_latency_context.get("summary") or {}
        total_domains = latency_summary.get("total_domains") or 1
        fresh = latency_summary.get("fresh") or 0
        acceptable = latency_summary.get("acceptable") or 0
        stability = (fresh + acceptable * 0.7) / total_domains if total_domains > 0 else 0.0
        stability = min(1.0, max(0.0, stability))

        # H_t: 基于质量门控状态
        # 诚实性 = 系统成功拦截了不合格数据的比例
        flag_penalties = {
            "market_world_model_blocked": 0.3,
            "asset_evidence_blocked": 0.2,
            "asset_evidence_thin": 0.1,
            "macro_context_not_ai_ready": 0.05,
            "cross_exchange_execution_not_ai_ready": 0.05,
            "news_context_missing": 0.05,
        }
        # 有门控标记说明系统在正确拦截（诚实），没有门控但 quality 差反而不诚实
        if data_quality_flag in ("ok", "partial"):
            honesty = 1.0  # 系统认为数据可用，且有门控机制在工作
        elif data_quality_flag == "thin":
            honesty = 0.7  # 数据薄但系统诚实标记了
        else:
            honesty = 0.4  # blocked 状态

        wmi = round(breadth * stability * honesty, 4)

        return {
            "wmi": wmi,
            "breadth": round(breadth, 4),
            "stability": round(stability, 4),
            "honesty": round(honesty, 4),
            "interpretation": (
                "sufficient" if wmi >= 0.6
                else "marginal" if wmi >= 0.3
                else "insufficient"
            ),
            "should_ai_abstain": wmi < 0.2,
        }
