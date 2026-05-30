from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from database.db_manager import DBManager
from data_layer.exchange_data.service import ExchangeDataService


class MarketStructureService:
    """基于真实交易所快照重组市场结构证据。"""

    CORE_SECTIONS = (
        "spot",
        "orderbook",
        "funding",
        "trade_flow",
        "open_interest",
        "basis",
    )
    OPTIONAL_SECTIONS = ("liquidations", "long_short_ratio")
    MINIMUM_EXCHANGE_COUNT_FOR_CROSS_SECTION = 2
    RAW_SOURCE_KEY_BY_SECTION = {
        "spot": "ticker",
        "orderbook": "orderbook",
        "funding": "funding",
        "trade_flow": "trade_flow",
        "open_interest": "open_interest",
        "liquidations": "liquidations",
        "positioning": "long_short_ratio",
        "basis": "basis",
    }
    SECTION_ALIASES = {
        "spot": "spot",
        "orderbook": "orderbook",
        "funding": "funding",
        "trade_flow": "trade_flow",
        "trade_flow_spot": "trade_flow",
        "trade_flow_derivatives": "trade_flow",
        "open_interest": "open_interest",
        "liquidations": "liquidations",
        "positioning": "positioning",
        "long_short_ratio": "positioning",
        "basis": "basis",
    }

    def __init__(
        self,
        db: DBManager | None = None,
        exchange_service: ExchangeDataService | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.exchange_service = exchange_service or ExchangeDataService(db=self.db)

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

    @classmethod
    def _normalize_asset_from_symbol(cls, symbol: str | None) -> str | None:
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

    @classmethod
    def _normalize_asset_keys(cls, asset_keys: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for asset_key in asset_keys or []:
            asset = cls._normalize_asset_from_symbol(asset_key)
            if not asset or asset in seen:
                continue
            seen.add(asset)
            normalized.append(asset)
        return normalized

    @staticmethod
    def _round(value: float | None, digits: int = 4) -> float | None:
        if value is None:
            return None
        return round(float(value), digits)

    @classmethod
    def _mean(cls, values: list[float | None], digits: int = 8) -> float | None:
        usable = [float(value) for value in values if value is not None]
        if not usable:
            return None
        return round(sum(usable) / len(usable), digits)

    @classmethod
    def _sum(cls, values: list[float | None], digits: int = 4) -> float | None:
        usable = [float(value) for value in values if value is not None]
        if not usable:
            return None
        return round(sum(usable), digits)

    @staticmethod
    def _exchange_names(rows: list[dict]) -> list[str]:
        return sorted(
            {
                str(row.get("exchange") or "").strip().lower()
                for row in rows
                if str(row.get("exchange") or "").strip()
            }
        )

    @staticmethod
    def _count_signs(values: list[float | None]) -> dict[str, int]:
        positive = 0
        negative = 0
        neutral = 0
        for value in values:
            if value is None:
                continue
            if value > 0:
                positive += 1
            elif value < 0:
                negative += 1
            else:
                neutral += 1
        return {
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
        }

    @staticmethod
    def _dedupe_texts(values: list[str]) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results

    @classmethod
    def _normalize_section_name(cls, section_name: str | None) -> str | None:
        if not section_name:
            return None
        return cls.SECTION_ALIASES.get(str(section_name).strip(), str(section_name).strip())

    @classmethod
    def _normalize_section_set(cls, section_names: list[str] | None) -> set[str]:
        normalized: set[str] = set()
        for section_name in section_names or []:
            normalized_name = cls._normalize_section_name(section_name)
            if normalized_name:
                normalized.add(normalized_name)
        return normalized

    def _visible_section_row_counts(self, symbol_entry: dict) -> dict[str, int]:
        trade_flow_row_count = int(len(symbol_entry.get("trade_flow") or []))
        if trade_flow_row_count <= 0:
            trade_flow_row_count = int(
                len(symbol_entry.get("trade_flow_spot") or [])
                + len(symbol_entry.get("trade_flow_derivatives") or [])
            )
        return {
            "spot": len(symbol_entry.get("spot") or []),
            "orderbook": len(symbol_entry.get("orderbook") or []),
            "funding": len(symbol_entry.get("funding") or []),
            "trade_flow": trade_flow_row_count,
            "open_interest": len(symbol_entry.get("open_interest") or []),
            "liquidations": len(symbol_entry.get("liquidations") or []),
            "positioning": len(symbol_entry.get("positioning") or []),
            "basis": len(symbol_entry.get("basis") or []),
        }

    def _build_ai_visible_coverage_summary(self, symbol_entry: dict) -> dict[str, object]:
        raw_coverage_summary = dict(symbol_entry.get("coverage_summary") or {})
        raw_section_statuses = dict(raw_coverage_summary.get("section_statuses") or {})
        raw_source_counts = dict(symbol_entry.get("raw_source_counts") or {})
        visible_row_counts = self._visible_section_row_counts(symbol_entry)

        visible_sections = sorted(
            section_name
            for section_name, row_count in visible_row_counts.items()
            if int(row_count or 0) > 0
        )
        visible_core_sections = [
            section_name
            for section_name in self.CORE_SECTIONS
            if int(visible_row_counts.get(section_name) or 0) > 0
        ]
        visible_optional_sections = [
            section_name
            for section_name in ("liquidations", "positioning")
            if int(visible_row_counts.get(section_name) or 0) > 0
        ]
        missing_visible_core_sections = [
            section_name
            for section_name in self.CORE_SECTIONS
            if int(visible_row_counts.get(section_name) or 0) <= 0
        ]
        missing_visible_optional_sections = [
            section_name
            for section_name in ("liquidations", "positioning")
            if int(visible_row_counts.get(section_name) or 0) <= 0
        ]
        configured_sections = sorted(
            self._normalize_section_set(
                [
                    section_name
                    for section_name, status in raw_section_statuses.items()
                    if status.get("configured")
                ]
            )
        )
        unconfigured_sections = sorted(
            self._normalize_section_set(raw_coverage_summary.get("unconfigured_sections") or [])
        )
        raw_present_missing_core_sections = [
            section_name
            for section_name in missing_visible_core_sections
            if int(raw_source_counts.get(self.RAW_SOURCE_KEY_BY_SECTION[section_name]) or 0) > 0
        ]
        raw_present_missing_optional_sections = [
            section_name
            for section_name in missing_visible_optional_sections
            if int(raw_source_counts.get(self.RAW_SOURCE_KEY_BY_SECTION[section_name]) or 0) > 0
        ]

        return {
            "configured_sections": configured_sections,
            "configured_core_sections": [
                section_name
                for section_name in self.CORE_SECTIONS
                if section_name in configured_sections
            ],
            "configured_optional_sections": [
                section_name
                for section_name in ("liquidations", "positioning")
                if section_name in configured_sections
            ],
            "visible_row_counts": visible_row_counts,
            "visible_section_count": len(visible_sections),
            "visible_sections": visible_sections,
            "visible_core_sections": visible_core_sections,
            "visible_optional_sections": visible_optional_sections,
            "missing_visible_core_sections": missing_visible_core_sections,
            "missing_visible_optional_sections": missing_visible_optional_sections,
            "raw_present_missing_core_sections": raw_present_missing_core_sections,
            "raw_present_missing_optional_sections": raw_present_missing_optional_sections,
            "configured_section_count": len(configured_sections),
            "configured_core_section_count": len(
                [
                    section_name
                    for section_name in self.CORE_SECTIONS
                    if section_name in configured_sections
                ]
            ),
            "visible_core_section_ratio": round(
                len(visible_core_sections) / max(len(self.CORE_SECTIONS), 1),
                4,
            ),
            "visible_optional_section_ratio": round(
                len(visible_optional_sections) / max(len(self.OPTIONAL_SECTIONS), 1),
                4,
            ),
            "unconfigured_sections": unconfigured_sections,
        }

    def _build_trade_flow_context(self, symbol_entry: dict) -> dict:
        spot_rows = list(symbol_entry.get("trade_flow_spot") or [])
        derivatives_rows = list(symbol_entry.get("trade_flow_derivatives") or [])
        all_rows = (
            spot_rows + derivatives_rows
            if (spot_rows or derivatives_rows)
            else list(symbol_entry.get("trade_flow") or [])
        )
        buy_notional = [self._safe_float(row.get("buy_notional")) for row in all_rows]
        sell_notional = [self._safe_float(row.get("sell_notional")) for row in all_rows]
        aggressive_buy = [
            self._safe_float(row.get("aggressive_buy_notional"))
            for row in all_rows
        ]
        aggressive_sell = [
            self._safe_float(row.get("aggressive_sell_notional"))
            for row in all_rows
        ]
        net_taker = [self._safe_float(row.get("net_taker_notional")) for row in all_rows]
        cvd_values = [self._safe_float(row.get("cvd")) for row in all_rows]
        aggressive_total = sum(
            value
            for value in (
                *(value for value in aggressive_buy if value is not None),
                *(value for value in aggressive_sell if value is not None),
            )
        )
        aggressive_buy_share = (
            round(
                sum(value for value in aggressive_buy if value is not None) / aggressive_total,
                4,
            )
            if aggressive_total > 0
            else None
        )
        return {
            "trade_flow_scope": str(symbol_entry.get("trade_flow_scope") or "missing"),
            "exchange_names": self._exchange_names(all_rows),
            "exchange_count": len(self._exchange_names(all_rows)),
            "row_count": len(all_rows),
            "spot_row_count": len(spot_rows),
            "derivatives_row_count": len(derivatives_rows),
            "buy_notional_sum": self._sum(buy_notional),
            "sell_notional_sum": self._sum(sell_notional),
            "aggressive_buy_notional_sum": self._sum(aggressive_buy),
            "aggressive_sell_notional_sum": self._sum(aggressive_sell),
            "net_taker_notional_sum": self._sum(net_taker),
            "cvd_sum": self._sum(cvd_values),
            "aggressive_buy_share": aggressive_buy_share,
        }

    def _build_funding_context(
        self,
        symbol_entry: dict,
        cross_exchange_diagnostics: dict,
    ) -> dict:
        rows = list(symbol_entry.get("funding") or [])
        funding_values = [self._safe_float(row.get("funding_rate")) for row in rows]
        mark_prices = [self._safe_float(row.get("mark_price")) for row in rows]
        return {
            "exchange_names": self._exchange_names(rows),
            "exchange_count": len(self._exchange_names(rows)),
            "row_count": len(rows),
            "average_funding_rate": self._mean(funding_values, digits=8),
            "max_funding_rate": max(
                (value for value in funding_values if value is not None),
                default=None,
            ),
            "min_funding_rate": min(
                (value for value in funding_values if value is not None),
                default=None,
            ),
            "average_mark_price": self._mean(mark_prices),
            "mark_price_dispersion_bps": self._round(
                self._safe_float(cross_exchange_diagnostics.get("funding_mark_price_range_bps"))
            ),
            **self._count_signs(funding_values),
        }

    def _build_basis_context(
        self,
        symbol_entry: dict,
        cross_exchange_diagnostics: dict,
    ) -> dict:
        rows = list(symbol_entry.get("basis") or [])
        basis_values = [self._safe_float(row.get("basis_bps")) for row in rows]
        annualized_values = [
            self._safe_float(row.get("annualized_basis_bps"))
            for row in rows
        ]
        missing_spot_price_count = sum(
            1
            for row in rows
            if row.get("spot_price") in (None, 0)
        )
        return {
            "exchange_names": self._exchange_names(rows),
            "exchange_count": len(self._exchange_names(rows)),
            "row_count": len(rows),
            "average_basis_bps": self._mean(basis_values),
            "average_annualized_basis_bps": self._mean(annualized_values),
            "max_abs_basis_bps": max(
                (abs(value) for value in basis_values if value is not None),
                default=None,
            ),
            "basis_dispersion_bps": self._round(
                self._safe_float(cross_exchange_diagnostics.get("basis_range_bps"))
            ),
            "missing_spot_price_count": missing_spot_price_count,
            **self._count_signs(basis_values),
        }

    def _build_open_interest_context(self, symbol_entry: dict) -> dict:
        rows = list(symbol_entry.get("open_interest") or [])
        oi_usd_values = [self._safe_float(row.get("open_interest_usd")) for row in rows]
        oi_contract_values = [
            self._safe_float(row.get("open_interest_contracts"))
            for row in rows
        ]
        total_oi_usd = self._sum(oi_usd_values)
        largest_exchange_share = None
        usable_oi_usd = [value for value in oi_usd_values if value is not None]
        if usable_oi_usd and total_oi_usd and total_oi_usd > 0:
            largest_exchange_share = round(max(usable_oi_usd) / total_oi_usd, 4)
        return {
            "exchange_names": self._exchange_names(rows),
            "exchange_count": len(self._exchange_names(rows)),
            "row_count": len(rows),
            "total_open_interest_usd": total_oi_usd,
            "total_open_interest_contracts": self._sum(oi_contract_values),
            "open_interest_change_5m_sum": self._sum(
                [self._safe_float(row.get("open_interest_change_5m")) for row in rows]
            ),
            "open_interest_change_1h_sum": self._sum(
                [self._safe_float(row.get("open_interest_change_1h")) for row in rows]
            ),
            "open_interest_change_24h_sum": self._sum(
                [self._safe_float(row.get("open_interest_change_24h")) for row in rows]
            ),
            "largest_exchange_share": largest_exchange_share,
        }

    def _build_liquidation_context(self, symbol_entry: dict) -> dict:
        rows = list(symbol_entry.get("liquidations") or [])
        total = self._sum(
            [self._safe_float(row.get("total_liquidation_notional")) for row in rows]
        )
        total_long = self._sum(
            [self._safe_float(row.get("long_liquidation_notional")) for row in rows]
        )
        total_short = self._sum(
            [self._safe_float(row.get("short_liquidation_notional")) for row in rows]
        )
        long_share = None
        short_share = None
        if total and total > 0:
            long_share = round(float(total_long or 0.0) / total, 4)
            short_share = round(float(total_short or 0.0) / total, 4)
        return {
            "exchange_names": self._exchange_names(rows),
            "exchange_count": len(self._exchange_names(rows)),
            "row_count": len(rows),
            "total_liquidation_notional": total,
            "total_long_liquidation_notional": total_long,
            "total_short_liquidation_notional": total_short,
            "long_liquidation_share": long_share,
            "short_liquidation_share": short_share,
            "max_single_liquidation_notional": max(
                (
                    self._safe_float(row.get("max_single_liquidation_notional"))
                    for row in rows
                    if self._safe_float(row.get("max_single_liquidation_notional")) is not None
                ),
                default=None,
            ),
        }

    def _build_positioning_context(self, symbol_entry: dict) -> dict:
        rows = list(symbol_entry.get("positioning") or [])
        return {
            "exchange_names": self._exchange_names(rows),
            "exchange_count": len(self._exchange_names(rows)),
            "row_count": len(rows),
            "average_long_short_ratio": self._mean(
                [self._safe_float(row.get("long_short_ratio")) for row in rows]
            ),
            "average_long_ratio": self._mean(
                [self._safe_float(row.get("long_ratio")) for row in rows]
            ),
            "average_short_ratio": self._mean(
                [self._safe_float(row.get("short_ratio")) for row in rows]
            ),
            "average_top_trader_long_ratio": self._mean(
                [self._safe_float(row.get("top_trader_long_ratio")) for row in rows]
            ),
            "average_top_trader_short_ratio": self._mean(
                [self._safe_float(row.get("top_trader_short_ratio")) for row in rows]
            ),
        }

    def _build_quality(
        self,
        *,
        symbol_entry: dict,
        asset: str,
        ai_visible_coverage_summary: dict[str, object],
        trade_flow_context: dict,
        funding_context: dict,
        basis_context: dict,
        open_interest_context: dict,
        liquidation_context: dict,
        positioning_context: dict,
    ) -> tuple[str, float, list[str], list[str]]:
        core_missing_sections = list(
            ai_visible_coverage_summary.get("missing_visible_core_sections") or []
        )
        raw_present_missing_core_sections = list(
            ai_visible_coverage_summary.get("raw_present_missing_core_sections") or []
        )
        completeness_score = round(
            float(ai_visible_coverage_summary.get("visible_core_section_ratio") or 0.0),
            4,
        )

        data_quality_flags = list(symbol_entry.get("data_quality_flags") or [])
        quality_notes = list(symbol_entry.get("quality_notes") or [])

        spot_exchange_count = len(
            self._exchange_names(list(symbol_entry.get("spot") or []))
        )
        if spot_exchange_count < self.MINIMUM_EXCHANGE_COUNT_FOR_CROSS_SECTION:
            data_quality_flags.append("market_structure_cross_exchange_thin")
            quality_notes.append(
                f"{asset} 当前只有 {spot_exchange_count} 家 spot 交易所可用于横截面对比，市场结构视角偏薄。"
            )
        if core_missing_sections:
            data_quality_flags.append("market_structure_core_section_missing")
            if raw_present_missing_core_sections:
                quality_notes.append(
                    "以下核心 section 虽然已有真实 raw 快照，但因 stale 或质量问题没有进入 AI 主视图: "
                    + ", ".join(raw_present_missing_core_sections)
                    + "。"
                )
            remaining_missing_sections = [
                section_name
                for section_name in core_missing_sections
                if section_name not in set(raw_present_missing_core_sections)
            ]
            if remaining_missing_sections:
                quality_notes.append(
                    "当前可直接给 AI 使用的核心 section 仍有缺口: "
                    + ", ".join(remaining_missing_sections)
                    + "。"
                )
        if str(trade_flow_context.get("trade_flow_scope") or "") == "spot_only":
            data_quality_flags.append("market_structure_trade_flow_derivatives_missing")
            quality_notes.append(
                "trade_flow 当前只有 spot 维度，没有可直接用于杠杆交易解读的 derivatives 成交流。"
            )
        if int(liquidation_context.get("row_count") or 0) == 0:
            data_quality_flags.append("market_structure_liquidations_missing")
            quality_notes.append("当前缺少真实清算快照，杠杆踩踏证据不完整。")
        if int(positioning_context.get("row_count") or 0) == 0:
            data_quality_flags.append("market_structure_positioning_missing")
            quality_notes.append("当前缺少真实多空定位快照，拥挤方向证据不完整。")
        if int(funding_context.get("row_count") or 0) == 0:
            data_quality_flags.append("market_structure_funding_missing")
        if int(basis_context.get("row_count") or 0) == 0:
            data_quality_flags.append("market_structure_basis_missing")
        if int(open_interest_context.get("row_count") or 0) == 0:
            data_quality_flags.append("market_structure_open_interest_missing")

        data_quality_flags = self._dedupe_texts(data_quality_flags)
        quality_notes = self._dedupe_texts(quality_notes)[:16]

        has_liquidation_context = int(liquidation_context.get("row_count") or 0) > 0
        has_positioning_context = int(positioning_context.get("row_count") or 0) > 0

        if (
            spot_exchange_count >= 2
            and not core_missing_sections
            and completeness_score >= 1.0
            and has_liquidation_context
            and has_positioning_context
        ):
            data_quality_flag = "ok"
        elif spot_exchange_count >= 1 and completeness_score >= 0.66:
            data_quality_flag = "partial"
        else:
            data_quality_flag = "thin"

        return data_quality_flag, completeness_score, data_quality_flags, quality_notes

    def build_latest_context_bundle(
        self,
        asset_keys: list[str] | None = None,
    ) -> dict:
        now = self._utc_now_naive()
        normalized_asset_keys = self._normalize_asset_keys(asset_keys)
        symbols = (
            [f"{asset}/USDT" for asset in normalized_asset_keys]
            if normalized_asset_keys
            else None
        )
        exchange_bundle = self.exchange_service.load_latest_market_context_bundle(
            symbols=symbols,
        )

        assets: list[dict[str, object]] = []
        quality_counter: Counter = Counter()
        for symbol_entry in exchange_bundle.get("symbols") or []:
            asset = self._normalize_asset_from_symbol(symbol_entry.get("symbol"))
            if not asset:
                continue
            cross_exchange_diagnostics = dict(
                symbol_entry.get("cross_exchange_diagnostics") or {}
            )
            trade_flow_context = self._build_trade_flow_context(symbol_entry)
            funding_context = self._build_funding_context(
                symbol_entry,
                cross_exchange_diagnostics,
            )
            basis_context = self._build_basis_context(
                symbol_entry,
                cross_exchange_diagnostics,
            )
            open_interest_context = self._build_open_interest_context(symbol_entry)
            liquidation_context = self._build_liquidation_context(symbol_entry)
            positioning_context = self._build_positioning_context(symbol_entry)
            ai_visible_coverage_summary = self._build_ai_visible_coverage_summary(symbol_entry)
            (
                data_quality_flag,
                completeness_score,
                data_quality_flags,
                quality_notes,
            ) = self._build_quality(
                symbol_entry=symbol_entry,
                asset=asset,
                ai_visible_coverage_summary=ai_visible_coverage_summary,
                trade_flow_context=trade_flow_context,
                funding_context=funding_context,
                basis_context=basis_context,
                open_interest_context=open_interest_context,
                liquidation_context=liquidation_context,
                positioning_context=positioning_context,
            )
            quality_counter[data_quality_flag] += 1
            assets.append(
                {
                    "asset": asset,
                    "symbol": symbol_entry.get("symbol"),
                    "trade_flow_context": trade_flow_context,
                    "funding_context": funding_context,
                    "basis_context": basis_context,
                    "open_interest_context": open_interest_context,
                    "liquidation_context": liquidation_context,
                    "positioning_context": positioning_context,
                    "cross_exchange_context": cross_exchange_diagnostics,
                    "coverage_summary": dict(symbol_entry.get("coverage_summary") or {}),
                    "ai_visible_coverage_summary": ai_visible_coverage_summary,
                    "source_counts": dict(symbol_entry.get("source_counts") or {}),
                    "raw_source_counts": dict(symbol_entry.get("raw_source_counts") or {}),
                    "ai_ready_source_names": list(symbol_entry.get("ai_ready_source_names") or []),
                    "ai_excluded_source_names": list(
                        symbol_entry.get("ai_excluded_source_names") or []
                    ),
                    "structure_completeness_score": completeness_score,
                    "data_quality_flag": data_quality_flag,
                    "data_quality_flags": data_quality_flags,
                    "quality_notes": quality_notes,
                }
            )

        assets.sort(
            key=lambda item: (
                {"ok": 0, "partial": 1, "thin": 2}.get(
                    str(item.get("data_quality_flag") or "thin"),
                    3,
                ),
                str(item.get("asset") or ""),
            )
        )
        if assets and all(item["data_quality_flag"] == "ok" for item in assets):
            bundle_quality_flag = "ok"
        elif any(item["data_quality_flag"] in {"ok", "partial"} for item in assets):
            bundle_quality_flag = "partial"
        else:
            bundle_quality_flag = "thin"

        return {
            "as_of": exchange_bundle.get("as_of") or now.isoformat(),
            "generated_at": now.isoformat(),
            "scope_kind": "filtered" if normalized_asset_keys else "default",
            "asset_count": len(assets),
            "data_quality_flag": bundle_quality_flag,
            "quality_distribution": {
                "ok_asset_count": int(quality_counter.get("ok") or 0),
                "partial_asset_count": int(quality_counter.get("partial") or 0),
                "thin_asset_count": int(quality_counter.get("thin") or 0),
            },
            "configured_universe_summary": dict(
                exchange_bundle.get("configured_universe_summary") or {}
            ),
            "source_health_summary": dict(
                exchange_bundle.get("source_health_summary") or {}
            ),
            "ai_ready_source_names": list(exchange_bundle.get("ai_ready_source_names") or []),
            "ai_excluded_source_names": list(
                exchange_bundle.get("ai_excluded_source_names") or []
            ),
            "coverage_summary": {
                "exchange_symbol_count": int(exchange_bundle.get("symbol_count") or 0),
                "exchange_row_count": int(exchange_bundle.get("row_count") or 0),
                "raw_exchange_row_count": int(exchange_bundle.get("raw_row_count") or 0),
            },
            "assets": assets,
        }

    def save_snapshot(self, bundle: dict | None = None) -> dict[str, object]:
        payload = dict(bundle or self.build_latest_context_bundle())
        snapshot_time = str(payload.get("generated_at") or self._utc_now_naive().isoformat())
        self.db.execute(
            """
            INSERT INTO market_structure_snapshots (
                snapshot_time, scope_kind, asset_count, data_quality_flag, bundle_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot_time,
                str(payload.get("scope_kind") or "default"),
                int(payload.get("asset_count") or 0),
                str(payload.get("data_quality_flag") or "thin"),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.db.commit()
        row = self.db.fetch_one(
            """
            SELECT id, snapshot_time, scope_kind, asset_count, data_quality_flag
            FROM market_structure_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else {}

    def close(self):
        self.db.close()
