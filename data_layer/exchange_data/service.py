import json
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from loguru import logger
from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import (
    EXCHANGE_DATA_RETENTION,
    EXCHANGE_DERIVATIVES_CONFIG,
    SCHEDULER_CONFIG,
)
from config.symbols import KLINE_TIMEFRAMES, TARGET_EXCHANGES, TARGET_SYMBOLS
from database.db_manager import DBManager
from data_layer.data_quality import (
    resolve_source_health_status,
    summarize_health_rows,
)
from data_layer.exchange_data.basis import BasisCollector
from data_layer.exchange_data.client import ExchangeClientManager
from data_layer.exchange_data.funding import FundingRateCollector
from data_layer.exchange_data.kline import KlineCollector
from data_layer.exchange_data.liquidations import LiquidationsCollector
from data_layer.exchange_data.long_short_ratio import LongShortRatioCollector
from data_layer.exchange_data.market_info import MarketInfoCollector
from data_layer.exchange_data.open_interest import OpenInterestCollector
from data_layer.exchange_data.orderbook import OrderBookCollector
from data_layer.exchange_data.taker_flow import TakerFlowCollector
from data_layer.exchange_data.ticker import TickerCollector
from data_layer.exchange_data.trades import TradesCollector


class ExchangeDataService:
    """交易所数据模块的统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH = 6
    MINIMUM_EXCHANGE_COUNT_FOR_MARKET_BREADTH = 4
    # Hot streams: health must track observation freshness, not a stale run row.
    OBSERVATION_PRIMARY_HEALTH_SOURCES = frozenset(
        {"ticker", "orderbook", "trade_flow", "open_interest", "funding", "basis"}
    )

    AI_CRITICAL_SOURCE_FLAGS = {
        "exchange_coverage_incomplete",
        "stale_pairs_present",
    }
    AI_CRITICAL_TRADE_FLOW_FLAGS = {
        "trade_flow_spot_only",
        "trade_flow_derivatives_missing",
        "trade_flow_derivatives_coverage_incomplete",
    }
    BUNDLE_SOURCE_TIME_FIELDS = {
        "ticker": "timestamp",
        "orderbook": "timestamp",
        "funding": "timestamp",
        "trade_flow": "open_time",
        "open_interest": "timestamp",
        "liquidations": "open_time",
        "long_short_ratio": "timestamp",
        "basis": "timestamp",
    }
    BUNDLE_SOURCE_SECTION_KEYS = {
        "ticker": ("spot",),
        "orderbook": ("orderbook",),
        "funding": ("funding",),
        "trade_flow": ("trade_flow_spot", "trade_flow_derivatives", "trade_flow"),
        "open_interest": ("open_interest",),
        "liquidations": ("liquidations",),
        "long_short_ratio": ("positioning",),
        "basis": ("basis",),
    }
    LIQUIDATION_FLOAT_FIELDS = (
        "long_liquidation_notional",
        "short_liquidation_notional",
        "total_liquidation_notional",
        "max_single_liquidation_notional",
    )
    LIQUIDATION_INT_FIELDS = (
        "long_liquidation_count",
        "short_liquidation_count",
    )
    LIQUIDATION_METRIC_FIELDS = (
        *LIQUIDATION_FLOAT_FIELDS,
        *LIQUIDATION_INT_FIELDS,
    )

    def __init__(
        self,
        client_manager: ExchangeClientManager | None = None,
        db: DBManager | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.EXCHANGE_DATA)
        self.client_manager = client_manager or ExchangeClientManager()
        self.market_info_collector = MarketInfoCollector(self.client_manager, self.db)
        self.kline_collector = KlineCollector(self.client_manager, self.db)
        self.ticker_collector = TickerCollector(self.client_manager, self.db)
        self.funding_collector = FundingRateCollector(self.client_manager, self.db)
        self.orderbook_collector = OrderBookCollector(self.client_manager, self.db)
        self.trades_collector = TradesCollector(self.client_manager, self.db)
        self.taker_flow_collector = TakerFlowCollector(self.trades_collector)
        self.open_interest_collector = OpenInterestCollector(self.client_manager, self.db)
        self.liquidations_collector = LiquidationsCollector(self.db)
        self.long_short_ratio_collector = LongShortRatioCollector(self.db)
        self.basis_collector = BasisCollector(self.db, funding_collector=self.funding_collector)

    def init_storage(self):
        self.db.init_exchange_data_tables()

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
    def _target_pair_count(target_symbols: list[str] | None = None) -> int:
        return len(target_symbols or TARGET_SYMBOLS) * len(TARGET_EXCHANGES)

    @staticmethod
    def _empty_symbol_entry(symbol: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "spot": [],
            "orderbook": [],
            "funding": [],
            "trade_flow": [],
            "trade_flow_spot": [],
            "trade_flow_derivatives": [],
            "trade_flow_scope": "missing",
            "open_interest": [],
            "liquidations": [],
            "positioning": [],
            "basis": [],
            "data_quality_flags": [],
            "quality_notes": [],
        }

    @classmethod
    def _build_symbols_map(
        cls,
        *,
        candidate_symbols: list[str],
        tickers: list[dict],
        trades: list[dict],
        orderbooks: list[dict],
        fundings: list[dict],
        open_interests: list[dict],
        liquidations: list[dict],
        positions: list[dict],
        basis_rows: list[dict],
    ) -> dict[str, dict[str, object]]:
        # v4.1.0: 预分配所有 symbol 条目，用直接索引替代 setdefault
        symbols_map = {
            symbol: cls._empty_symbol_entry(symbol)
            for symbol in candidate_symbols
        }
        for row in tickers:
            sym = str(row["symbol"])
            entry = symbols_map.get(sym)
            if entry is None:
                entry = cls._empty_symbol_entry(sym)
                symbols_map[sym] = entry
            entry["spot"].append(row)
        for row in trades:
            sym = str(row["symbol"])
            entry = symbols_map.get(sym)
            if entry is None:
                entry = cls._empty_symbol_entry(sym)
                symbols_map[sym] = entry
            market_type = str(row.get("market_type") or "").strip().lower()
            if market_type == "spot":
                entry["trade_flow_spot"].append(row)
            else:
                entry["trade_flow_derivatives"].append(row)
        for collection_name, rows in (
            ("orderbook", orderbooks),
            ("funding", fundings),
            ("open_interest", open_interests),
            ("liquidations", liquidations),
            ("positioning", positions),
            ("basis", basis_rows),
        ):
            for row in rows:
                sym = str(row["symbol"])
                entry = symbols_map.get(sym)
                if entry is None:
                    entry = cls._empty_symbol_entry(sym)
                    symbols_map[sym] = entry
                entry[collection_name].append(row)
        return symbols_map

    @staticmethod
    def _normalize_symbols(symbols: list[str] | None) -> list[str] | None:
        normalized = [
            str(symbol).strip()
            for symbol in (symbols or [])
            if str(symbol).strip()
        ]
        return normalized or None

    @staticmethod
    def _count_rows_by_source(
        row_groups: dict[str, list[dict]],
    ) -> dict[str, int]:
        counts = {
            str(source_name): len(rows)
            for source_name, rows in row_groups.items()
            if rows
        }
        return dict(
            sorted(
                counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    @classmethod
    def _latest_time_from_source_rows(
        cls,
        row_groups: dict[str, list[dict]],
    ) -> datetime | None:
        latest: datetime | None = None
        for source_name, rows in row_groups.items():
            time_field = cls.BUNDLE_SOURCE_TIME_FIELDS.get(str(source_name))
            if not time_field:
                continue
            for row in rows:
                row_dt = cls._to_datetime(row.get(time_field))
                if row_dt is None:
                    continue
                if latest is None or row_dt > latest:
                    latest = row_dt
        return latest

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
        raw_row_groups: dict[str, list[dict]],
        coverage_rows: list[dict],
    ) -> list[dict]:
        excluded: list[dict] = []
        for coverage_row in coverage_rows:
            source_name = str(coverage_row["source_name"])
            source_rows = list(raw_row_groups.get(source_name) or [])
            if not source_rows or coverage_row.get("is_ready_for_ai"):
                continue
            excluded.append(
                {
                    "source_name": source_name,
                    "excluded_reason": cls.AI_EXCLUDED_SOURCE_REASON,
                    "raw_row_count": len(source_rows),
                    "raw_symbol_count": len(
                        {
                            str(row.get("symbol") or "").strip()
                            for row in source_rows
                            if str(row.get("symbol") or "").strip()
                        }
                    ),
                    "raw_symbols": sorted(
                        {
                            str(row.get("symbol") or "").strip()
                            for row in source_rows
                            if str(row.get("symbol") or "").strip()
                        }
                    ),
                    "raw_exchange_count": len(
                        {
                            str(row.get("exchange") or "").strip().lower()
                            for row in source_rows
                            if str(row.get("exchange") or "").strip()
                        }
                    ),
                    "raw_latest_observation_time": (
                        cls._latest_time_from_source_rows({source_name: source_rows}).isoformat()
                        if cls._latest_time_from_source_rows({source_name: source_rows}) is not None
                        else None
                    ),
                    "semantic_scope": coverage_row.get("semantic_scope"),
                    "latest_pair_count": coverage_row.get("latest_pair_count"),
                    "latest_non_stale_pair_count": coverage_row.get(
                        "latest_non_stale_pair_count"
                    ),
                    "latest_non_stale_coverage_ratio": coverage_row.get(
                        "latest_non_stale_coverage_ratio"
                    ),
                    "latest_derivatives_pair_count": coverage_row.get(
                        "latest_derivatives_pair_count"
                    ),
                    "latest_derivatives_coverage_ratio": coverage_row.get(
                        "latest_derivatives_coverage_ratio"
                    ),
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    @staticmethod
    def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
        denominator = float(denominator or 0)
        if denominator <= 0:
            return 0.0
        return round(float(numerator or 0) / denominator, 4)

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _loads_json(value):
        if not value:
            return None
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _append_unique(values: list[str], value: str | None):
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    @staticmethod
    def _to_datetime(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @classmethod
    def _basis_diagnostics(cls, row: dict) -> dict:
        payload = cls._loads_json(row.get("raw_payload_json"))
        if not isinstance(payload, dict):
            return {}
        diagnostics = payload.get("diagnostics")
        return diagnostics if isinstance(diagnostics, dict) else {}

    @classmethod
    def _normalize_liquidation_metric_value(
        cls,
        field_name: str,
        value,
    ) -> float | int | None:
        if field_name in cls.LIQUIDATION_INT_FIELDS:
            if value is None or value == "":
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        return cls._safe_float(value)

    @classmethod
    def _liquidation_metrics_from_payload(
        cls,
        payload,
    ) -> dict[str, float | int | None] | None:
        if not isinstance(payload, dict):
            return None
        if not any(field in payload for field in cls.LIQUIDATION_METRIC_FIELDS):
            return None
        return {
            field: (
                cls._normalize_liquidation_metric_value(field, payload.get(field))
                if field in payload
                else None
            )
            for field in cls.LIQUIDATION_METRIC_FIELDS
        }

    @classmethod
    def _enrich_basis_row(cls, row: dict) -> dict:
        enriched = dict(row)
        diagnostics = cls._basis_diagnostics(enriched)
        enriched["ticker_timestamp"] = diagnostics.get("ticker_timestamp")
        enriched["ticker_timestamp_status"] = diagnostics.get("ticker_timestamp_status")
        enriched["component_timestamp_gap_seconds"] = diagnostics.get(
            "component_timestamp_gap_seconds"
        )
        enriched["component_timestamp_gap_status"] = diagnostics.get(
            "component_timestamp_gap_status"
        )
        enriched["max_component_timestamp_gap_seconds"] = diagnostics.get(
            "max_component_timestamp_gap_seconds"
        )
        enriched["next_funding_time_status"] = diagnostics.get("next_funding_time_status")
        enriched["annualization_status"] = diagnostics.get("annualization_status")
        enriched["hours_to_funding"] = diagnostics.get("hours_to_funding")
        return enriched

    @staticmethod
    def _ranked_counter_rows(counter: Counter, field_name: str) -> list[dict]:
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
    def _ticker_visibility_reason(cls, row: dict) -> str:
        last_price = cls._safe_float(row.get("last_price"))
        bid = cls._safe_float(row.get("bid"))
        ask = cls._safe_float(row.get("ask"))
        has_positive_last_price = last_price is not None and last_price > 0
        has_positive_bid_ask = (
            bid is not None
            and bid > 0
            and ask is not None
            and ask > 0
        )

        if has_positive_last_price and has_positive_bid_ask:
            return "ready_full_price_context"
        if has_positive_last_price:
            return "ready_last_price_only"
        if has_positive_bid_ask:
            return "ready_bid_ask_only"
        if last_price is not None or bid is not None or ask is not None:
            return "invalid_core_price"
        return "missing_core_price"

    @classmethod
    def _build_ticker_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._ticker_visibility_reason(row)
            is_row_level_visible = visibility_reason.startswith("ready")
            row["spot_visibility_reason"] = visibility_reason
            row["spot_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["spot_row_status"] = "ready" if row["spot_is_ai_visible"] else "raw_only"
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "full_price_context_count": int(reason_counter.get("ready_full_price_context", 0)),
            "last_price_only_count": int(reason_counter.get("ready_last_price_only", 0)),
            "bid_ask_only_count": int(reason_counter.get("ready_bid_ask_only", 0)),
            "missing_core_price_count": int(reason_counter.get("missing_core_price", 0)),
            "invalid_core_price_count": int(reason_counter.get("invalid_core_price", 0)),
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @classmethod
    def _orderbook_visibility_reason(cls, row: dict) -> str:
        best_bid = cls._safe_float(row.get("best_bid"))
        best_ask = cls._safe_float(row.get("best_ask"))
        bid_depth_notional = cls._safe_float(row.get("bid_depth_notional"))
        ask_depth_notional = cls._safe_float(row.get("ask_depth_notional"))
        has_positive_top_of_book = (
            best_bid is not None
            and best_bid > 0
            and best_ask is not None
            and best_ask > 0
        )
        has_positive_depth_context = (
            bid_depth_notional is not None
            and bid_depth_notional > 0
            and ask_depth_notional is not None
            and ask_depth_notional > 0
        )

        if has_positive_top_of_book and has_positive_depth_context:
            return "ready_full_depth_context"
        if has_positive_top_of_book:
            return "ready_top_of_book_only"
        if best_bid is not None or best_ask is not None:
            return "invalid_top_of_book"
        return "missing_top_of_book"

    @classmethod
    def _build_orderbook_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._orderbook_visibility_reason(row)
            is_row_level_visible = visibility_reason.startswith("ready")
            row["orderbook_visibility_reason"] = visibility_reason
            row["orderbook_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["orderbook_row_status"] = (
                "ready" if row["orderbook_is_ai_visible"] else "raw_only"
            )
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "full_depth_context_count": int(reason_counter.get("ready_full_depth_context", 0)),
            "top_of_book_only_count": int(reason_counter.get("ready_top_of_book_only", 0)),
            "missing_top_of_book_count": int(reason_counter.get("missing_top_of_book", 0)),
            "invalid_top_of_book_count": int(reason_counter.get("invalid_top_of_book", 0)),
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @classmethod
    def _basis_visibility_reason(cls, row: dict) -> str:
        if row.get("spot_price") in (None, 0) or row.get("basis_bps") is None:
            return "missing_basis_value"
        ticker_timestamp_status = str(row.get("ticker_timestamp_status") or "").strip()
        if ticker_timestamp_status in {"missing", "parse_error"}:
            return "missing_ticker_timestamp"
        if str(row.get("component_timestamp_gap_status") or "").strip() == "wide":
            return "component_time_gap_wide"
        return "ready"

    @classmethod
    def _build_basis_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._basis_visibility_reason(row)
            is_row_level_visible = visibility_reason == "ready"
            row["basis_visibility_reason"] = visibility_reason
            row["basis_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["basis_row_status"] = "ready" if row["basis_is_ai_visible"] else "raw_only"
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        annualization_unavailable_count = sum(
            1
            for row in raw_rows
            if str(row.get("annualization_status") or "") not in {
                "",
                "ok",
                "missing_basis_bps",
            }
        )
        missing_spot_price_count = sum(
            1
            for row in raw_rows
            if row.get("spot_price") in (None, 0)
        )
        missing_ticker_timestamp_count = sum(
            1
            for row in raw_rows
            if str(row.get("ticker_timestamp_status") or "").strip() in {"missing", "parse_error"}
        )
        wide_component_gap_count = sum(
            1
            for row in raw_rows
            if str(row.get("component_timestamp_gap_status") or "").strip() == "wide"
        )

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "missing_spot_price_count": missing_spot_price_count,
            "missing_ticker_timestamp_count": missing_ticker_timestamp_count,
            "wide_component_gap_count": wide_component_gap_count,
            "annualization_unavailable_count": annualization_unavailable_count,
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @classmethod
    def _open_interest_visibility_reason(cls, row: dict) -> str:
        if row.get("open_interest_usd") is None and row.get("open_interest_contracts") is None:
            return "missing_open_interest_value"
        return "ready"

    @classmethod
    def _build_open_interest_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._open_interest_visibility_reason(row)
            is_row_level_visible = visibility_reason == "ready"
            row["open_interest_visibility_reason"] = visibility_reason
            row["open_interest_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["open_interest_row_status"] = (
                "ready" if row["open_interest_is_ai_visible"] else "raw_only"
            )
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        missing_value_count = sum(
            1
            for row in raw_rows
            if cls._open_interest_visibility_reason(row) == "missing_open_interest_value"
        )

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "missing_value_count": missing_value_count,
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @classmethod
    def _positioning_visibility_reason(cls, row: dict) -> str:
        long_ratio = cls._safe_float(row.get("long_ratio"))
        short_ratio = cls._safe_float(row.get("short_ratio"))
        long_short_ratio = cls._safe_float(row.get("long_short_ratio"))
        top_trader_long_ratio = cls._safe_float(row.get("top_trader_long_ratio"))
        top_trader_short_ratio = cls._safe_float(row.get("top_trader_short_ratio"))
        has_any_metric = any(
            value is not None
            for value in (
                long_ratio,
                short_ratio,
                long_short_ratio,
                top_trader_long_ratio,
                top_trader_short_ratio,
            )
        )
        if not has_any_metric:
            return "missing_positioning_metrics"
        if (
            long_short_ratio is not None
            or (long_ratio is not None and short_ratio is not None)
            or (
                top_trader_long_ratio is not None
                and top_trader_short_ratio is not None
            )
        ):
            return "ready"
        if long_ratio is not None or short_ratio is not None:
            return "incomplete_accounts_metrics"
        if top_trader_long_ratio is not None or top_trader_short_ratio is not None:
            return "incomplete_top_trader_metrics"
        return "incomplete_positioning_metrics"

    @classmethod
    def _build_positioning_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._positioning_visibility_reason(row)
            is_row_level_visible = visibility_reason == "ready"
            row["positioning_visibility_reason"] = visibility_reason
            row["positioning_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["positioning_row_status"] = (
                "ready" if row["positioning_is_ai_visible"] else "raw_only"
            )
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        missing_metric_count = sum(
            1
            for row in raw_rows
            if cls._positioning_visibility_reason(row) == "missing_positioning_metrics"
        )
        incomplete_accounts_metric_count = sum(
            1
            for row in raw_rows
            if cls._positioning_visibility_reason(row) == "incomplete_accounts_metrics"
        )
        incomplete_top_trader_metric_count = sum(
            1
            for row in raw_rows
            if cls._positioning_visibility_reason(row) == "incomplete_top_trader_metrics"
        )
        incomplete_metric_count = sum(
            1
            for row in raw_rows
            if cls._positioning_visibility_reason(row) not in {"ready", "missing_positioning_metrics"}
        )

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "missing_metric_count": missing_metric_count,
            "incomplete_metric_count": incomplete_metric_count,
            "incomplete_accounts_metric_count": incomplete_accounts_metric_count,
            "incomplete_top_trader_metric_count": incomplete_top_trader_metric_count,
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @classmethod
    def _liquidations_visibility_reason(cls, row: dict) -> str:
        total_notional = cls._safe_float(row.get("total_liquidation_notional"))
        long_notional = cls._safe_float(row.get("long_liquidation_notional"))
        short_notional = cls._safe_float(row.get("short_liquidation_notional"))
        long_count = row.get("long_liquidation_count")
        short_count = row.get("short_liquidation_count")
        max_single = cls._safe_float(row.get("max_single_liquidation_notional"))

        if total_notional is not None:
            return "ready"
        if long_notional is not None and short_notional is not None:
            return "ready"
        if (
            long_notional is None
            and short_notional is None
            and long_count is None
            and short_count is None
            and max_single is None
        ):
            return "missing_liquidation_metrics"
        return "incomplete_liquidation_metrics"

    @classmethod
    def _build_liquidations_view(
        cls,
        rows: list[dict],
        *,
        allow_visible: bool,
    ) -> tuple[list[dict], list[dict], dict]:
        raw_rows: list[dict] = []
        candidate_visible_rows: list[dict] = []
        visible_rows: list[dict] = []
        reason_counter: Counter = Counter()
        raw_exchanges: set[str] = set()
        visible_exchanges: set[str] = set()
        excluded_exchanges: set[str] = set()

        for raw_row in rows or []:
            row = dict(raw_row)
            visibility_reason = cls._liquidations_visibility_reason(row)
            is_row_level_visible = visibility_reason == "ready"
            row["liquidations_visibility_reason"] = visibility_reason
            row["liquidations_is_ai_visible"] = bool(allow_visible and is_row_level_visible)
            row["liquidations_row_status"] = (
                "ready" if row["liquidations_is_ai_visible"] else "raw_only"
            )
            raw_rows.append(row)
            reason_counter[visibility_reason] += 1

            exchange_name = str(row.get("exchange") or "").strip().lower()
            if exchange_name:
                raw_exchanges.add(exchange_name)

            if is_row_level_visible:
                candidate_visible_rows.append(row)
                if exchange_name:
                    visible_exchanges.add(exchange_name)
                if allow_visible:
                    visible_rows.append(row)
                continue

            if exchange_name:
                excluded_exchanges.add(exchange_name)

        if allow_visible and visible_rows and len(visible_rows) == len(raw_rows):
            status = "ready"
        elif visible_rows:
            status = "partial"
        elif raw_rows:
            status = "raw_only"
        else:
            status = "missing"

        missing_metric_count = sum(
            1
            for row in raw_rows
            if cls._liquidations_visibility_reason(row) == "missing_liquidation_metrics"
        )
        incomplete_metric_count = sum(
            1
            for row in raw_rows
            if cls._liquidations_visibility_reason(row) == "incomplete_liquidation_metrics"
        )

        return visible_rows, raw_rows, {
            "status": status,
            "source_gate_applied": bool(not allow_visible),
            "raw_row_count": len(raw_rows),
            "row_level_visible_row_count": len(candidate_visible_rows),
            "visible_row_count": len(visible_rows),
            "excluded_row_count": len(raw_rows) - len(visible_rows),
            "raw_exchange_count": len(raw_exchanges),
            "visible_exchange_count": len(visible_exchanges) if allow_visible else 0,
            "excluded_exchange_count": len(excluded_exchanges),
            "raw_exchange_names": sorted(raw_exchanges),
            "visible_exchange_names": sorted(visible_exchanges) if allow_visible else [],
            "excluded_exchange_names": sorted(excluded_exchanges),
            "missing_metric_count": missing_metric_count,
            "incomplete_metric_count": incomplete_metric_count,
            "visibility_reasons": cls._ranked_counter_rows(
                reason_counter,
                "reason",
            ),
        }

    @staticmethod
    def _derivatives_core_alignment_specs() -> tuple[dict[str, object], ...]:
        return (
            {
                "key": "funding",
                "timestamp_field": "timestamp",
                "interval_seconds": max(60, int(SCHEDULER_CONFIG["funding_interval"])),
            },
            {
                "key": "open_interest",
                "timestamp_field": "timestamp",
                "interval_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval_seconds"]),
                ),
            },
            {
                "key": "basis",
                "timestamp_field": "timestamp",
                "interval_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["basis_interval_seconds"]),
                ),
            },
        )

    @classmethod
    def _build_derivatives_core_alignment_summary(
        cls,
        raw_symbol_entry: dict[str, object],
    ) -> dict[str, object]:
        specs = list(cls._derivatives_core_alignment_specs())
        latest_rows_by_section = {
            str(spec["key"]): cls._latest_rows_by_exchange(
                list(raw_symbol_entry.get(str(spec["key"])) or []),
                str(spec["timestamp_field"]),
            )
            for spec in specs
        }
        exchanges = sorted(
            {
                exchange_name
                for rows in latest_rows_by_section.values()
                for exchange_name in rows
            }
        )
        pair_defs: list[dict[str, object]] = []
        for index, left_spec in enumerate(specs):
            for right_spec in specs[index + 1 :]:
                pair_defs.append(
                    {
                        "pair": f"{left_spec['key']}_vs_{right_spec['key']}",
                        "left_key": str(left_spec["key"]),
                        "right_key": str(right_spec["key"]),
                        "threshold_seconds": max(
                            int(left_spec["interval_seconds"]),
                            int(right_spec["interval_seconds"]),
                        ),
                    }
                )

        pair_aggregates = {
            str(pair_def["pair"]): {
                "pair": str(pair_def["pair"]),
                "threshold_seconds": int(pair_def["threshold_seconds"]),
                "comparable_exchange_count": 0,
                "wide_exchange_count": 0,
                "max_gap_seconds": None,
            }
            for pair_def in pair_defs
        }
        exchange_statuses: list[dict[str, object]] = []
        max_gap_seconds: float | None = None

        for exchange_name in exchanges:
            component_timestamps: dict[str, str | None] = {}
            component_rows_present: dict[str, bool] = {}
            component_datetimes: dict[str, datetime | None] = {}
            pair_results: list[dict[str, object]] = []

            for spec in specs:
                section_key = str(spec["key"])
                row = latest_rows_by_section[section_key].get(exchange_name)
                dt = (
                    cls._to_datetime(row.get(str(spec["timestamp_field"])))
                    if row is not None
                    else None
                )
                component_datetimes[section_key] = dt
                component_rows_present[section_key] = row is not None
                component_timestamps[section_key] = dt.isoformat() if dt is not None else None

            for pair_def in pair_defs:
                left_dt = component_datetimes[str(pair_def["left_key"])]
                right_dt = component_datetimes[str(pair_def["right_key"])]
                if left_dt is None or right_dt is None:
                    continue
                gap_seconds = round(abs((left_dt - right_dt).total_seconds()), 3)
                status = (
                    "wide"
                    if gap_seconds > float(pair_def["threshold_seconds"])
                    else "ok"
                )
                pair_results.append(
                    {
                        "pair": str(pair_def["pair"]),
                        "gap_seconds": gap_seconds,
                        "threshold_seconds": int(pair_def["threshold_seconds"]),
                        "status": status,
                    }
                )
                aggregate = pair_aggregates[str(pair_def["pair"])]
                aggregate["comparable_exchange_count"] += 1
                if status == "wide":
                    aggregate["wide_exchange_count"] += 1
                current_max_gap = aggregate["max_gap_seconds"]
                aggregate["max_gap_seconds"] = (
                    gap_seconds
                    if current_max_gap is None
                    else max(float(current_max_gap), gap_seconds)
                )
                max_gap_seconds = (
                    gap_seconds
                    if max_gap_seconds is None
                    else max(float(max_gap_seconds), gap_seconds)
                )

            component_count = sum(1 for dt in component_datetimes.values() if dt is not None)
            if not pair_results:
                exchange_status = "insufficient"
            elif any(result["status"] == "wide" for result in pair_results):
                exchange_status = "wide"
            elif component_count == len(specs):
                exchange_status = "aligned"
            else:
                exchange_status = "partial"

            exchange_statuses.append(
                {
                    "exchange": exchange_name,
                    "status": exchange_status,
                    "component_count": component_count,
                    "present_sections": [
                        key
                        for key, present in component_rows_present.items()
                        if present
                    ],
                    "missing_sections": [
                        key
                        for key, present in component_rows_present.items()
                        if not present
                    ],
                    "component_timestamps": component_timestamps,
                    "pair_results": pair_results,
                    "max_gap_seconds": (
                        max(
                            float(result["gap_seconds"])
                            for result in pair_results
                        )
                        if pair_results
                        else None
                    ),
                }
            )

        status_counter = Counter(
            str(item["status"])
            for item in exchange_statuses
        )
        raw_exchange_count = len(exchanges)
        aligned_exchange_names = [
            str(item["exchange"])
            for item in exchange_statuses
            if item["status"] == "aligned"
        ]
        wide_exchange_names = [
            str(item["exchange"])
            for item in exchange_statuses
            if item["status"] == "wide"
        ]
        partial_exchange_names = [
            str(item["exchange"])
            for item in exchange_statuses
            if item["status"] == "partial"
        ]
        insufficient_exchange_names = [
            str(item["exchange"])
            for item in exchange_statuses
            if item["status"] == "insufficient"
        ]
        comparable_exchange_count = (
            int(status_counter.get("aligned", 0))
            + int(status_counter.get("partial", 0))
            + int(status_counter.get("wide", 0))
        )

        if raw_exchange_count == 0:
            status = "missing"
        elif int(status_counter.get("wide", 0)) > 0:
            status = "wide"
        elif int(status_counter.get("aligned", 0)) == raw_exchange_count:
            status = "ready"
        elif comparable_exchange_count > 0:
            status = "partial"
        else:
            status = "insufficient"

        return {
            "status": status,
            "sections": [str(spec["key"]) for spec in specs],
            "raw_exchange_count": raw_exchange_count,
            "comparable_exchange_count": comparable_exchange_count,
            "aligned_exchange_count": int(status_counter.get("aligned", 0)),
            "partial_exchange_count": int(status_counter.get("partial", 0)),
            "wide_exchange_count": int(status_counter.get("wide", 0)),
            "insufficient_exchange_count": int(status_counter.get("insufficient", 0)),
            "aligned_exchange_names": aligned_exchange_names,
            "partial_exchange_names": partial_exchange_names,
            "wide_exchange_names": wide_exchange_names,
            "insufficient_exchange_names": insufficient_exchange_names,
            "max_gap_seconds": max_gap_seconds,
            "pair_summaries": list(pair_aggregates.values()),
            "exchange_statuses": exchange_statuses,
        }

    @classmethod
    def _age_seconds(cls, now: datetime, value) -> float | None:
        dt = cls._to_datetime(value)
        if dt is None:
            return None
        return round(max((now - dt).total_seconds(), 0.0), 3)

    @classmethod
    def _latest_rows_by_exchange(
        cls,
        rows: list[dict],
        timestamp_field: str,
    ) -> dict[str, dict]:
        latest_rows: dict[str, dict] = {}
        for row in rows:
            exchange = str(row.get("exchange") or "").strip().lower()
            if not exchange:
                continue
            row_dt = cls._to_datetime(row.get(timestamp_field))
            current = latest_rows.get(exchange)
            if current is None:
                latest_rows[exchange] = row
                continue
            current_dt = cls._to_datetime(current.get(timestamp_field))
            if row_dt and current_dt:
                if row_dt >= current_dt:
                    latest_rows[exchange] = row
                continue
            if row_dt and not current_dt:
                latest_rows[exchange] = row
        return latest_rows

    @classmethod
    def _numeric_values_from_rows(
        cls,
        rows: list[dict],
        field_name: str,
    ) -> list[float]:
        values: list[float] = []
        for row in rows:
            value = cls._safe_float(row.get(field_name))
            if value is not None:
                values.append(value)
        return values

    @classmethod
    def _range_bps_from_rows(
        cls,
        rows: list[dict],
        field_name: str,
    ) -> float | None:
        values = cls._numeric_values_from_rows(rows, field_name)
        if len(values) < 2:
            return None
        mean_value = sum(values) / len(values)
        if mean_value == 0:
            return None
        return round(((max(values) - min(values)) / mean_value) * 10000, 4)

    @classmethod
    def _absolute_range_from_rows(
        cls,
        rows: list[dict],
        field_name: str,
    ) -> float | None:
        values = cls._numeric_values_from_rows(rows, field_name)
        if len(values) < 2:
            return None
        return round(max(values) - min(values), 4)

    @classmethod
    def _build_section_status(
        cls,
        *,
        rows: list[dict],
        label: str,
        timestamp_field: str,
        expected_exchanges: list[str],
        configured: bool,
        stale_after_seconds: int,
        now: datetime,
    ) -> dict[str, object]:
        latest_rows_by_exchange = cls._latest_rows_by_exchange(rows, timestamp_field)
        latest_rows = list(latest_rows_by_exchange.values())
        observed_exchanges = sorted(latest_rows_by_exchange)
        missing_exchanges = [
            exchange
            for exchange in expected_exchanges
            if exchange not in latest_rows_by_exchange
        ]
        timestamps = [
            dt
            for dt in (
                cls._to_datetime(row.get(timestamp_field))
                for row in latest_rows
            )
            if dt is not None
        ]
        freshest_dt = max(timestamps) if timestamps else None
        oldest_dt = min(timestamps) if timestamps else None
        stale_exchange_count = 0
        for row in latest_rows:
            age_seconds = cls._age_seconds(now, row.get(timestamp_field))
            if age_seconds is not None and age_seconds > stale_after_seconds:
                stale_exchange_count += 1

        return {
            "label": label,
            "configured": configured,
            "row_count": len(rows),
            "expected_exchange_count": len(expected_exchanges),
            "exchange_count": len(observed_exchanges),
            "coverage_ratio": cls._safe_ratio(
                len(observed_exchanges),
                len(expected_exchanges),
            ),
            "observed_exchanges": observed_exchanges,
            "missing_exchanges": missing_exchanges,
            "freshest_timestamp": freshest_dt.isoformat() if freshest_dt else None,
            "oldest_timestamp": oldest_dt.isoformat() if oldest_dt else None,
            "freshest_age_seconds": cls._age_seconds(now, freshest_dt),
            "oldest_age_seconds": cls._age_seconds(now, oldest_dt),
            "timestamp_spread_seconds": (
                round((freshest_dt - oldest_dt).total_seconds(), 3)
                if freshest_dt and oldest_dt and freshest_dt != oldest_dt
                else None
            ),
            "stale_after_seconds": stale_after_seconds,
            "stale_exchange_count": stale_exchange_count,
            "all_rows_stale": bool(latest_rows) and stale_exchange_count == len(latest_rows),
        }

    @staticmethod
    def _build_symbol_exchange_map(rows: list[dict]) -> dict[str, set[str]]:
        exchanges_by_symbol: dict[str, set[str]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            exchange = str(row.get("exchange") or "").strip().lower()
            if not symbol or not exchange or exchange not in TARGET_EXCHANGES:
                continue
            exchanges_by_symbol.setdefault(symbol, set()).add(exchange)
        return exchanges_by_symbol

    @classmethod
    def _build_symbol_coverage_summary(
        cls,
        exchanges_by_symbol: dict[str, set[str]],
        target_symbols: list[str] | None = None,
    ) -> dict[str, object]:
        candidate_symbols = list(target_symbols or TARGET_SYMBOLS)
        target_exchange_count = len(TARGET_EXCHANGES)
        total_observed_pairs = 0
        full_coverage_symbol_count = 0
        undercovered_symbol_count = 0
        missing_symbol_count = 0
        coverage_gaps: list[dict[str, object]] = []

        for symbol in candidate_symbols:
            observed_exchanges = sorted(exchanges_by_symbol.get(symbol, set()))
            missing_exchanges = [
                exchange
                for exchange in TARGET_EXCHANGES
                if exchange not in observed_exchanges
            ]
            observed_exchange_count = len(observed_exchanges)
            total_observed_pairs += observed_exchange_count

            if observed_exchange_count == target_exchange_count:
                full_coverage_symbol_count += 1
            elif observed_exchange_count == 0:
                missing_symbol_count += 1
            else:
                undercovered_symbol_count += 1

            if missing_exchanges:
                coverage_gaps.append(
                    {
                        "symbol": symbol,
                        "observed_exchange_count": observed_exchange_count,
                        "coverage_ratio": cls._safe_ratio(
                            observed_exchange_count,
                            target_exchange_count,
                        ),
                        "observed_exchanges": observed_exchanges,
                        "missing_exchanges": missing_exchanges,
                    }
                )

        expected_pair_count = len(candidate_symbols) * target_exchange_count
        return {
            "coverage_ratio": cls._safe_ratio(total_observed_pairs, expected_pair_count),
            "observed_pair_count": total_observed_pairs,
            "missing_pair_count": max(expected_pair_count - total_observed_pairs, 0),
            "full_coverage_symbol_count": full_coverage_symbol_count,
            "undercovered_symbol_count": undercovered_symbol_count,
            "missing_symbol_count": missing_symbol_count,
            "coverage_gaps": coverage_gaps,
        }

    @staticmethod
    def _coverage_gap_note(coverage_gaps: list[dict[str, object]]) -> str | None:
        if not coverage_gaps:
            return None
        samples = []
        for gap in coverage_gaps[:2]:
            missing_exchanges = ",".join(gap["missing_exchanges"])
            samples.append(f"{gap['symbol']} 缺 {missing_exchanges}")
        joined = "；".join(samples)
        return (
            f"例如 {joined}。"
            if joined
            else None
        )

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        requested_symbols: list[str] | None = None,
    ) -> dict[str, object]:
        scope_kind = "filtered" if requested_symbols else "default"
        configured_symbols = list(requested_symbols or TARGET_SYMBOLS)
        configured_exchanges = list(TARGET_EXCHANGES)
        asset_count = len(configured_symbols)
        exchange_count = len(configured_exchanges)
        # Keep the aspirational 4-exchange floor for multi-venue defaults.
        # Only single-venue (geo-limited) deploys scale the floor down so they
        # are not permanently marked "limited".
        if exchange_count <= 1:
            min_exchange_count = max(exchange_count, 1)
        else:
            min_exchange_count = cls.MINIMUM_EXCHANGE_COUNT_FOR_MARKET_BREADTH
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = (
                "sufficient"
                if (
                    asset_count >= cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH
                    and exchange_count >= min_exchange_count
                )
                else "limited"
            )
        return {
            "scope_kind": scope_kind,
            "tracked_symbols": configured_symbols,
            "tracked_exchanges": configured_exchanges,
            "asset_count": asset_count,
            "exchange_count": exchange_count,
            "minimum_asset_count_for_market_breadth": cls.MINIMUM_ASSET_COUNT_FOR_MARKET_BREADTH,
            "minimum_exchange_count_for_market_breadth": min_exchange_count,
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    def _is_source_ready_for_ai(
        self,
        *,
        source_name: str,
        health_status: str,
        latest_non_stale_pair_count: int,
        latest_non_stale_coverage_ratio: float,
        data_quality_flags: list[str],
        latest_derivatives_pair_count: int = 0,
        latest_derivatives_coverage_ratio: float = 0.0,
    ) -> bool:
        if health_status != "ready":
            return False
        if int(latest_non_stale_pair_count or 0) <= 0:
            return False
        if float(latest_non_stale_coverage_ratio or 0.0) < 1.0:
            return False

        critical_flags = set(self.AI_CRITICAL_SOURCE_FLAGS)
        if source_name == "trade_flow":
            critical_flags.update(self.AI_CRITICAL_TRADE_FLOW_FLAGS)
            if int(latest_derivatives_pair_count or 0) <= 0:
                return False
            if float(latest_derivatives_coverage_ratio or 0.0) < 1.0:
                return False

        return not critical_flags.intersection(set(data_quality_flags))

    def _load_table_rows(
        self,
        *,
        table_name: str,
        params: tuple | list = (),
        where_sql: str = "",
        extra_columns: tuple[str, ...] = (),
    ) -> list[dict]:
        selected_columns = list(dict.fromkeys(["symbol", "exchange", *extra_columns]))
        rows = self.db.fetch_all(
            f"SELECT {', '.join(selected_columns)} FROM {table_name}{where_sql}",
            tuple(params),
        )
        return [dict(row) for row in rows]

    @classmethod
    def _build_latest_pair_times_from_rows(
        cls,
        rows: list[dict],
        time_column: str,
    ) -> list[dict]:
        latest_rows_by_pair: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            exchange = str(row.get("exchange") or "").strip().lower()
            if not symbol or not exchange:
                continue
            pair_key = (symbol, exchange)
            row_dt = cls._to_datetime(row.get(time_column))
            current = latest_rows_by_pair.get(pair_key)
            if current is None:
                latest_rows_by_pair[pair_key] = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "latest_pair_time": row.get(time_column),
                }
                continue
            current_dt = cls._to_datetime(current.get("latest_pair_time"))
            if row_dt and current_dt:
                if row_dt >= current_dt:
                    latest_rows_by_pair[pair_key] = {
                        "symbol": symbol,
                        "exchange": exchange,
                        "latest_pair_time": row.get(time_column),
                    }
                continue
            if row_dt and not current_dt:
                latest_rows_by_pair[pair_key] = {
                    "symbol": symbol,
                    "exchange": exchange,
                    "latest_pair_time": row.get(time_column),
                }
        return list(latest_rows_by_pair.values())

    @classmethod
    def _build_source_meta_from_rows(
        cls,
        rows: list[dict],
        time_column: str,
    ) -> dict[str, object]:
        symbols: set[str] = set()
        exchanges: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        latest_observation_dt: datetime | None = None

        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            exchange = str(row.get("exchange") or "").strip().lower()
            if symbol:
                symbols.add(symbol)
            if exchange:
                exchanges.add(exchange)
            if symbol and exchange:
                pairs.add((symbol, exchange))
            row_dt = cls._to_datetime(row.get(time_column))
            if row_dt is not None and (
                latest_observation_dt is None or row_dt > latest_observation_dt
            ):
                latest_observation_dt = row_dt

        return {
            "latest_point_count": len(rows),
            "latest_symbol_count": len(symbols),
            "latest_exchange_count": len(exchanges),
            "latest_pair_count": len(pairs),
            "latest_observation_time": (
                latest_observation_dt.isoformat()
                if latest_observation_dt is not None
                else None
            ),
        }

    def _run_collection_job(
        self,
        *,
        source_name: str,
        job_name: str,
        func,
        metadata: dict[str, object] | None = None,
    ):
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
            logger.error(f"交易所来源采集失败 [{source_name}]: {message}")
        finally:
            finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.db.record_collection_run(
                module_name="exchange_data",
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

    def _build_coverage_specs(
        self,
        target_symbols: list[str] | None = None,
    ) -> list[dict[str, object]]:
        target_pair_count = self._target_pair_count(target_symbols)
        specs: list[dict[str, object]] = [
            {
                "source_name": "market_info",
                "name": "交易对静态信息",
                "table_name": "market_info",
                "time_column": "updated_at",
                "interval_seconds": SCHEDULER_CONFIG["market_info_interval"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
            {
                "source_name": "ticker",
                "name": "实时行情",
                "table_name": "latest_tickers",
                "time_column": "timestamp",
                "interval_seconds": SCHEDULER_CONFIG["ticker_interval"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
            {
                "source_name": "funding",
                "name": "资金费率",
                "table_name": "latest_funding_rates",
                "time_column": "timestamp",
                "interval_seconds": SCHEDULER_CONFIG["funding_interval"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
            {
                "source_name": "orderbook",
                "name": "盘口深度",
                "table_name": "latest_orderbook_snapshots",
                "time_column": "timestamp",
                "interval_seconds": SCHEDULER_CONFIG["orderbook_interval"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
            {
                "source_name": "trade_flow",
                "name": "成交流",
                "table_name": "latest_trade_flow_bars",
                "time_column": "open_time",
                "interval_seconds": EXCHANGE_DERIVATIVES_CONFIG["trade_flow_interval_seconds"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [
                    "trade_flow 会按 market_type 区分现货与合约成交流。",
                    "当 semantic_scope 显示为 spot_only 时，说明衍生品逐笔成交流仍然缺失。",
                ],
            },
            {
                "source_name": "open_interest",
                "name": "持仓量",
                "table_name": "latest_open_interest_snapshots",
                "time_column": "timestamp",
                "interval_seconds": EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval_seconds"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
            {
                "source_name": "liquidations",
                "name": "清算聚合",
                "table_name": "latest_liquidation_bars",
                "time_column": "open_time",
                "interval_seconds": EXCHANGE_DERIVATIVES_CONFIG["liquidation_interval_seconds"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": bool(EXCHANGE_DERIVATIVES_CONFIG["liquidation_url"]),
                "quality_notes": [],
            },
            {
                "source_name": "long_short_ratio",
                "name": "多空比",
                "table_name": "latest_positioning_snapshots",
                "time_column": "timestamp",
                "interval_seconds": EXCHANGE_DERIVATIVES_CONFIG["positioning_interval_seconds"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": bool(EXCHANGE_DERIVATIVES_CONFIG["long_short_ratio_url"]),
                "quality_notes": [],
            },
            {
                "source_name": "basis",
                "name": "Basis",
                "table_name": "latest_basis_snapshots",
                "time_column": "timestamp",
                "interval_seconds": EXCHANGE_DERIVATIVES_CONFIG["basis_interval_seconds"],
                "expected_pair_count": target_pair_count,
                "configuration_ready": True,
                "quality_notes": [],
            },
        ]
        for timeframe in KLINE_TIMEFRAMES:
            specs.append(
                {
                    "source_name": f"kline_{timeframe}",
                    "name": f"K线[{timeframe}]",
                    "table_name": "klines",
                    "time_column": "open_time",
                    "interval_seconds": self.kline_collector.TIMEFRAME_INTERVAL_SECONDS.get(
                        timeframe,
                        SCHEDULER_CONFIG["kline_interval"],
                    ),
                    "expected_pair_count": target_pair_count,
                    "configuration_ready": True,
                    "where_sql": "timeframe = ?",
                    "params": (timeframe,),
                    "quality_notes": [],
                }
            )
        return specs

    def bootstrap(self, include_backfill: bool = True):
        """模块首次启动时执行的低频初始化采集。"""
        self._run_collection_job(
            source_name="market_info",
            job_name="market_info_bootstrap",
            func=lambda: self.market_info_collector.collect(force=True),
            metadata={"mode": "bootstrap"},
        )
        if include_backfill:
            self.kline_collector.backfill_all()

    def _collect_orderbooks_for_symbols(self, symbols: list[str]) -> list:
        """采集指定符号列表的深度数据并保存。用于分层调度。"""
        orderbooks = self.orderbook_collector.fetch_all_orderbooks(symbols=symbols)
        if orderbooks:
            self.orderbook_collector.save_to_db(orderbooks)
        return orderbooks

    def collect_once(self, include_backfill: bool = False):
        """执行一次完整采集，用于手动触发或本地联调。"""
        self._run_collection_job(
            source_name="market_info",
            job_name="market_info_once",
            func=lambda: self.market_info_collector.collect(force=True),
            metadata={"mode": "once", "force": True},
        )
        if include_backfill:
            self.kline_collector.backfill_all()
        else:
            for timeframe in KLINE_TIMEFRAMES:
                self._run_collection_job(
                    source_name=f"kline_{timeframe}",
                    job_name="kline_once",
                    func=lambda timeframe=timeframe: self.kline_collector.collect_timeframe(timeframe),
                    metadata={"mode": "once", "timeframe": timeframe},
                )
        self._run_collection_job(
            source_name="ticker",
            job_name="ticker_once",
            func=self.ticker_collector.collect,
            metadata={"mode": "once"},
        )
        self._run_collection_job(
            source_name="funding",
            job_name="funding_once",
            func=self.funding_collector.collect,
            metadata={"mode": "once"},
        )
        self._run_collection_job(
            source_name="orderbook",
            job_name="orderbook_once",
            func=self.orderbook_collector.collect,
            metadata={"mode": "once"},
        )
        self.collect_derivatives_once()

    async def collect_once_async(self, include_backfill: bool = False):
        """异步执行一次完整采集 — 利用 asyncio 并发调度独立的采集任务。

        适用于 AsyncIOScheduler 模式，将互相独立的采集任务并发执行。
        """
        import asyncio

        loop = asyncio.get_event_loop()

        # market_info 必须先完成（后续采集依赖交易对信息）
        await loop.run_in_executor(
            None,
            lambda: self._run_collection_job(
                source_name="market_info",
                job_name="market_info_async",
                func=lambda: self.market_info_collector.collect(force=True),
                metadata={"mode": "async", "force": True},
            ),
        )

        # kline 采集
        if include_backfill:
            await loop.run_in_executor(None, self.kline_collector.backfill_all)
        else:
            kline_tasks = [
                loop.run_in_executor(
                    None,
                    lambda tf=tf: self._run_collection_job(
                        source_name=f"kline_{tf}",
                        job_name="kline_async",
                        func=lambda tf=tf: self.kline_collector.collect_timeframe(tf),
                        metadata={"mode": "async", "timeframe": tf},
                    ),
                )
                for tf in KLINE_TIMEFRAMES
            ]
            await asyncio.gather(*kline_tasks, return_exceptions=True)

        # 独立采集任务并发执行
        independent_tasks = [
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="ticker",
                    job_name="ticker_async",
                    func=self.ticker_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="funding",
                    job_name="funding_async",
                    func=self.funding_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="orderbook",
                    job_name="orderbook_async",
                    func=self.orderbook_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
        ]
        await asyncio.gather(*independent_tasks, return_exceptions=True)

        # 衍生品采集并发
        derivatives_tasks = [
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="trade_flow",
                    job_name="trade_flow_async",
                    func=self.trades_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="open_interest",
                    job_name="open_interest_async",
                    func=self.open_interest_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="liquidations",
                    job_name="liquidations_async",
                    func=self.liquidations_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="long_short_ratio",
                    job_name="long_short_ratio_async",
                    func=self.long_short_ratio_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
            loop.run_in_executor(
                None,
                lambda: self._run_collection_job(
                    source_name="basis",
                    job_name="basis_async",
                    func=self.basis_collector.collect,
                    metadata={"mode": "async"},
                ),
            ),
        ]
        await asyncio.gather(*derivatives_tasks, return_exceptions=True)

    def collect_derivatives_once(self):
        """执行一次衍生品结构采集。"""
        self._run_collection_job(
            source_name="trade_flow",
            job_name="trade_flow_once",
            func=self.trades_collector.collect,
            metadata={"mode": "derivatives_once"},
        )
        self._run_collection_job(
            source_name="open_interest",
            job_name="open_interest_once",
            func=self.open_interest_collector.collect,
            metadata={"mode": "derivatives_once"},
        )
        self._run_collection_job(
            source_name="liquidations",
            job_name="liquidations_once",
            func=self.liquidations_collector.collect,
            metadata={"mode": "derivatives_once"},
        )
        self._run_collection_job(
            source_name="long_short_ratio",
            job_name="long_short_ratio_once",
            func=self.long_short_ratio_collector.collect,
            metadata={"mode": "derivatives_once"},
        )
        self._run_collection_job(
            source_name="basis",
            job_name="basis_once",
            func=self.basis_collector.collect,
            metadata={"mode": "derivatives_once"},
        )

    def cleanup_historical_data(self) -> dict[str, int]:
        """清理高频快照表中过旧的数据，控制数据库膨胀速度。"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cleanup_plan = {
            "tickers": ("timestamp", EXCHANGE_DATA_RETENTION.get("ticker_days", 0)),
            "orderbook_snapshots": ("timestamp", EXCHANGE_DATA_RETENTION.get("orderbook_days", 0)),
            "funding_rates": ("timestamp", EXCHANGE_DATA_RETENTION.get("funding_days", 0)),
            "trade_flow_bars": ("open_time", EXCHANGE_DATA_RETENTION.get("trade_flow_days", 0)),
            "open_interest_snapshots": (
                "timestamp",
                EXCHANGE_DATA_RETENTION.get("open_interest_days", 0),
            ),
            "basis_snapshots": ("timestamp", EXCHANGE_DATA_RETENTION.get("basis_days", 0)),
            "liquidation_bars": ("open_time", EXCHANGE_DATA_RETENTION.get("liquidation_days", 0)),
            "positioning_snapshots": (
                "timestamp",
                EXCHANGE_DATA_RETENTION.get("positioning_days", 0),
            ),
        }
        deleted_counts: dict[str, int] = {}

        for table_name, (time_column, retention_days) in cleanup_plan.items():
            if retention_days <= 0:
                deleted_counts[table_name] = 0
                logger.info(f"跳过历史清理 [{table_name}] retention_days={retention_days}")
                continue

            cutoff = now - timedelta(days=retention_days)
            cursor = self.db.execute(
                f"DELETE FROM {table_name} WHERE {time_column} < ?",
                (cutoff.isoformat(),),
            )
            deleted_counts[table_name] = max(cursor.rowcount, 0)
            logger.info(
                f"历史数据清理完成 [{table_name}] 保留最近{retention_days}天, "
                f"删除 {deleted_counts[table_name]} 条"
            )

        self.db.commit()
        return deleted_counts

    def _repair_liquidation_table_from_raw_payload(self, table_name: str) -> int:
        rows = self.db.fetch_all(
            f"""
            SELECT
                id,
                {", ".join(self.LIQUIDATION_METRIC_FIELDS)},
                raw_payload_json
            FROM {table_name}
            WHERE raw_payload_json IS NOT NULL
              AND TRIM(raw_payload_json) <> ''
            """
        )
        updates: list[tuple] = []
        for row in rows:
            payload_metrics = self._liquidation_metrics_from_payload(
                self._loads_json(row["raw_payload_json"])
            )
            if payload_metrics is None:
                continue
            current_metrics = {
                field: row[field]
                for field in self.LIQUIDATION_METRIC_FIELDS
            }
            if all(
                current_metrics[field] == payload_metrics[field]
                for field in self.LIQUIDATION_METRIC_FIELDS
            ):
                continue
            updates.append(
                tuple(payload_metrics[field] for field in self.LIQUIDATION_METRIC_FIELDS)
                + (int(row["id"]),)
            )

        if not updates:
            return 0

        self.db.execute_many(
            f"""
            UPDATE {table_name}
            SET
                long_liquidation_notional = ?,
                short_liquidation_notional = ?,
                total_liquidation_notional = ?,
                max_single_liquidation_notional = ?,
                long_liquidation_count = ?,
                short_liquidation_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            updates,
        )
        self.db.commit()
        logger.info(
            f"已基于 raw_payload_json 修复清算字段语义 [{table_name}] {len(updates)} 条"
        )
        return len(updates)

    def repair_liquidation_semantics_from_raw_payload(self) -> dict[str, int]:
        """把旧版 collector 写成 0 的未知清算字段，按 raw_payload_json 恢复为真实语义。"""
        return self._run_collection_job(
            source_name="liquidations",
            job_name="liquidations_repair",
            func=lambda: {
                "history_rows_repaired": self._repair_liquidation_table_from_raw_payload(
                    "liquidation_bars"
                ),
                "latest_rows_repaired": self._repair_liquidation_table_from_raw_payload(
                    "latest_liquidation_bars"
                ),
            },
            metadata={
                "mode": "maintenance",
                "repair": "restore_liquidation_metrics_from_raw_payload",
            },
        )

    def backfill_funding_history(self, days: int = 30):
        """回填历史资金费率，补齐衍生品上下文样本。"""
        return self.funding_collector.backfill_all_history(days=days)

    def collect_market_context_burst(
        self,
        cycles: int = 120,
        interval_seconds: float = 3.0,
        funding_every: int = 20,
        funding_history_days: int = 0,
    ):
        """
        高频积累 ticker / funding / orderbook 样本。

        ticker 和 orderbook 无法像K线一样直接历史回填，开发阶段通过短周期循环采样快速积累上下文样本。
        """
        if funding_history_days > 0:
            self.backfill_funding_history(days=funding_history_days)

        for cycle in range(1, cycles + 1):
            logger.info(f"开始市场上下文采样，第 {cycle}/{cycles} 轮")
            self.ticker_collector.collect()
            self.orderbook_collector.collect()
            self.trades_collector.collect()

            if cycle == 1 or (funding_every > 0 and cycle % funding_every == 0):
                self.funding_collector.collect()
                self.open_interest_collector.collect()
                self.basis_collector.collect()

            if cycle < cycles and interval_seconds > 0:
                time.sleep(interval_seconds)

        logger.info("市场上下文高频采样完成")

    def load_latest_market_context_bundle(
        self,
        symbols: list[str] | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized_symbols = self._normalize_symbols(symbols)
        configured_universe_summary = self._build_configured_universe_summary(
            requested_symbols=normalized_symbols,
        )
        symbol_filter_sql = ""
        params: list[str] = []
        if normalized_symbols:
            placeholders = ",".join("?" for _ in normalized_symbols)
            symbol_filter_sql = f" WHERE symbol IN ({placeholders})"
            params.extend(normalized_symbols)

        tickers = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_tickers{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        orderbooks = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_orderbook_snapshots{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        fundings = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_funding_rates{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        trades = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_trade_flow_bars{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        open_interests = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_open_interest_snapshots{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        liquidations = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_liquidation_bars{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        positions = [
            dict(row)
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_positioning_snapshots{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        basis_rows = [
            self._enrich_basis_row(dict(row))
            for row in self.db.fetch_all(
                f"SELECT * FROM latest_basis_snapshots{symbol_filter_sql} ORDER BY symbol, exchange",
                tuple(params),
            )
        ]
        raw_row_groups = {
            "ticker": tickers,
            "orderbook": orderbooks,
            "funding": fundings,
            "trade_flow": trades,
            "open_interest": open_interests,
            "liquidations": liquidations,
            "long_short_ratio": positions,
            "basis": basis_rows,
        }
        coverage = self.load_source_coverage(symbols=normalized_symbols)
        coverage_rows = coverage.get("sources", [])
        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        source_visible_names = {
            str(row["source_name"])
            for row in coverage_rows
            if bool(row.get("configuration_ready"))
            and str(row.get("health_status") or "").strip().lower() == "ready"
        }
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_row_groups=raw_row_groups,
            coverage_rows=[
                row
                for row in coverage_rows
                if str(row["source_name"]) not in source_visible_names
            ],
        )
        not_ready_for_ai_source_names = [
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("is_ready_for_ai")
        ]

        tickers, raw_ticker_rows, spot_quality_summary = self._build_ticker_view(
            list(raw_row_groups["ticker"]),
            allow_visible="ticker" in source_visible_names,
        )
        orderbooks, raw_orderbook_rows, orderbook_quality_summary = (
            self._build_orderbook_view(
                list(raw_row_groups["orderbook"]),
                allow_visible="orderbook" in source_visible_names,
            )
        )
        fundings = list(raw_row_groups["funding"]) if "funding" in source_visible_names else []
        trades = list(raw_row_groups["trade_flow"]) if "trade_flow" in source_visible_names else []
        open_interests, raw_open_interest_rows, open_interest_quality_summary = (
            self._build_open_interest_view(
                list(raw_row_groups["open_interest"]),
                allow_visible="open_interest" in source_visible_names,
            )
        )
        liquidations, raw_liquidation_rows, liquidations_quality_summary = (
            self._build_liquidations_view(
                list(raw_row_groups["liquidations"]),
                allow_visible="liquidations" in source_visible_names,
            )
        )
        positions, raw_position_rows, positioning_quality_summary = (
            self._build_positioning_view(
                list(raw_row_groups["long_short_ratio"]),
                allow_visible="long_short_ratio" in source_visible_names,
            )
        )
        basis_rows, raw_basis_rows, basis_quality_summary = self._build_basis_view(
            list(raw_row_groups["basis"]),
            allow_visible="basis" in source_visible_names,
        )

        candidate_symbols = list(normalized_symbols or TARGET_SYMBOLS)
        symbols_map = self._build_symbols_map(
            candidate_symbols=candidate_symbols,
            tickers=tickers,
            trades=trades,
            orderbooks=orderbooks,
            fundings=fundings,
            open_interests=open_interests,
            liquidations=liquidations,
            positions=positions,
            basis_rows=basis_rows,
        )
        raw_symbols_map = self._build_symbols_map(
            candidate_symbols=candidate_symbols,
            tickers=raw_ticker_rows,
            trades=list(raw_row_groups["trade_flow"]),
            orderbooks=raw_orderbook_rows,
            fundings=list(raw_row_groups["funding"]),
            open_interests=raw_open_interest_rows,
            liquidations=raw_liquidation_rows,
            positions=raw_position_rows,
            basis_rows=raw_basis_rows,
        )

        section_specs = (
            {
                "key": "spot",
                "label": "spot 行情",
                "timestamp_field": "timestamp",
                "configured": True,
                "stale_after_seconds": max(15, int(SCHEDULER_CONFIG["ticker_interval"]) * 3),
            },
            {
                "key": "orderbook",
                "label": "orderbook",
                "timestamp_field": "timestamp",
                "configured": True,
                "stale_after_seconds": max(15, int(SCHEDULER_CONFIG["orderbook_interval"]) * 3),
            },
            {
                "key": "funding",
                "label": "funding",
                "timestamp_field": "timestamp",
                "configured": True,
                "stale_after_seconds": max(60, int(SCHEDULER_CONFIG["funding_interval"]) * 3),
            },
            {
                "key": "trade_flow_spot",
                "label": "trade_flow_spot",
                "timestamp_field": "open_time",
                "configured": True,
                "stale_after_seconds": max(
                    30,
                    int(EXCHANGE_DERIVATIVES_CONFIG["trade_flow_interval_seconds"]) * 3,
                ),
            },
            {
                "key": "trade_flow_derivatives",
                "label": "trade_flow_derivatives",
                "timestamp_field": "open_time",
                "configured": True,
                "stale_after_seconds": max(
                    30,
                    int(EXCHANGE_DERIVATIVES_CONFIG["trade_flow_interval_seconds"]) * 3,
                ),
            },
            {
                "key": "open_interest",
                "label": "open_interest",
                "timestamp_field": "timestamp",
                "configured": True,
                "stale_after_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval_seconds"]) * 3,
                ),
            },
            {
                "key": "liquidations",
                "label": "liquidations",
                "timestamp_field": "open_time",
                "configured": bool(EXCHANGE_DERIVATIVES_CONFIG["liquidation_url"]),
                "stale_after_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["liquidation_interval_seconds"]) * 3,
                ),
            },
            {
                "key": "positioning",
                "label": "positioning",
                "timestamp_field": "timestamp",
                "configured": bool(EXCHANGE_DERIVATIVES_CONFIG["long_short_ratio_url"]),
                "stale_after_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["positioning_interval_seconds"]) * 3,
                ),
            },
            {
                "key": "basis",
                "label": "basis",
                "timestamp_field": "timestamp",
                "configured": True,
                "stale_after_seconds": max(
                    60,
                    int(EXCHANGE_DERIVATIVES_CONFIG["basis_interval_seconds"]) * 3,
                ),
            },
        )

        for symbol_name, symbol_entry in symbols_map.items():
            raw_symbol_entry = raw_symbols_map.get(symbol_name) or self._empty_symbol_entry(
                symbol_name
            )
            spot_symbol_rows, raw_spot_symbol_rows, spot_symbol_quality_summary = (
                self._build_ticker_view(
                    list(raw_symbol_entry["spot"]),
                    allow_visible="ticker" in source_visible_names,
                )
            )
            orderbook_symbol_rows, raw_orderbook_symbol_rows, orderbook_symbol_quality_summary = (
                self._build_orderbook_view(
                    list(raw_symbol_entry["orderbook"]),
                    allow_visible="orderbook" in source_visible_names,
                )
            )
            symbol_entry["spot"] = spot_symbol_rows
            symbol_entry["raw_spot"] = raw_spot_symbol_rows
            symbol_entry["spot_quality_summary"] = spot_symbol_quality_summary
            symbol_entry["orderbook"] = orderbook_symbol_rows
            symbol_entry["raw_orderbook"] = raw_orderbook_symbol_rows
            symbol_entry["orderbook_quality_summary"] = orderbook_symbol_quality_summary
            visible_trade_flow_spot = list(symbol_entry["trade_flow_spot"])
            visible_trade_flow_derivatives = list(symbol_entry["trade_flow_derivatives"])
            raw_trade_flow_spot = list(raw_symbol_entry["trade_flow_spot"])
            raw_trade_flow_derivatives = list(raw_symbol_entry["trade_flow_derivatives"])

            if raw_trade_flow_derivatives:
                symbol_entry["trade_flow_scope"] = (
                    "mixed"
                    if raw_trade_flow_spot
                    else "derivatives_only"
                )
            elif raw_trade_flow_spot:
                symbol_entry["trade_flow_scope"] = "spot_only"
                symbol_entry["data_quality_flags"].append("trade_flow_spot_only")
                symbol_entry["quality_notes"].append(
                    "trade_flow 当前只覆盖现货成交流，不代表合约主动买卖流。"
                )
            symbol_entry["trade_flow"] = (
                visible_trade_flow_derivatives
                if visible_trade_flow_derivatives
                else visible_trade_flow_spot
            )

            data_quality_flags = list(symbol_entry["data_quality_flags"])
            quality_notes = list(symbol_entry["quality_notes"])
            section_statuses: dict[str, dict[str, object]] = {}
            configured_section_ratios: list[float] = []
            complete_sections: list[str] = []
            partial_sections: list[str] = []
            missing_sections: list[str] = []
            unconfigured_sections: list[str] = []
            stale_sections: list[str] = []

            for spec in section_specs:
                status = self._build_section_status(
                    rows=list(symbol_entry[spec["key"]]),
                    label=str(spec["label"]),
                    timestamp_field=str(spec["timestamp_field"]),
                    expected_exchanges=TARGET_EXCHANGES,
                    configured=bool(spec["configured"]),
                    stale_after_seconds=int(spec["stale_after_seconds"]),
                    now=now,
                )
                section_statuses[str(spec["key"])] = status
                if not status["configured"]:
                    unconfigured_sections.append(str(spec["key"]))
                    continue
                configured_section_ratios.append(float(status["coverage_ratio"]))
                if int(status["exchange_count"]) == 0:
                    missing_sections.append(str(spec["key"]))
                    self._append_unique(data_quality_flags, f"missing_{spec['key']}")
                    self._append_unique(
                        quality_notes,
                        f"{status['label']} 当前没有任何目标交易所最新快照。",
                    )
                elif float(status["coverage_ratio"]) < 1.0:
                    partial_sections.append(str(spec["key"]))
                    self._append_unique(
                        data_quality_flags,
                        f"{spec['key']}_exchange_coverage_incomplete",
                    )
                    missing_exchange_text = ",".join(status["missing_exchanges"])
                    self._append_unique(
                        quality_notes,
                        (
                            f"{status['label']} 只覆盖了 {status['exchange_count']}/"
                            f"{status['expected_exchange_count']} 家目标交易所，"
                            f"缺少 {missing_exchange_text}。"
                        ),
                    )
                else:
                    complete_sections.append(str(spec["key"]))

                if int(status["stale_exchange_count"]) > 0:
                    stale_sections.append(str(spec["key"]))

            if unconfigured_sections:
                labels = [
                    str(section_statuses[key]["label"])
                    for key in unconfigured_sections
                ]
                self._append_unique(
                    quality_notes,
                    f"{', '.join(labels)} 当前未配置真实来源，因此 bundle 中为空。",
                )

            if (
                configured_universe_summary.get("scope_kind") == "default"
                and configured_universe_summary.get("breadth_status") == "limited"
            ):
                self._append_unique(
                    data_quality_flags,
                    "exchange_configured_market_breadth_limited",
                )
                self._append_unique(
                    quality_notes,
                    "当前 exchange 默认市场宇宙只覆盖 "
                    f"{int(configured_universe_summary.get('asset_count') or 0)} 个资产、"
                    f"{int(configured_universe_summary.get('exchange_count') or 0)} 家交易所，"
                    "更适合核心执行市场监控，尚不足以代表更广市场 breadth。",
                )

            if not_ready_for_ai_source_names:
                self._append_unique(
                    data_quality_flags,
                    "exchange_source_not_ready_for_ai_present",
                )
                self._append_unique(
                    quality_notes,
                    "当前仍有 exchange source 虽然最近任务成功，但 latest 快照还不适合直接作为 AI 的交易证据: "
                    f"{', '.join(not_ready_for_ai_source_names[:8])}"
                    f"{' ...' if len(not_ready_for_ai_source_names) > 8 else ''}。",
                )

            # Cross-venue validation only applies when multiple venues are configured.
            min_spot_venues = min(2, max(len(TARGET_EXCHANGES), 1))
            if int(section_statuses["spot"]["exchange_count"]) < min_spot_venues:
                self._append_unique(data_quality_flags, "spot_cross_exchange_validation_weak")
                self._append_unique(
                    quality_notes,
                    (
                        f"spot 行情低于 {min_spot_venues} 家目标交易所，"
                        "AI 无法可靠做跨交易所价格校验。"
                        if min_spot_venues > 1
                        else "spot 行情缺少已配置目标交易所快照。"
                    ),
                )

            if stale_sections:
                stale_labels = [
                    str(section_statuses[key]["label"])
                    for key in stale_sections
                ]
                self._append_unique(data_quality_flags, "stale_subsection_present")
                self._append_unique(
                    quality_notes,
                    f"{', '.join(stale_labels)} 含有超过采样窗口的旧快照。",
                )

            spot_exchanges = set(section_statuses["spot"]["observed_exchanges"])
            orderbook_exchanges = set(section_statuses["orderbook"]["observed_exchanges"])
            funding_exchanges = set(section_statuses["funding"]["observed_exchanges"])
            trade_flow_derivative_exchanges = set(
                section_statuses["trade_flow_derivatives"]["observed_exchanges"]
            )
            open_interest_exchanges = set(
                section_statuses["open_interest"]["observed_exchanges"]
            )
            basis_exchanges = set(section_statuses["basis"]["observed_exchanges"])

            missing_orderbook_exchanges = sorted(spot_exchanges - orderbook_exchanges)
            if missing_orderbook_exchanges:
                self._append_unique(
                    data_quality_flags,
                    "missing_orderbook_for_some_spot_exchanges",
                )
                self._append_unique(
                    quality_notes,
                    f"orderbook 缺少部分已有 spot 行情的交易所快照: {', '.join(missing_orderbook_exchanges)}。",
                )

            missing_funding_exchanges = sorted(spot_exchanges - funding_exchanges)
            if missing_funding_exchanges:
                self._append_unique(
                    data_quality_flags,
                    "missing_funding_for_some_spot_exchanges",
                )
                self._append_unique(
                    quality_notes,
                    f"funding 缺少部分已有 spot 行情的交易所快照: {', '.join(missing_funding_exchanges)}。",
                )

            missing_trade_flow_derivative_exchanges = sorted(
                funding_exchanges - trade_flow_derivative_exchanges
            )
            if missing_trade_flow_derivative_exchanges:
                self._append_unique(
                    data_quality_flags,
                    "missing_trade_flow_derivatives_for_some_funding_exchanges",
                )
                self._append_unique(
                    quality_notes,
                    "trade_flow_derivatives 缺少部分已有 funding 的交易所快照: "
                    f"{', '.join(missing_trade_flow_derivative_exchanges)}。",
                )

            missing_open_interest_exchanges = sorted(
                funding_exchanges - open_interest_exchanges
            )
            if missing_open_interest_exchanges:
                self._append_unique(
                    data_quality_flags,
                    "missing_open_interest_for_some_funding_exchanges",
                )
                self._append_unique(
                    quality_notes,
                    "open_interest 缺少部分已有 funding 的交易所快照: "
                    f"{', '.join(missing_open_interest_exchanges)}。",
                )

            missing_basis_exchanges = sorted(funding_exchanges - basis_exchanges)
            if missing_basis_exchanges:
                self._append_unique(
                    data_quality_flags,
                    "missing_basis_for_some_funding_exchanges",
                )
                self._append_unique(
                    quality_notes,
                    f"basis 缺少部分已有 funding 的交易所快照: {', '.join(missing_basis_exchanges)}。",
                )

            if int(spot_symbol_quality_summary["missing_core_price_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "spot_missing_core_price",
                )
                self._append_unique(
                    quality_notes,
                    "spot 中存在既没有 last_price，也没有完整 bid/ask 对的真实交易所快照，"
                    "这些行只会保留在 raw_spot 中，不会被伪装成可直接交易解释的价格切片。",
                )

            if int(spot_symbol_quality_summary["invalid_core_price_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "spot_invalid_core_price",
                )
                self._append_unique(
                    quality_notes,
                    "spot 中存在价格字段非正或语义异常的真实交易所快照，"
                    "这些行只会保留在 raw_spot 中，避免 AI 误把坏价格当成真实市场状态。",
                )

            if int(spot_symbol_quality_summary["last_price_only_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "spot_bid_ask_missing_present",
                )
                self._append_unique(
                    quality_notes,
                    "spot 中存在只给出 last_price、缺少完整 bid/ask 对的交易所快照；"
                    "这些行仍可作为价格参考，但执行流动性语境偏弱。",
                )

            if int(spot_symbol_quality_summary["bid_ask_only_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "spot_last_price_missing_present",
                )
                self._append_unique(
                    quality_notes,
                    "spot 中存在只有 bid/ask、没有 last_price 的交易所快照；"
                    "这些行保留了可执行报价，但缺少最近成交价参考。",
                )

            if int(orderbook_symbol_quality_summary["missing_top_of_book_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "orderbook_missing_top_of_book",
                )
                self._append_unique(
                    quality_notes,
                    "orderbook 中存在既没有 best_bid 也没有 best_ask 的真实交易所快照，"
                    "这些行只会保留在 raw_orderbook 中，不会被伪装成可执行盘口。",
                )

            if int(orderbook_symbol_quality_summary["invalid_top_of_book_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "orderbook_invalid_top_of_book",
                )
                self._append_unique(
                    quality_notes,
                    "orderbook 中存在单边或非正 top-of-book 的真实交易所快照，"
                    "这些行只会保留在 raw_orderbook 中，避免 AI 把坏盘口当成真实流动性。",
                )

            spot_latest_rows = list(
                self._latest_rows_by_exchange(
                    list(raw_symbol_entry["spot"]),
                    "timestamp",
                ).values()
            )
            orderbook_latest_rows = list(
                self._latest_rows_by_exchange(
                    list(raw_symbol_entry["orderbook"]),
                    "timestamp",
                ).values()
            )
            funding_latest_rows = list(
                self._latest_rows_by_exchange(
                    list(raw_symbol_entry["funding"]),
                    "timestamp",
                ).values()
            )
            basis_latest_rows = list(
                self._latest_rows_by_exchange(
                    list(raw_symbol_entry["basis"]),
                    "timestamp",
                ).values()
            )
            liquidations_symbol_rows, raw_liquidation_symbol_rows, liquidations_symbol_quality_summary = (
                self._build_liquidations_view(
                    list(raw_symbol_entry["liquidations"]),
                    allow_visible="liquidations" in source_visible_names,
                )
            )
            open_interest_symbol_rows, raw_open_interest_symbol_rows, open_interest_symbol_quality_summary = (
                self._build_open_interest_view(
                    list(raw_symbol_entry["open_interest"]),
                    allow_visible="open_interest" in source_visible_names,
                )
            )
            positioning_symbol_rows, raw_positioning_symbol_rows, positioning_symbol_quality_summary = (
                self._build_positioning_view(
                    list(raw_symbol_entry["positioning"]),
                    allow_visible="long_short_ratio" in source_visible_names,
                )
            )
            derivatives_core_alignment = self._build_derivatives_core_alignment_summary(
                raw_symbol_entry
            )

            cross_exchange_diagnostics = {
                "spot_last_price_range_bps": self._range_bps_from_rows(
                    spot_latest_rows,
                    "last_price",
                ),
                "spot_mid_price_range_bps": self._range_bps_from_rows(
                    spot_latest_rows,
                    "mid_price",
                ),
                "orderbook_mid_price_range_bps": self._range_bps_from_rows(
                    orderbook_latest_rows,
                    "mid_price",
                ),
                "funding_mark_price_range_bps": self._range_bps_from_rows(
                    funding_latest_rows,
                    "mark_price",
                ),
                "basis_range_bps": self._absolute_range_from_rows(
                    basis_latest_rows,
                    "basis_bps",
                ),
                "max_derivatives_core_time_gap_seconds": derivatives_core_alignment[
                    "max_gap_seconds"
                ],
                "max_section_timestamp_spread_seconds": max(
                    (
                        float(status["timestamp_spread_seconds"])
                        for status in section_statuses.values()
                        if status["timestamp_spread_seconds"] is not None
                    ),
                    default=None,
                ),
            }

            spot_last_price_range_bps = cross_exchange_diagnostics["spot_last_price_range_bps"]
            if (
                spot_last_price_range_bps is not None
                and float(spot_last_price_range_bps) >= 30.0
            ):
                self._append_unique(
                    data_quality_flags,
                    "cross_exchange_last_price_dispersion_high",
                )
                self._append_unique(
                    quality_notes,
                    "spot 最新成交价跨交易所离散度达到 "
                    f"{float(spot_last_price_range_bps):.2f} bps，可能是快照时间错位或真实价差扩大。",
                )

            orderbook_mid_price_range_bps = cross_exchange_diagnostics["orderbook_mid_price_range_bps"]
            if (
                orderbook_mid_price_range_bps is not None
                and float(orderbook_mid_price_range_bps) >= 30.0
            ):
                self._append_unique(
                    data_quality_flags,
                    "cross_exchange_orderbook_mid_dispersion_high",
                )
                self._append_unique(
                    quality_notes,
                    "orderbook 中间价跨交易所离散度达到 "
                    f"{float(orderbook_mid_price_range_bps):.2f} bps。",
                )

            funding_mark_price_range_bps = cross_exchange_diagnostics["funding_mark_price_range_bps"]
            if (
                funding_mark_price_range_bps is not None
                and float(funding_mark_price_range_bps) >= 30.0
            ):
                self._append_unique(
                    data_quality_flags,
                    "cross_exchange_funding_mark_dispersion_high",
                )
                self._append_unique(
                    quality_notes,
                    "funding.mark_price 跨交易所离散度达到 "
                    f"{float(funding_mark_price_range_bps):.2f} bps。",
                )

            basis_range_bps = cross_exchange_diagnostics["basis_range_bps"]
            if basis_range_bps is not None and float(basis_range_bps) >= 100.0:
                self._append_unique(
                    data_quality_flags,
                    "cross_exchange_basis_dispersion_high",
                )
                self._append_unique(
                    quality_notes,
                    f"basis_bps 跨交易所差值达到 {float(basis_range_bps):.2f} bps。",
                )

            ticker_crossed_market_count = sum(
                1
                for row in spot_latest_rows
                if (
                    self._safe_float(row.get("bid")) is not None
                    and self._safe_float(row.get("ask")) is not None
                    and float(row["bid"]) > float(row["ask"])
                ) or (
                    self._safe_float(row.get("spread")) is not None
                    and float(row["spread"]) < 0
                )
            )
            if ticker_crossed_market_count > 0:
                self._append_unique(data_quality_flags, "ticker_crossed_market_present")
                self._append_unique(
                    quality_notes,
                    f"spot 行情中发现 {ticker_crossed_market_count} 个 crossed market/负 spread 快照。",
                )

            orderbook_crossed_book_count = sum(
                1
                for row in orderbook_latest_rows
                if (
                    self._safe_float(row.get("best_bid")) is not None
                    and self._safe_float(row.get("best_ask")) is not None
                    and float(row["best_bid"]) > float(row["best_ask"])
                ) or (
                    self._safe_float(row.get("spread")) is not None
                    and float(row["spread"]) < 0
                )
            )
            if orderbook_crossed_book_count > 0:
                self._append_unique(data_quality_flags, "orderbook_crossed_book_present")
                self._append_unique(
                    quality_notes,
                    f"orderbook 中发现 {orderbook_crossed_book_count} 个 crossed book/负 spread 快照。",
                )

            orderbook_missing_depth_notional_count = sum(
                1
                for row in orderbook_latest_rows
                if row.get("bid_depth_notional") is None or row.get("ask_depth_notional") is None
            )
            if orderbook_missing_depth_notional_count > 0:
                self._append_unique(data_quality_flags, "orderbook_missing_depth_notional")
                self._append_unique(
                    quality_notes,
                    "orderbook 存在缺少深度名义价值字段的交易所快照。",
                )

            funding_missing_mark_or_index_count = sum(
                1
                for row in funding_latest_rows
                if row.get("mark_price") is None or row.get("index_price") is None
            )
            if funding_missing_mark_or_index_count > 0:
                self._append_unique(data_quality_flags, "funding_missing_mark_or_index_price")
                self._append_unique(
                    quality_notes,
                    "funding 存在缺少 mark_price 或 index_price 的交易所快照。",
                )

            if int(open_interest_symbol_quality_summary["missing_value_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "open_interest_missing_value",
                )
                self._append_unique(
                    quality_notes,
                    "open_interest 中存在既没有 open_interest_usd 也没有 open_interest_contracts 的交易所快照，"
                    "这些真实行会保留在 raw_open_interest 中，但不会直接进入 AI 主视图。",
                )

            if int(positioning_symbol_quality_summary["missing_metric_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "positioning_missing_metrics",
                )
                self._append_unique(
                    quality_notes,
                    "positioning 中存在完全缺少核心多空指标的交易所快照，这些真实行只会保留在 raw_positioning 中。",
                )

            if int(positioning_symbol_quality_summary["incomplete_metric_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "positioning_incomplete_metrics_present",
                )
                self._append_unique(
                    quality_notes,
                    "positioning 中存在只给出单边账户比例或单边大户比例的交易所快照，"
                    "这类真实行不足以代表完整站位结构，只保留在 raw_positioning 诊断字段中。",
                )

            if int(liquidations_symbol_quality_summary["missing_metric_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "liquidations_missing_metrics",
                )
                self._append_unique(
                    quality_notes,
                    "liquidations 中存在既没有总清算额，也没有完整多空侧清算额的交易所快照，"
                    "这些真实行只会保留在 raw_liquidations 中，不会被伪装成零清算压力。",
                )

            if int(liquidations_symbol_quality_summary["incomplete_metric_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "liquidations_incomplete_metrics_present",
                )
                self._append_unique(
                    quality_notes,
                    "liquidations 中存在只给出部分清算字段的交易所快照，"
                    "这类真实行不足以代表完整清算压力，只保留在 raw_liquidations 诊断字段中。",
                )

            basis_missing_spot_price_count = sum(
                1
                for row in basis_latest_rows
                if row.get("spot_price") in (None, 0)
            )
            if basis_missing_spot_price_count > 0:
                self._append_unique(data_quality_flags, "basis_missing_spot_price")
                self._append_unique(
                    quality_notes,
                    "basis 中存在缺少 spot_price 的交易所快照，basis 只能作为部分参考。",
                )

            basis_missing_ticker_timestamp_count = sum(
                1
                for row in basis_latest_rows
                if str(row.get("ticker_timestamp_status") or "") in {"missing", "parse_error"}
            )
            if basis_missing_ticker_timestamp_count > 0:
                self._append_unique(data_quality_flags, "basis_missing_ticker_timestamp")
                self._append_unique(
                    quality_notes,
                    "basis 中存在缺少或无法解析 ticker 时间戳的交易所快照，"
                    "这些 basis 只能保留真实价差，不能证明现货与 funding 时间已严格对齐。",
                )

            basis_wide_component_gap_count = sum(
                1
                for row in basis_latest_rows
                if str(row.get("component_timestamp_gap_status") or "") == "wide"
            )
            if basis_wide_component_gap_count > 0:
                self._append_unique(data_quality_flags, "basis_component_time_gap_wide")
                self._append_unique(
                    quality_notes,
                    "basis 中存在现货与 funding 组件时间差过大的交易所快照，"
                    "这类 basis 更适合作为原始诊断，不应过度解释为严格同步的瞬时溢价。",
                )

            basis_annualization_unavailable_count = sum(
                1
                for row in basis_latest_rows
                if str(row.get("annualization_status") or "") not in {
                    "",
                    "ok",
                    "missing_basis_bps",
                }
            )
            if basis_annualization_unavailable_count > 0:
                self._append_unique(
                    data_quality_flags,
                    "basis_annualization_unavailable_present",
                )
                self._append_unique(
                    quality_notes,
                    "basis 中存在无法可靠年化的交易所快照，说明 next_funding_time 缺失、无效或不再晚于 funding 时间。",
                )

            if int(derivatives_core_alignment["wide_exchange_count"]) > 0:
                self._append_unique(
                    data_quality_flags,
                    "derivatives_core_time_gap_wide",
                )
                wide_exchange_names = list(
                    derivatives_core_alignment["wide_exchange_names"] or []
                )
                self._append_unique(
                    quality_notes,
                    "funding / open_interest / basis 在部分交易所不处于同一时间切片"
                    f"（例如 {', '.join(wide_exchange_names[:3])}"
                    f"{' ...' if len(wide_exchange_names) > 3 else ''}），"
                    f"最大核心时间差为 {float(derivatives_core_alignment['max_gap_seconds'] or 0.0):.1f} 秒；"
                    "这些真实字段更适合作为分层证据，而不应被直接解释成严格同步的合约拥挤快照。",
                )

            basis_symbol_rows, raw_basis_symbol_rows, basis_symbol_quality_summary = (
                self._build_basis_view(
                    list(raw_symbol_entry["basis"]),
                    allow_visible="basis" in source_visible_names,
                )
            )
            symbol_entry["open_interest"] = open_interest_symbol_rows
            symbol_entry["raw_open_interest"] = raw_open_interest_symbol_rows
            symbol_entry["open_interest_quality_summary"] = open_interest_symbol_quality_summary
            symbol_entry["liquidations"] = liquidations_symbol_rows
            symbol_entry["raw_liquidations"] = raw_liquidation_symbol_rows
            symbol_entry["liquidations_quality_summary"] = liquidations_symbol_quality_summary
            symbol_entry["positioning"] = positioning_symbol_rows
            symbol_entry["raw_positioning"] = raw_positioning_symbol_rows
            symbol_entry["positioning_quality_summary"] = positioning_symbol_quality_summary
            symbol_entry["basis"] = basis_symbol_rows
            symbol_entry["raw_basis"] = raw_basis_symbol_rows
            symbol_entry["basis_quality_summary"] = basis_symbol_quality_summary

            symbol_entry["coverage_summary"] = {
                "target_exchanges": list(TARGET_EXCHANGES),
                "expected_exchange_count": len(TARGET_EXCHANGES),
                "configured_section_count": len(configured_section_ratios),
                "configured_section_coverage_ratio": (
                    round(
                        sum(configured_section_ratios) / len(configured_section_ratios),
                        4,
                    )
                    if configured_section_ratios
                    else 0.0
                ),
                "complete_sections": complete_sections,
                "partial_sections": partial_sections,
                "missing_sections": missing_sections,
                "unconfigured_sections": unconfigured_sections,
                "stale_sections": stale_sections,
                "section_statuses": section_statuses,
            }
            symbol_entry["cross_exchange_diagnostics"] = cross_exchange_diagnostics
            symbol_entry["derivatives_core_alignment"] = derivatives_core_alignment
            symbol_entry["data_quality_flags"] = data_quality_flags
            symbol_entry["quality_notes"] = quality_notes
            symbol_entry["raw_source_counts"] = {
                source_name: count
                for source_name, count in {
                    "ticker": len(raw_symbol_entry["spot"]),
                    "orderbook": len(raw_symbol_entry["orderbook"]),
                    "funding": len(raw_symbol_entry["funding"]),
                    "trade_flow": len(raw_symbol_entry["trade_flow_spot"])
                    + len(raw_symbol_entry["trade_flow_derivatives"]),
                    "open_interest": len(raw_symbol_entry["open_interest"]),
                    "liquidations": len(raw_symbol_entry["liquidations"]),
                    "long_short_ratio": len(raw_symbol_entry["positioning"]),
                    "basis": len(raw_symbol_entry["basis"]),
                }.items()
                if count > 0
            }
            symbol_entry["source_counts"] = {
                source_name: count
                for source_name, count in {
                    "ticker": len(symbol_entry["spot"]),
                    "orderbook": len(symbol_entry["orderbook"]),
                    "funding": len(symbol_entry["funding"]),
                    "trade_flow": len(symbol_entry["trade_flow_spot"])
                    + len(symbol_entry["trade_flow_derivatives"]),
                    "open_interest": len(symbol_entry["open_interest"]),
                    "liquidations": len(symbol_entry["liquidations"]),
                    "long_short_ratio": len(symbol_entry["positioning"]),
                    "basis": len(symbol_entry["basis"]),
                }.items()
                if count > 0
            }
            symbol_entry["row_count"] = sum(symbol_entry["source_counts"].values())
            symbol_entry["raw_row_count"] = sum(symbol_entry["raw_source_counts"].values())
            symbol_entry["ai_ready_source_names"] = sorted(ai_ready_source_names)
            symbol_entry["ai_excluded_source_names"] = [
                item["source_name"]
                for item in ai_excluded_sources
                if symbol_name in set(item.get("raw_symbols") or [])
            ]

        return {
            "as_of": (
                self._latest_time_from_source_rows(
                    {
                        "ticker": tickers,
                        "orderbook": orderbooks,
                        "funding": fundings,
                        "trade_flow": trades,
                        "open_interest": open_interests,
                        "liquidations": liquidations,
                        "long_short_ratio": positions,
                        "basis": basis_rows,
                    }
                ).isoformat()
                if self._latest_time_from_source_rows(
                    {
                        "ticker": tickers,
                        "orderbook": orderbooks,
                        "funding": fundings,
                        "trade_flow": trades,
                        "open_interest": open_interests,
                        "liquidations": liquidations,
                        "long_short_ratio": positions,
                        "basis": basis_rows,
                    }
                ) is not None
                else None
            ),
            "raw_as_of": (
                self._latest_time_from_source_rows(raw_row_groups).isoformat()
                if self._latest_time_from_source_rows(raw_row_groups) is not None
                else None
            ),
            "generated_at": now.isoformat(),
            "symbol_count": len(symbols_map),
            "raw_symbol_count": len(
                {
                    str(row.get("symbol") or "").strip()
                    for rows in raw_row_groups.values()
                    for row in rows
                    if str(row.get("symbol") or "").strip()
                }
            ),
            "source_counts": self._count_rows_by_source(
                {
                    "ticker": tickers,
                    "orderbook": orderbooks,
                    "funding": fundings,
                    "trade_flow": trades,
                    "open_interest": open_interests,
                    "liquidations": liquidations,
                    "long_short_ratio": positions,
                    "basis": basis_rows,
                }
            ),
            "raw_source_counts": self._count_rows_by_source(raw_row_groups),
            "row_count": sum(
                len(rows)
                for rows in (
                    tickers,
                    orderbooks,
                    fundings,
                    trades,
                    open_interests,
                    liquidations,
                    positions,
                    basis_rows,
                )
            ),
            "raw_row_count": sum(len(rows) for rows in raw_row_groups.values()),
            "ai_ready_source_names": sorted(ai_ready_source_names),
            "ai_excluded_source_names": [
                str(item["source_name"])
                for item in ai_excluded_sources
            ],
            "ai_excluded_sources": ai_excluded_sources,
            "spot_quality_summary": spot_quality_summary,
            "orderbook_quality_summary": orderbook_quality_summary,
            "open_interest_quality_summary": open_interest_quality_summary,
            "liquidations_quality_summary": liquidations_quality_summary,
            "positioning_quality_summary": positioning_quality_summary,
            "basis_quality_summary": basis_quality_summary,
            "configured_universe_summary": configured_universe_summary,
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
            "source_health": [
                {
                    "source_name": row["source_name"],
                    "health_status": row["health_status"],
                    "is_ready_for_ai": row["is_ready_for_ai"],
                    "configuration_ready": row["configuration_ready"],
                    "semantic_scope": row["semantic_scope"],
                    "latest_pair_count": row["latest_pair_count"],
                    "latest_non_stale_pair_count": row["latest_non_stale_pair_count"],
                    "latest_non_stale_coverage_ratio": row["latest_non_stale_coverage_ratio"],
                    "latest_derivatives_pair_count": row["latest_derivatives_pair_count"],
                    "latest_derivatives_coverage_ratio": row["latest_derivatives_coverage_ratio"],
                    "data_quality_flags": row["data_quality_flags"],
                    "quality_notes": row["quality_notes"],
                }
                for row in coverage_rows
            ],
            "symbols": list(symbols_map.values()),
        }

    def load_source_coverage(
        self,
        source_names: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> dict:
        normalized_symbols = self._normalize_symbols(symbols)
        normalized_names = {
            source_name.strip().lower()
            for source_name in (source_names or [])
            if source_name.strip()
        }
        specs = [
            spec
            for spec in self._build_coverage_specs(normalized_symbols)
            if not normalized_names or str(spec["source_name"]).lower() in normalized_names
        ]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not specs:
            health_summary = summarize_health_rows([])
            return {
                "generated_at": now.isoformat(),
                "source_count": 0,
                "stale_source_count": 0,
                "total_latest_pair_count": 0,
                "total_latest_point_count": 0,
                "ready_for_ai_source_count": 0,
                "not_ready_for_ai_source_count": 0,
                **health_summary,
                "sources": [],
            }

        source_name_list = [str(spec["source_name"]) for spec in specs]
        placeholders = ",".join("?" for _ in source_name_list)
        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'exchange_data'
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
        for spec in specs:
            where_sql = ""
            base_params = list(spec.get("params") or ())
            params = tuple(base_params)
            where_clauses: list[str] = []
            if spec.get("where_sql"):
                where_clauses.append(str(spec["where_sql"]))
            if normalized_symbols:
                placeholders = ",".join("?" for _ in normalized_symbols)
                where_clauses.append(f"symbol IN ({placeholders})")
                base_params.extend(normalized_symbols)
            params = tuple(base_params)
            if spec.get("where_sql"):
                where_sql = f" WHERE {spec['where_sql']}"
            if where_clauses:
                where_sql = f" WHERE {' AND '.join(where_clauses)}"
            if spec["source_name"] == "ticker":
                extra_columns = (
                    "timestamp",
                    "last_price",
                    "bid",
                    "ask",
                )
            elif spec["source_name"] == "orderbook":
                extra_columns = (
                    "timestamp",
                    "best_bid",
                    "best_ask",
                    "bid_depth_notional",
                    "ask_depth_notional",
                )
            elif spec["source_name"] == "trade_flow":
                extra_columns = ("market_type",)
            elif spec["source_name"] == "open_interest":
                extra_columns = (
                    "timestamp",
                    "open_interest_contracts",
                    "open_interest_usd",
                )
            elif spec["source_name"] == "liquidations":
                extra_columns = (
                    "open_time",
                    "long_liquidation_notional",
                    "short_liquidation_notional",
                    "long_liquidation_count",
                    "short_liquidation_count",
                    "total_liquidation_notional",
                    "max_single_liquidation_notional",
                )
            elif spec["source_name"] == "long_short_ratio":
                extra_columns = (
                    "timestamp",
                    "long_ratio",
                    "short_ratio",
                    "long_short_ratio",
                    "top_trader_long_ratio",
                    "top_trader_short_ratio",
                )
            elif spec["source_name"] == "basis":
                extra_columns = (
                    "timestamp",
                    "basis_bps",
                    "annualized_basis_bps",
                    "next_funding_time",
                    "raw_payload_json",
                )
            else:
                extra_columns = ()
            extra_columns = tuple(
                dict.fromkeys((str(spec["time_column"]), *extra_columns))
            )
            table_rows = self._load_table_rows(
                table_name=str(spec["table_name"]),
                params=params,
                where_sql=where_sql,
                extra_columns=extra_columns,
            )
            semantic_scope = spec.get("semantic_scope")
            quality_notes = list(spec.get("quality_notes") or [])
            data_quality_flags: list[str] = []
            latest_market_type_count = 0
            latest_derivatives_pair_count = 0
            latest_spot_pair_count = 0
            latest_spot_coverage_ratio = 0.0
            latest_derivatives_coverage_ratio = 0.0
            latest_spot_missing_pair_count = 0
            latest_derivatives_missing_pair_count = 0
            latest_spot_undercovered_symbol_count = 0
            latest_derivatives_undercovered_symbol_count = 0
            spot_coverage_gaps: list[dict[str, object]] = []
            derivatives_coverage_gaps: list[dict[str, object]] = []
            visible_table_rows = list(table_rows)
            if spec["source_name"] == "ticker":
                visible_table_rows, _, _ = self._build_ticker_view(
                    table_rows,
                    allow_visible=True,
                )
                ticker_missing_core_price_count = sum(
                    1
                    for row in table_rows
                    if self._ticker_visibility_reason(row) == "missing_core_price"
                )
                if ticker_missing_core_price_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "spot_missing_core_price",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest spot 快照里存在既没有 last_price，也没有完整 bid/ask 对的行，"
                        "这些真实行只会保留在 raw_spot 中，不会直接进入 AI 主视图。",
                    )

                ticker_invalid_core_price_count = sum(
                    1
                    for row in table_rows
                    if self._ticker_visibility_reason(row) == "invalid_core_price"
                )
                if ticker_invalid_core_price_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "spot_invalid_core_price",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest spot 快照里存在价格字段非正或语义异常的行，"
                        "这些真实行只会保留在 raw_spot 中。",
                    )

                ticker_last_price_only_count = sum(
                    1
                    for row in table_rows
                    if self._ticker_visibility_reason(row) == "ready_last_price_only"
                )
                if ticker_last_price_only_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "spot_bid_ask_missing_present",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest spot 快照里存在只给出 last_price、缺少完整 bid/ask 对的行；"
                        "这些行仍可作为价格参考，但执行语境较弱。",
                    )

                ticker_bid_ask_only_count = sum(
                    1
                    for row in table_rows
                    if self._ticker_visibility_reason(row) == "ready_bid_ask_only"
                )
                if ticker_bid_ask_only_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "spot_last_price_missing_present",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest spot 快照里存在只有 bid/ask、没有 last_price 的行；"
                        "这些行保留了可执行报价，但缺少最近成交价参考。",
                    )
            elif spec["source_name"] == "orderbook":
                visible_table_rows, _, _ = self._build_orderbook_view(
                    table_rows,
                    allow_visible=True,
                )
                orderbook_missing_top_of_book_count = sum(
                    1
                    for row in table_rows
                    if self._orderbook_visibility_reason(row) == "missing_top_of_book"
                )
                if orderbook_missing_top_of_book_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "orderbook_missing_top_of_book",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest orderbook 快照里存在既没有 best_bid 也没有 best_ask 的行，"
                        "这些真实行只会保留在 raw_orderbook 中，不会直接进入 AI 主视图。",
                    )

                orderbook_invalid_top_of_book_count = sum(
                    1
                    for row in table_rows
                    if self._orderbook_visibility_reason(row) == "invalid_top_of_book"
                )
                if orderbook_invalid_top_of_book_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "orderbook_invalid_top_of_book",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest orderbook 快照里存在单边或非正 top-of-book 的行，"
                        "这些真实行只会保留在 raw_orderbook 中。",
                    )
            elif spec["source_name"] == "open_interest":
                visible_table_rows, _, _ = self._build_open_interest_view(
                    table_rows,
                    allow_visible=True,
                )
            elif spec["source_name"] == "liquidations":
                visible_table_rows, _, _ = self._build_liquidations_view(
                    table_rows,
                    allow_visible=True,
                )
            elif spec["source_name"] == "long_short_ratio":
                visible_table_rows, _, _ = self._build_positioning_view(
                    table_rows,
                    allow_visible=True,
                )
            elif spec["source_name"] == "basis":
                visible_table_rows, _, _ = self._build_basis_view(
                    [self._enrich_basis_row(row) for row in table_rows],
                    allow_visible=True,
                )

            coverage_summary = self._build_symbol_coverage_summary(
                self._build_symbol_exchange_map(visible_table_rows),
                normalized_symbols,
            )
            latest_pair_times = self._build_latest_pair_times_from_rows(
                visible_table_rows,
                str(spec["time_column"]),
            )
            latest_stale_pair_count = 0
            latest_stale_symbols: set[str] = set()
            stale_after_seconds = int(spec["interval_seconds"]) * 3
            if len(TARGET_EXCHANGES) <= 1 and str(spec["source_name"]) in {
                "ticker",
                "orderbook",
            }:
                stale_after_seconds = max(stale_after_seconds, 45)
            for row in latest_pair_times:
                symbol = str(row.get("symbol") or "").strip()
                exchange = str(row.get("exchange") or "").strip().lower()
                if symbol not in TARGET_SYMBOLS or exchange not in TARGET_EXCHANGES:
                    continue
                age_seconds = self._age_seconds(now, row.get("latest_pair_time"))
                if age_seconds is not None and age_seconds > stale_after_seconds:
                    latest_stale_pair_count += 1
                    latest_stale_symbols.add(symbol)
            latest_meta = self._build_source_meta_from_rows(
                visible_table_rows,
                str(spec["time_column"]),
            )
            if spec["source_name"] == "trade_flow":
                spot_trade_flow_rows = [
                    row
                    for row in table_rows
                    if str(row.get("market_type") or "").strip().lower() == "spot"
                ]
                derivatives_trade_flow_rows = [
                    row
                    for row in table_rows
                    if str(row.get("market_type") or "").strip().lower() != "spot"
                ]
                spot_trade_flow_coverage = self._build_symbol_coverage_summary(
                    self._build_symbol_exchange_map(spot_trade_flow_rows),
                    normalized_symbols,
                )
                derivatives_trade_flow_coverage = self._build_symbol_coverage_summary(
                    self._build_symbol_exchange_map(derivatives_trade_flow_rows),
                    normalized_symbols,
                )
                latest_market_type_count = len(
                    {
                        str(row.get("market_type") or "").strip().lower()
                        for row in table_rows
                        if str(row.get("market_type") or "").strip()
                    }
                )
                latest_spot_pair_count = int(
                    spot_trade_flow_coverage["observed_pair_count"] or 0
                )
                latest_derivatives_pair_count = int(
                    derivatives_trade_flow_coverage["observed_pair_count"] or 0
                )
                latest_spot_coverage_ratio = float(
                    spot_trade_flow_coverage["coverage_ratio"] or 0.0
                )
                latest_derivatives_coverage_ratio = float(
                    derivatives_trade_flow_coverage["coverage_ratio"] or 0.0
                )
                latest_spot_missing_pair_count = int(
                    spot_trade_flow_coverage["missing_pair_count"] or 0
                )
                latest_derivatives_missing_pair_count = int(
                    derivatives_trade_flow_coverage["missing_pair_count"] or 0
                )
                latest_spot_undercovered_symbol_count = int(
                    spot_trade_flow_coverage["undercovered_symbol_count"] or 0
                )
                latest_derivatives_undercovered_symbol_count = int(
                    derivatives_trade_flow_coverage["undercovered_symbol_count"] or 0
                )
                spot_coverage_gaps = list(spot_trade_flow_coverage["coverage_gaps"] or [])
                derivatives_coverage_gaps = list(
                    derivatives_trade_flow_coverage["coverage_gaps"] or []
                )
                if latest_derivatives_pair_count > 0:
                    semantic_scope = (
                        "mixed"
                        if latest_spot_pair_count > 0
                        else "derivatives_only"
                    )
                elif latest_spot_pair_count > 0:
                    semantic_scope = "spot_only"
                    self._append_unique(data_quality_flags, "trade_flow_spot_only")
                    self._append_unique(
                        quality_notes,
                        "trade_flow 当前只覆盖现货成交流，不代表合约主动买卖流。"
                    )
                else:
                    semantic_scope = "missing"
                if latest_derivatives_pair_count == 0 and latest_spot_pair_count > 0:
                    self._append_unique(data_quality_flags, "trade_flow_derivatives_missing")
                elif (
                    latest_derivatives_pair_count > 0
                    and latest_derivatives_coverage_ratio < 1.0
                ):
                    self._append_unique(
                        data_quality_flags,
                        "trade_flow_derivatives_coverage_incomplete",
                    )
                    derivatives_gap_note = self._coverage_gap_note(derivatives_coverage_gaps)
                    self._append_unique(
                        quality_notes,
                        (
                            "trade_flow 的合约维度仍未覆盖全部目标交易所。"
                            f"{derivatives_gap_note or ''}"
                        ),
                    )
                if latest_spot_pair_count > 0 and latest_spot_coverage_ratio < 1.0:
                    spot_gap_note = self._coverage_gap_note(spot_coverage_gaps)
                    self._append_unique(
                        quality_notes,
                        f"trade_flow 的现货维度仍未覆盖全部目标交易所。{spot_gap_note or ''}",
                    )
            elif spec["source_name"] == "open_interest":
                open_interest_missing_value_count = sum(
                    1
                    for row in table_rows
                    if self._open_interest_visibility_reason(row)
                    == "missing_open_interest_value"
                )
                if open_interest_missing_value_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "open_interest_missing_value",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest open_interest 快照里存在既没有 open_interest_usd 也没有 open_interest_contracts 的行，"
                        "这些真实行会保留在 raw_open_interest 诊断里，而不会直接进入 AI 主视图。",
                    )
            elif spec["source_name"] == "long_short_ratio":
                positioning_missing_metric_count = sum(
                    1
                    for row in table_rows
                    if self._positioning_visibility_reason(row)
                    == "missing_positioning_metrics"
                )
                if positioning_missing_metric_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "positioning_missing_metrics",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest positioning 快照里存在完全缺少核心多空指标的行，这些真实行只会保留在 raw_positioning 中。",
                    )

                positioning_incomplete_metric_count = sum(
                    1
                    for row in table_rows
                    if self._positioning_visibility_reason(row)
                    in {
                        "incomplete_accounts_metrics",
                        "incomplete_top_trader_metrics",
                        "incomplete_positioning_metrics",
                    }
                )
                if positioning_incomplete_metric_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "positioning_incomplete_metrics_present",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest positioning 快照里存在只给出单边账户比例或单边大户比例的行，"
                        "这些真实行不足以代表完整站位结构，只保留在 raw_positioning 诊断字段中。",
                    )
            elif spec["source_name"] == "liquidations":
                liquidations_missing_metric_count = sum(
                    1
                    for row in table_rows
                    if self._liquidations_visibility_reason(row)
                    == "missing_liquidation_metrics"
                )
                if liquidations_missing_metric_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "liquidations_missing_metrics",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest liquidations 快照里存在既没有总清算额，也没有完整多空侧清算额的行，"
                        "这些真实行只会保留在 raw_liquidations 中，不会被伪装成零清算压力。",
                    )

                liquidations_incomplete_metric_count = sum(
                    1
                    for row in table_rows
                    if self._liquidations_visibility_reason(row)
                    == "incomplete_liquidation_metrics"
                )
                if liquidations_incomplete_metric_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "liquidations_incomplete_metrics_present",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest liquidations 快照里存在只给出部分清算字段的行，"
                        "这些真实行不足以代表完整清算压力，只保留在 raw_liquidations 诊断字段中。",
                    )
            elif spec["source_name"] == "basis":
                basis_missing_ticker_timestamp_count = sum(
                    1
                    for row in table_rows
                    if str(
                        self._basis_diagnostics(row).get("ticker_timestamp_status") or ""
                    ) in {"missing", "parse_error"}
                )
                if basis_missing_ticker_timestamp_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "basis_missing_ticker_timestamp",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest basis 快照里存在缺少或无法解析 ticker 时间戳的行，"
                        "说明部分 basis 不能证明现货与 funding 时间已经严格对齐。",
                    )

                basis_component_gap_wide_count = sum(
                    1
                    for row in table_rows
                    if str(
                        self._basis_diagnostics(row).get("component_timestamp_gap_status") or ""
                    ) == "wide"
                )
                if basis_component_gap_wide_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "basis_component_time_gap_wide",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest basis 快照里存在现货与 funding 时间差过大的行，"
                        "部分 basis 更适合作为原始诊断而不是严格同步的交易执行证据。",
                    )

                basis_annualization_unavailable_count = sum(
                    1
                    for row in table_rows
                    if str(
                        self._basis_diagnostics(row).get("annualization_status") or ""
                    ) not in {
                        "",
                        "ok",
                        "missing_basis_bps",
                    }
                )
                if basis_annualization_unavailable_count > 0:
                    self._append_unique(
                        data_quality_flags,
                        "basis_annualization_unavailable_present",
                    )
                    self._append_unique(
                        quality_notes,
                        "latest basis 快照里存在无法可靠年化的行，说明 next_funding_time 对部分交易所不可直接用于年化 basis 推导。",
                    )
            if (
                bool(spec.get("configuration_ready", True))
                and (
                    int(coverage_summary["undercovered_symbol_count"]) > 0
                    or int(coverage_summary["missing_symbol_count"]) > 0
                )
            ):
                self._append_unique(data_quality_flags, "exchange_coverage_incomplete")
                coverage_gap_note = self._coverage_gap_note(
                    list(coverage_summary["coverage_gaps"] or [])
                )
                self._append_unique(
                    quality_notes,
                    (
                        "最新快照仍有目标 symbol 未覆盖全部目标交易所。"
                        f"{coverage_gap_note or ''}"
                    ),
                )
            if latest_stale_pair_count > 0:
                self._append_unique(data_quality_flags, "stale_pairs_present")
                self._append_unique(
                    quality_notes,
                    (
                        f"latest 快照里有 {latest_stale_pair_count} 个 symbol|exchange"
                        f" 已超过采样窗口，涉及 {len(latest_stale_symbols)} 个 symbol。"
                    ),
                )
            run_meta = run_map.get(str(spec["source_name"]), {})
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = self._to_datetime(last_run_finished_at)
            latest_observation_time = latest_meta.get("latest_observation_time")
            latest_observation_dt = self._to_datetime(latest_observation_time)
            # Prefer observation time for hot streams: an old collection_runs row
            # must not hide fresh latest_* snapshots (common after once-mode collects).
            source_name = str(spec["source_name"])
            if (
                source_name in self.OBSERVATION_PRIMARY_HEALTH_SOURCES
                and latest_observation_dt is not None
            ):
                staleness_anchor = latest_observation_dt
            else:
                staleness_anchor = last_run_dt or latest_observation_dt
            stale_mult = int(spec["interval_seconds"]) * 3
            # Single-venue deploys often collect serially across many symbols; give
            # ticker/orderbook a slightly wider health window so AI visibility is
            # not lost before the bundle is assembled.
            if len(TARGET_EXCHANGES) <= 1 and source_name in {"ticker", "orderbook"}:
                stale_mult = max(stale_mult, 45)
            is_stale = staleness_anchor is None or (
                now - staleness_anchor
            ).total_seconds() > stale_mult
            health_status = resolve_source_health_status(
                enabled=True,
                configuration_ready=bool(spec.get("configuration_ready", True)),
                last_run_status=run_meta.get("status"),
                latest_point_count=int(latest_meta.get("latest_pair_count") or 0),
                is_stale=is_stale,
            )
            latest_non_stale_pair_count = max(
                int(coverage_summary["observed_pair_count"] or 0) - latest_stale_pair_count,
                0,
            )
            latest_non_stale_coverage_ratio = self._safe_ratio(
                latest_non_stale_pair_count,
                int(spec.get("expected_pair_count") or 0),
            )
            is_ready_for_ai = self._is_source_ready_for_ai(
                source_name=str(spec["source_name"]),
                health_status=health_status,
                latest_non_stale_pair_count=latest_non_stale_pair_count,
                latest_non_stale_coverage_ratio=latest_non_stale_coverage_ratio,
                data_quality_flags=data_quality_flags,
                latest_derivatives_pair_count=latest_derivatives_pair_count,
                latest_derivatives_coverage_ratio=latest_derivatives_coverage_ratio,
            )
            if health_status == "ready" and not is_ready_for_ai:
                self._append_unique(
                    quality_notes,
                    "最近一次采集虽然成功，但 latest 快照仍未达到可直接供 AI 做交易判断的质量门槛。",
                )
            rows.append(
                {
                    "source_name": spec["source_name"],
                    "name": spec["name"],
                    "enabled": True,
                    "configuration_ready": bool(spec.get("configuration_ready", True)),
                    "table_name": spec["table_name"],
                    "expected_pair_count": int(spec.get("expected_pair_count") or 0),
                    "latest_point_count": int(latest_meta.get("latest_point_count") or 0),
                    "latest_symbol_count": int(latest_meta.get("latest_symbol_count") or 0),
                    "latest_exchange_count": int(latest_meta.get("latest_exchange_count") or 0),
                    "latest_pair_count": int(latest_meta.get("latest_pair_count") or 0),
                    "latest_coverage_ratio": float(coverage_summary["coverage_ratio"] or 0.0),
                    "latest_missing_pair_count": int(
                        coverage_summary["missing_pair_count"] or 0
                    ),
                    "latest_full_coverage_symbol_count": int(
                        coverage_summary["full_coverage_symbol_count"] or 0
                    ),
                    "latest_undercovered_symbol_count": int(
                        coverage_summary["undercovered_symbol_count"] or 0
                    ),
                    "latest_missing_symbol_count": int(
                        coverage_summary["missing_symbol_count"] or 0
                    ),
                    "latest_stale_pair_count": latest_stale_pair_count,
                    "latest_stale_symbol_count": len(latest_stale_symbols),
                    "latest_non_stale_pair_count": latest_non_stale_pair_count,
                    "latest_non_stale_coverage_ratio": latest_non_stale_coverage_ratio,
                    "coverage_gaps": coverage_summary["coverage_gaps"],
                    "latest_market_type_count": latest_market_type_count,
                    "latest_spot_pair_count": latest_spot_pair_count,
                    "latest_derivatives_pair_count": latest_derivatives_pair_count,
                    "latest_spot_coverage_ratio": latest_spot_coverage_ratio,
                    "latest_derivatives_coverage_ratio": latest_derivatives_coverage_ratio,
                    "latest_spot_missing_pair_count": latest_spot_missing_pair_count,
                    "latest_derivatives_missing_pair_count": latest_derivatives_missing_pair_count,
                    "latest_spot_undercovered_symbol_count": latest_spot_undercovered_symbol_count,
                    "latest_derivatives_undercovered_symbol_count": latest_derivatives_undercovered_symbol_count,
                    "spot_coverage_gaps": spot_coverage_gaps,
                    "derivatives_coverage_gaps": derivatives_coverage_gaps,
                    "latest_observation_time": latest_observation_time,
                    "last_run_status": run_meta.get("status"),
                    "last_run_item_count": int(run_meta.get("item_count") or 0),
                    "last_run_finished_at": last_run_finished_at,
                    "last_run_message": run_meta.get("message"),
                    "last_run_metadata": json.loads(run_meta["metadata_json"])
                    if run_meta.get("metadata_json")
                    else None,
                    "is_stale": is_stale,
                    "health_status": health_status,
                    "is_ready_for_ai": is_ready_for_ai,
                    "semantic_scope": semantic_scope,
                    "data_quality_flags": data_quality_flags,
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
            "total_latest_pair_count": sum(item["latest_pair_count"] for item in rows),
            "total_latest_point_count": sum(item["latest_point_count"] for item in rows),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
            **health_summary,
            "sources": rows,
        }

    def build_scheduler(self) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        market_info_interval = SCHEDULER_CONFIG["market_info_interval"]
        kline_interval = SCHEDULER_CONFIG["kline_interval"]
        ticker_interval = SCHEDULER_CONFIG["ticker_interval"]
        funding_interval = SCHEDULER_CONFIG["funding_interval"]
        orderbook_interval = SCHEDULER_CONFIG["orderbook_interval"]
        cleanup_interval = EXCHANGE_DATA_RETENTION["cleanup_interval"]
        trade_flow_interval = EXCHANGE_DERIVATIVES_CONFIG["trade_flow_interval_seconds"]
        open_interest_interval = EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval_seconds"]
        liquidation_interval = EXCHANGE_DERIVATIVES_CONFIG["liquidation_interval_seconds"]
        positioning_interval = EXCHANGE_DERIVATIVES_CONFIG["positioning_interval_seconds"]
        basis_interval = EXCHANGE_DERIVATIVES_CONFIG["basis_interval_seconds"]

        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="market_info",
                job_name="market_info_scheduler",
                func=lambda: self.market_info_collector.collect(force=False),
                metadata={"mode": "scheduler", "force": False},
            ),
            "interval",
            seconds=market_info_interval,
            id="market_info",
            name="交易对静态信息采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, market_info_interval),
            jitter=max(1, market_info_interval // 10),
        )
        for timeframe in KLINE_TIMEFRAMES:
            interval_seconds = self.kline_collector.TIMEFRAME_INTERVAL_SECONDS.get(
                timeframe,
                kline_interval,
            )
            scheduler.add_job(
                lambda timeframe=timeframe: self._run_collection_job(
                    source_name=f"kline_{timeframe}",
                    job_name="kline_scheduler",
                    func=lambda timeframe=timeframe: self.kline_collector.collect_timeframe(
                        timeframe
                    ),
                    metadata={"mode": "scheduler", "timeframe": timeframe},
                ),
                "interval",
                seconds=interval_seconds,
                id=f"kline_{timeframe}",
                name=f"K线增量更新[{timeframe}]",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(60, interval_seconds),
                jitter=max(1, interval_seconds // 10),
            )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="ticker",
                job_name="ticker_scheduler",
                func=self.ticker_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=ticker_interval,
            id="ticker",
            name="实时行情采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(15, ticker_interval * 3),
            jitter=max(1, ticker_interval // 5),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="funding",
                job_name="funding_scheduler",
                func=self.funding_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=funding_interval,
            id="funding",
            name="资金费率采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, funding_interval),
            jitter=max(1, funding_interval // 10),
        )
        # 分层深度采集：按 tier 不同频率
        from config.symbols import SymbolTier, symbols_by_tier
        from config.collection_tiers import get_orderbook_interval

        for tier in SymbolTier:
            tier_symbols = symbols_by_tier(tier)
            tier_interval = get_orderbook_interval(tier)
            scheduler.add_job(
                lambda syms=tier_symbols: self._run_collection_job(
                    source_name="orderbook",
                    job_name=f"orderbook_tiered_scheduler",
                    func=lambda syms=syms: self._collect_orderbooks_for_symbols(syms),
                    metadata={"mode": "scheduler", "tier": tier.value},
                ),
                "interval",
                seconds=tier_interval,
                id=f"orderbook_{tier.value}",
                name=f"深度数据采集[{tier.value}]",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(15, tier_interval * 3),
                jitter=max(1, tier_interval // 5),
            )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="trade_flow",
                job_name="trade_flow_scheduler",
                func=self.trades_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=trade_flow_interval,
            id="trade_flow",
            name="成交与主动买卖流采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(30, trade_flow_interval * 3),
            jitter=max(1, trade_flow_interval // 10),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="open_interest",
                job_name="open_interest_scheduler",
                func=self.open_interest_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=open_interest_interval,
            id="open_interest",
            name="持仓量采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, open_interest_interval * 3),
            jitter=max(1, open_interest_interval // 10),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="liquidations",
                job_name="liquidations_scheduler",
                func=self.liquidations_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=liquidation_interval,
            id="liquidations",
            name="清算聚合采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, liquidation_interval * 3),
            jitter=max(1, liquidation_interval // 10),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="long_short_ratio",
                job_name="long_short_ratio_scheduler",
                func=self.long_short_ratio_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=positioning_interval,
            id="long_short_ratio",
            name="多空比采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, positioning_interval * 3),
            jitter=max(1, positioning_interval // 10),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="basis",
                job_name="basis_scheduler",
                func=self.basis_collector.collect,
                metadata={"mode": "scheduler"},
            ),
            "interval",
            seconds=basis_interval,
            id="basis",
            name="basis 计算",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, basis_interval * 3),
            jitter=max(1, basis_interval // 10),
        )
        scheduler.add_job(
            self.cleanup_historical_data,
            "interval",
            seconds=cleanup_interval,
            id="exchange_cleanup",
            name="交易所高频快照清理",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(300, cleanup_interval),
        )
        return scheduler

    def build_async_scheduler(self):
        """构建 AsyncIOScheduler — 利用 asyncio 事件循环调度采集任务。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        market_info_interval = SCHEDULER_CONFIG["market_info_interval"]
        kline_interval = SCHEDULER_CONFIG["kline_interval"]
        ticker_interval = SCHEDULER_CONFIG["ticker_interval"]
        funding_interval = SCHEDULER_CONFIG["funding_interval"]
        cleanup_interval = EXCHANGE_DATA_RETENTION["cleanup_interval"]
        trade_flow_interval = EXCHANGE_DERIVATIVES_CONFIG["trade_flow_interval_seconds"]
        open_interest_interval = EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval_seconds"]
        liquidation_interval = EXCHANGE_DERIVATIVES_CONFIG["liquidation_interval_seconds"]
        positioning_interval = EXCHANGE_DERIVATIVES_CONFIG["positioning_interval_seconds"]
        basis_interval = EXCHANGE_DERIVATIVES_CONFIG["basis_interval_seconds"]

        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="market_info",
                job_name="market_info_async_scheduler",
                func=lambda: self.market_info_collector.collect(force=False),
                metadata={"mode": "async_scheduler", "force": False},
            ),
            "interval",
            seconds=market_info_interval,
            id="market_info",
            name="交易对静态信息采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, market_info_interval),
        )
        for timeframe in KLINE_TIMEFRAMES:
            interval_seconds = self.kline_collector.TIMEFRAME_INTERVAL_SECONDS.get(
                timeframe, kline_interval,
            )
            scheduler.add_job(
                lambda tf=timeframe: self._run_collection_job(
                    source_name=f"kline_{tf}",
                    job_name="kline_async_scheduler",
                    func=lambda tf=tf: self.kline_collector.collect_timeframe(tf),
                    metadata={"mode": "async_scheduler", "timeframe": tf},
                ),
                "interval",
                seconds=interval_seconds,
                id=f"kline_{timeframe}",
                name=f"K线增量更新[{timeframe}](async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(60, interval_seconds),
            )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="ticker",
                job_name="ticker_async_scheduler",
                func=self.ticker_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=ticker_interval,
            id="ticker",
            name="实时行情采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(15, ticker_interval * 3),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="funding",
                job_name="funding_async_scheduler",
                func=self.funding_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=funding_interval,
            id="funding",
            name="资金费率采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, funding_interval),
        )

        from config.symbols import SymbolTier, symbols_by_tier
        from config.collection_tiers import get_orderbook_interval

        for tier in SymbolTier:
            tier_symbols = symbols_by_tier(tier)
            tier_interval = get_orderbook_interval(tier)
            scheduler.add_job(
                lambda syms=tier_symbols: self._run_collection_job(
                    source_name="orderbook",
                    job_name="orderbook_tiered_async_scheduler",
                    func=lambda syms=syms: self._collect_orderbooks_for_symbols(syms),
                    metadata={"mode": "async_scheduler", "tier": tier.value},
                ),
                "interval",
                seconds=tier_interval,
                id=f"orderbook_{tier.value}",
                name=f"深度数据采集[{tier.value}](async)",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(15, tier_interval * 3),
            )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="trade_flow",
                job_name="trade_flow_async_scheduler",
                func=self.trades_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=trade_flow_interval,
            id="trade_flow",
            name="成交与主动买卖流采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(30, trade_flow_interval * 3),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="open_interest",
                job_name="open_interest_async_scheduler",
                func=self.open_interest_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=open_interest_interval,
            id="open_interest",
            name="持仓量采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, open_interest_interval * 3),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="liquidations",
                job_name="liquidations_async_scheduler",
                func=self.liquidations_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=liquidation_interval,
            id="liquidations",
            name="清算聚合采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, liquidation_interval * 3),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="long_short_ratio",
                job_name="long_short_ratio_async_scheduler",
                func=self.long_short_ratio_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=positioning_interval,
            id="long_short_ratio",
            name="多空比采集(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, positioning_interval * 3),
        )
        scheduler.add_job(
            lambda: self._run_collection_job(
                source_name="basis",
                job_name="basis_async_scheduler",
                func=self.basis_collector.collect,
                metadata={"mode": "async_scheduler"},
            ),
            "interval",
            seconds=basis_interval,
            id="basis",
            name="basis 计算(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, basis_interval * 3),
        )
        scheduler.add_job(
            self.cleanup_historical_data,
            "interval",
            seconds=cleanup_interval,
            id="exchange_cleanup",
            name="交易所高频快照清理(async)",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(300, cleanup_interval),
        )
        return scheduler

    def close(self):
        self.client_manager.close_all()
        self.db.close()
