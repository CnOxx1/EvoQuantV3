from __future__ import annotations

import json
from datetime import datetime
from itertools import combinations
from typing import Any, Optional

import pandas as pd

from logic_layer.exchange_comparison.models import (
    ExchangeComparisonConfig,
    ExchangeComparisonSnapshot,
)


class ExchangeComparator:
    """生成 AI 可直接消费的跨交易所状态特征。"""

    FUNDING_MARKET_TYPES = {"swap", "future", "futures", "perpetual", "contract"}

    def compare(
        self,
        aligned_snapshots: pd.DataFrame,
        config: ExchangeComparisonConfig,
        as_of: Optional[datetime] = None,
    ) -> pd.DataFrame:
        if aligned_snapshots.empty:
            return pd.DataFrame(columns=ExchangeComparisonSnapshot.TABLE_COLUMNS)

        as_of_ts = self._normalize_timestamp(as_of or pd.Timestamp.now(tz="UTC"))
        comparison_rows: list[dict[str, Any]] = []

        for symbol, symbol_frame in aligned_snapshots.groupby("symbol", sort=True):
            symbol_frame = (
                symbol_frame.sort_values("exchange")
                .drop_duplicates("exchange", keep="last")
                .reset_index(drop=True)
            )
            if len(symbol_frame) < 2:
                continue

            records = symbol_frame.to_dict("records")
            for left, right in combinations(records, 2):
                comparison_rows.append(
                    self._build_pair_snapshot(symbol, left, right, config, as_of_ts)
                )

        if not comparison_rows:
            return pd.DataFrame(columns=ExchangeComparisonSnapshot.TABLE_COLUMNS)
        return pd.DataFrame.from_records(
            comparison_rows,
            columns=ExchangeComparisonSnapshot.TABLE_COLUMNS,
        )

    def _build_pair_snapshot(
        self,
        symbol: str,
        left: dict[str, Any],
        right: dict[str, Any],
        config: ExchangeComparisonConfig,
        as_of: pd.Timestamp,
    ) -> dict[str, Any]:
        exchange_a = str(left["exchange"])
        exchange_b = str(right["exchange"])

        ticker_ts_a = self._optional_timestamp(left.get("ticker_timestamp"))
        ticker_ts_b = self._optional_timestamp(right.get("ticker_timestamp"))
        orderbook_ts_a = self._optional_timestamp(left.get("orderbook_timestamp"))
        orderbook_ts_b = self._optional_timestamp(right.get("orderbook_timestamp"))
        funding_ts_a = self._optional_timestamp(left.get("funding_timestamp"))
        funding_ts_b = self._optional_timestamp(right.get("funding_timestamp"))

        bid_a = self._coalesce(left.get("bid"), left.get("orderbook_best_bid"))
        ask_a = self._coalesce(left.get("ask"), left.get("orderbook_best_ask"))
        bid_b = self._coalesce(right.get("bid"), right.get("orderbook_best_bid"))
        ask_b = self._coalesce(right.get("ask"), right.get("orderbook_best_ask"))

        mid_a = self._coalesce(
            left.get("mid_price"),
            left.get("orderbook_mid_price"),
            self._mid_from_bid_ask(bid_a, ask_a),
        )
        mid_b = self._coalesce(
            right.get("mid_price"),
            right.get("orderbook_mid_price"),
            self._mid_from_bid_ask(bid_b, ask_b),
        )

        spread_bps_a = self._coalesce(
            left.get("spread_bps"),
            left.get("orderbook_spread_bps"),
            self._spread_bps_from_bid_ask(bid_a, ask_a),
        )
        spread_bps_b = self._coalesce(
            right.get("spread_bps"),
            right.get("orderbook_spread_bps"),
            self._spread_bps_from_bid_ask(bid_b, ask_b),
        )

        bid_depth_notional_a = self._to_float(left.get("orderbook_bid_depth_notional"))
        bid_depth_notional_b = self._to_float(right.get("orderbook_bid_depth_notional"))
        ask_depth_notional_a = self._to_float(left.get("orderbook_ask_depth_notional"))
        ask_depth_notional_b = self._to_float(right.get("orderbook_ask_depth_notional"))

        last_price_a = self._to_float(left.get("last_price"))
        last_price_b = self._to_float(right.get("last_price"))
        quote_volume_a = self._to_float(left.get("quote_volume_24h"))
        quote_volume_b = self._to_float(right.get("quote_volume_24h"))
        depth_imbalance_a = self._to_float(left.get("orderbook_depth_imbalance"))
        depth_imbalance_b = self._to_float(right.get("orderbook_depth_imbalance"))

        funding_rate_a = self._to_float(left.get("funding_rate"))
        funding_rate_b = self._to_float(right.get("funding_rate"))
        mark_price_a = self._to_float(left.get("mark_price"))
        mark_price_b = self._to_float(right.get("mark_price"))
        index_price_a = self._to_float(left.get("index_price"))
        index_price_b = self._to_float(right.get("index_price"))

        context_timeframe = self._coalesce_str(
            left.get("context_timeframe"),
            right.get("context_timeframe"),
        )
        context_open_time = self._optional_timestamp(
            left.get("context_open_time") or right.get("context_open_time")
        )
        context_close = self._coalesce(left.get("context_close"), right.get("context_close"))
        context_rsi_14 = self._coalesce(left.get("context_rsi_14"), right.get("context_rsi_14"))
        context_macd_hist = self._coalesce(
            left.get("context_macd_hist"),
            right.get("context_macd_hist"),
        )
        context_atr_pct_14 = self._coalesce(
            left.get("context_atr_pct_14"),
            right.get("context_atr_pct_14"),
        )
        context_volatility_20 = self._coalesce(
            left.get("context_volatility_20"),
            right.get("context_volatility_20"),
        )
        context_adx_14 = self._coalesce(
            left.get("context_adx_14"),
            right.get("context_adx_14"),
        )
        context_bb_width = self._coalesce(
            left.get("context_bb_width"),
            right.get("context_bb_width"),
        )
        context_price_zscore_20 = self._coalesce(
            left.get("context_price_zscore_20"),
            right.get("context_price_zscore_20"),
        )
        context_volume_ratio_20 = self._coalesce(
            left.get("context_volume_ratio_20"),
            right.get("context_volume_ratio_20"),
        )
        context_cross_exchange_last_price_range_bps = self._coalesce(
            left.get("context_cross_exchange_last_price_range_bps"),
            right.get("context_cross_exchange_last_price_range_bps"),
        )
        context_funding_basis_bps_mean = self._coalesce(
            left.get("context_funding_basis_bps_mean"),
            right.get("context_funding_basis_bps_mean"),
        )
        context_orderbook_total_depth_notional = self._coalesce(
            left.get("context_orderbook_total_depth_notional"),
            right.get("context_orderbook_total_depth_notional"),
        )
        context_age_seconds = (
            (as_of - context_open_time).total_seconds()
            if context_open_time is not None
            else None
        )

        inter_exchange_ticker_gap_ms = self._timestamp_gap_ms(ticker_ts_a, ticker_ts_b)
        inter_exchange_funding_gap_ms = self._timestamp_gap_ms(funding_ts_a, funding_ts_b)
        orderbook_gap_ms = self._timestamp_gap_ms(orderbook_ts_a, orderbook_ts_b)

        reference_price = self._average(mid_a, mid_b, last_price_a, last_price_b)
        last_diff_abs = self._difference(last_price_a, last_price_b)
        last_diff_bps = self._to_bps(last_diff_abs, self._average(last_price_a, last_price_b))
        mid_diff_abs = self._difference(mid_a, mid_b)
        mid_diff_bps = self._to_bps(mid_diff_abs, self._average(mid_a, mid_b))
        bid_diff_bps = self._to_bps(self._difference(bid_a, bid_b), self._average(bid_a, bid_b))
        ask_diff_bps = self._to_bps(self._difference(ask_a, ask_b), self._average(ask_a, ask_b))

        funding_rate_diff_abs = self._difference(funding_rate_a, funding_rate_b)
        funding_rate_diff_bps = (
            funding_rate_diff_abs * 10000.0 if funding_rate_diff_abs is not None else None
        )
        mark_price_diff_bps = self._to_bps(
            self._difference(mark_price_a, mark_price_b),
            self._average(mark_price_a, mark_price_b),
        )
        index_price_diff_bps = self._to_bps(
            self._difference(index_price_a, index_price_b),
            self._average(index_price_a, index_price_b),
        )

        cross_spread_ab_bps = self._to_bps(self._difference(bid_a, ask_b), reference_price)
        cross_spread_ba_bps = self._to_bps(self._difference(bid_b, ask_a), reference_price)

        fee_rate_a, fee_source_a = self._resolve_fee_rate(left, config)
        fee_rate_b, fee_source_b = self._resolve_fee_rate(right, config)
        estimated_fee_bps = self._to_bps(fee_rate_a + fee_rate_b, 1.0)

        slippage_ab_bps, liquidity_multiple_ab = self._estimate_directional_slippage_bps(
            sell_depth_notional=bid_depth_notional_a,
            buy_depth_notional=ask_depth_notional_b,
            sell_spread_bps=spread_bps_a,
            buy_spread_bps=spread_bps_b,
            config=config,
        )
        slippage_ba_bps, liquidity_multiple_ba = self._estimate_directional_slippage_bps(
            sell_depth_notional=bid_depth_notional_b,
            buy_depth_notional=ask_depth_notional_a,
            sell_spread_bps=spread_bps_b,
            buy_spread_bps=spread_bps_a,
            config=config,
        )

        net_ab_bps = self._net_spread_bps(
            cross_spread_ab_bps,
            estimated_fee_bps,
            slippage_ab_bps,
        )
        net_ba_bps = self._net_spread_bps(
            cross_spread_ba_bps,
            estimated_fee_bps,
            slippage_ba_bps,
        )
        net_cross_spread_max_bps = self._max_value(net_ab_bps, net_ba_bps)

        best_buy_exchange = self._best_buy_exchange(
            exchange_a,
            exchange_b,
            ask_a,
            ask_b,
            mid_a,
            mid_b,
            last_price_a,
            last_price_b,
        )
        best_sell_exchange = self._best_sell_exchange(
            exchange_a,
            exchange_b,
            bid_a,
            bid_b,
            mid_a,
            mid_b,
            last_price_a,
            last_price_b,
        )

        opportunity_type, selected_slippage_bps, selected_liquidity_multiple = (
            self._select_direction(
                exchange_a,
                exchange_b,
                net_ab_bps,
                net_ba_bps,
                slippage_ab_bps,
                slippage_ba_bps,
                liquidity_multiple_ab,
                liquidity_multiple_ba,
            )
        )

        expects_funding = self._expects_funding_context(config)
        quality_flags = self._build_quality_flags(
            ticker_ts_a=ticker_ts_a,
            ticker_ts_b=ticker_ts_b,
            orderbook_ts_a=orderbook_ts_a,
            orderbook_ts_b=orderbook_ts_b,
            funding_ts_a=funding_ts_a,
            funding_ts_b=funding_ts_b,
            context_open_time=context_open_time,
            context_age_seconds=context_age_seconds,
            bid_a=bid_a,
            ask_a=ask_a,
            bid_b=bid_b,
            ask_b=ask_b,
            inter_exchange_ticker_gap_ms=inter_exchange_ticker_gap_ms,
            inter_exchange_funding_gap_ms=inter_exchange_funding_gap_ms,
            orderbook_gap_ms=orderbook_gap_ms,
            as_of=as_of,
            config=config,
            expects_funding=expects_funding,
        )

        context_completeness_score = self._resolve_context_completeness_score(
            funding_ts_a=funding_ts_a,
            funding_ts_b=funding_ts_b,
            context_open_time=context_open_time,
            context_age_seconds=context_age_seconds,
            as_of=as_of,
            config=config,
            expects_funding=expects_funding,
        )

        market_regime_label = self._resolve_market_regime_label(
            context_rsi_14=context_rsi_14,
            context_macd_hist=context_macd_hist,
            context_atr_pct_14=context_atr_pct_14,
            context_volatility_20=context_volatility_20,
            context_adx_14=context_adx_14,
            context_price_zscore_20=context_price_zscore_20,
            config=config,
        )
        funding_regime_label = self._resolve_funding_regime_label(
            funding_rate_a=funding_rate_a,
            funding_rate_b=funding_rate_b,
            funding_rate_diff_bps=funding_rate_diff_bps,
            expects_funding=expects_funding,
            config=config,
        )

        is_actionable = bool(
            opportunity_type != "none"
            and net_cross_spread_max_bps is not None
            and net_cross_spread_max_bps >= config.min_actionable_net_spread_bps
            and selected_liquidity_multiple is not None
            and selected_liquidity_multiple >= config.liquidity_buffer_ratio
            and selected_slippage_bps is not None
            and selected_slippage_bps <= config.max_slippage_bps
            and not self._has_blocking_quality_issue(quality_flags)
        )

        signal_label = self._resolve_signal_label(
            quality_flags=quality_flags,
            gross_spread_max_bps=self._max_value(cross_spread_ab_bps, cross_spread_ba_bps),
            net_cross_spread_max_bps=net_cross_spread_max_bps,
            selected_liquidity_multiple=selected_liquidity_multiple,
            mid_diff_bps=mid_diff_bps,
            is_actionable=is_actionable,
            config=config,
        )
        signal_strength = self._resolve_signal_strength(
            signal_label=signal_label,
            net_cross_spread_max_bps=net_cross_spread_max_bps,
            gross_spread_max_bps=self._max_value(cross_spread_ab_bps, cross_spread_ba_bps),
            mid_diff_bps=mid_diff_bps,
            quality_flags=quality_flags,
            config=config,
        )
        anomaly_score = self._resolve_anomaly_score(
            mid_diff_bps=mid_diff_bps,
            funding_rate_diff_bps=funding_rate_diff_bps,
            quality_flags=quality_flags,
            selected_liquidity_multiple=selected_liquidity_multiple,
            context_age_seconds=context_age_seconds,
            config=config,
            expects_funding=expects_funding,
        )
        execution_preference_score = self._resolve_execution_preference_score(
            net_cross_spread_max_bps=net_cross_spread_max_bps,
            selected_liquidity_multiple=selected_liquidity_multiple,
            spread_bps_a=spread_bps_a,
            spread_bps_b=spread_bps_b,
            quality_flags=quality_flags,
            config=config,
        )

        comparison_timestamp = self._latest_timestamp(ticker_ts_a, ticker_ts_b) or as_of
        raw_context_json = json.dumps(
            self._json_ready(
                {
                    "as_of": as_of,
                    "quality_flags": quality_flags,
                    "fee_rate_source": {
                        exchange_a: fee_source_a,
                        exchange_b: fee_source_b,
                    },
                    "fee_rate": {
                        exchange_a: fee_rate_a,
                        exchange_b: fee_rate_b,
                    },
                    "orderbook_alignment_gap_ms": {
                        exchange_a: left.get("orderbook_alignment_gap_ms"),
                        exchange_b: right.get("orderbook_alignment_gap_ms"),
                    },
                    "funding_alignment_gap_ms": {
                        exchange_a: left.get("funding_alignment_gap_ms"),
                        exchange_b: right.get("funding_alignment_gap_ms"),
                    },
                    "indicator_context_alignment_gap_ms": self._coalesce(
                        left.get("context_alignment_gap_ms"),
                        right.get("context_alignment_gap_ms"),
                    ),
                    "liquidity_multiple": {
                        f"{exchange_a}_sell_{exchange_b}_buy": liquidity_multiple_ab,
                        f"{exchange_b}_sell_{exchange_a}_buy": liquidity_multiple_ba,
                    },
                    "selected_direction": opportunity_type,
                    "market_type": {
                        exchange_a: left.get("market_type"),
                        exchange_b: right.get("market_type"),
                    },
                    "funding_regime_label": funding_regime_label,
                    "market_regime_label": market_regime_label,
                    "context_completeness_score": context_completeness_score,
                }
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        snapshot = ExchangeComparisonSnapshot(
            symbol=symbol,
            exchange_a=exchange_a,
            exchange_b=exchange_b,
            compare_window_seconds=config.compare_window_seconds,
            timestamp=comparison_timestamp.to_pydatetime(),
            ticker_timestamp_a=ticker_ts_a.to_pydatetime() if ticker_ts_a is not None else None,
            ticker_timestamp_b=ticker_ts_b.to_pydatetime() if ticker_ts_b is not None else None,
            orderbook_timestamp_a=orderbook_ts_a.to_pydatetime() if orderbook_ts_a is not None else None,
            orderbook_timestamp_b=orderbook_ts_b.to_pydatetime() if orderbook_ts_b is not None else None,
            funding_timestamp_a=funding_ts_a.to_pydatetime() if funding_ts_a is not None else None,
            funding_timestamp_b=funding_ts_b.to_pydatetime() if funding_ts_b is not None else None,
            last_price_a=last_price_a,
            last_price_b=last_price_b,
            mid_price_a=mid_a,
            mid_price_b=mid_b,
            bid_a=bid_a,
            ask_a=ask_a,
            bid_b=bid_b,
            ask_b=ask_b,
            spread_bps_a=spread_bps_a,
            spread_bps_b=spread_bps_b,
            quote_volume_24h_a=quote_volume_a,
            quote_volume_24h_b=quote_volume_b,
            bid_depth_notional_a=bid_depth_notional_a,
            bid_depth_notional_b=bid_depth_notional_b,
            ask_depth_notional_a=ask_depth_notional_a,
            ask_depth_notional_b=ask_depth_notional_b,
            depth_imbalance_a=depth_imbalance_a,
            depth_imbalance_b=depth_imbalance_b,
            funding_rate_a=funding_rate_a,
            funding_rate_b=funding_rate_b,
            mark_price_a=mark_price_a,
            mark_price_b=mark_price_b,
            index_price_a=index_price_a,
            index_price_b=index_price_b,
            last_diff_abs=last_diff_abs,
            last_diff_bps=last_diff_bps,
            mid_diff_abs=mid_diff_abs,
            mid_diff_bps=mid_diff_bps,
            bid_diff_bps=bid_diff_bps,
            ask_diff_bps=ask_diff_bps,
            funding_rate_diff_abs=funding_rate_diff_abs,
            funding_rate_diff_bps=funding_rate_diff_bps,
            mark_price_diff_bps=mark_price_diff_bps,
            index_price_diff_bps=index_price_diff_bps,
            cross_spread_ab_bps=cross_spread_ab_bps,
            cross_spread_ba_bps=cross_spread_ba_bps,
            estimated_fee_bps=estimated_fee_bps,
            estimated_slippage_ab_bps=slippage_ab_bps,
            estimated_slippage_ba_bps=slippage_ba_bps,
            estimated_slippage_bps=selected_slippage_bps,
            net_cross_spread_ab_bps=net_ab_bps,
            net_cross_spread_ba_bps=net_ba_bps,
            net_cross_spread_max_bps=net_cross_spread_max_bps,
            quote_volume_ratio=self._safe_ratio(quote_volume_a, quote_volume_b),
            bid_depth_ratio=self._safe_ratio(bid_depth_notional_a, bid_depth_notional_b),
            ask_depth_ratio=self._safe_ratio(ask_depth_notional_a, ask_depth_notional_b),
            total_depth_ratio=self._safe_ratio(
                self._sum_values(bid_depth_notional_a, ask_depth_notional_a),
                self._sum_values(bid_depth_notional_b, ask_depth_notional_b),
            ),
            spread_bps_gap=self._difference(spread_bps_a, spread_bps_b),
            depth_imbalance_gap=self._difference(depth_imbalance_a, depth_imbalance_b),
            inter_exchange_ticker_gap_ms=inter_exchange_ticker_gap_ms,
            inter_exchange_funding_gap_ms=inter_exchange_funding_gap_ms,
            context_timeframe=context_timeframe,
            context_open_time=(
                context_open_time.to_pydatetime() if context_open_time is not None else None
            ),
            context_age_seconds=context_age_seconds,
            context_close=context_close,
            context_rsi_14=context_rsi_14,
            context_macd_hist=context_macd_hist,
            context_atr_pct_14=context_atr_pct_14,
            context_volatility_20=context_volatility_20,
            context_adx_14=context_adx_14,
            context_bb_width=context_bb_width,
            context_price_zscore_20=context_price_zscore_20,
            context_volume_ratio_20=context_volume_ratio_20,
            context_cross_exchange_last_price_range_bps=context_cross_exchange_last_price_range_bps,
            context_funding_basis_bps_mean=context_funding_basis_bps_mean,
            context_orderbook_total_depth_notional=context_orderbook_total_depth_notional,
            best_buy_exchange=best_buy_exchange,
            best_sell_exchange=best_sell_exchange,
            opportunity_type=opportunity_type,
            signal_label=signal_label,
            signal_strength=signal_strength,
            is_actionable=is_actionable,
            anomaly_score=anomaly_score,
            execution_preference_score=execution_preference_score,
            market_regime_label=market_regime_label,
            funding_regime_label=funding_regime_label,
            context_completeness_score=context_completeness_score,
            data_quality_flag="ok" if not quality_flags else "|".join(quality_flags),
            raw_context_json=raw_context_json,
        )
        return snapshot.model_dump()

    def _build_quality_flags(
        self,
        ticker_ts_a: Optional[pd.Timestamp],
        ticker_ts_b: Optional[pd.Timestamp],
        orderbook_ts_a: Optional[pd.Timestamp],
        orderbook_ts_b: Optional[pd.Timestamp],
        funding_ts_a: Optional[pd.Timestamp],
        funding_ts_b: Optional[pd.Timestamp],
        context_open_time: Optional[pd.Timestamp],
        context_age_seconds: Optional[float],
        bid_a: Optional[float],
        ask_a: Optional[float],
        bid_b: Optional[float],
        ask_b: Optional[float],
        inter_exchange_ticker_gap_ms: Optional[float],
        inter_exchange_funding_gap_ms: Optional[float],
        orderbook_gap_ms: Optional[float],
        as_of: pd.Timestamp,
        config: ExchangeComparisonConfig,
        expects_funding: bool,
    ) -> list[str]:
        flags: list[str] = []

        if ticker_ts_a is None:
            flags.append("missing_ticker_a")
        elif (as_of - ticker_ts_a).total_seconds() > config.max_ticker_age_seconds:
            flags.append("stale_ticker_a")

        if ticker_ts_b is None:
            flags.append("missing_ticker_b")
        elif (as_of - ticker_ts_b).total_seconds() > config.max_ticker_age_seconds:
            flags.append("stale_ticker_b")

        if orderbook_ts_a is None:
            flags.append("missing_orderbook_a")
        elif (as_of - orderbook_ts_a).total_seconds() > config.max_orderbook_age_seconds:
            flags.append("stale_orderbook_a")

        if orderbook_ts_b is None:
            flags.append("missing_orderbook_b")
        elif (as_of - orderbook_ts_b).total_seconds() > config.max_orderbook_age_seconds:
            flags.append("stale_orderbook_b")

        if bid_a is None or ask_a is None:
            flags.append("missing_bid_ask_a")
        if bid_b is None or ask_b is None:
            flags.append("missing_bid_ask_b")

        if (
            inter_exchange_ticker_gap_ms is not None
            and inter_exchange_ticker_gap_ms > config.compare_window_seconds * 1000
        ):
            flags.append("cross_exchange_ticker_gap")

        if (
            orderbook_gap_ms is not None
            and orderbook_gap_ms > config.compare_window_seconds * 1000
        ):
            flags.append("cross_exchange_orderbook_gap")

        if expects_funding:
            if funding_ts_a is None:
                flags.append("missing_funding_a")
            elif (as_of - funding_ts_a).total_seconds() > config.max_funding_age_seconds:
                flags.append("stale_funding_a")

            if funding_ts_b is None:
                flags.append("missing_funding_b")
            elif (as_of - funding_ts_b).total_seconds() > config.max_funding_age_seconds:
                flags.append("stale_funding_b")

            if (
                inter_exchange_funding_gap_ms is not None
                and inter_exchange_funding_gap_ms > config.funding_window_seconds * 1000
            ):
                flags.append("cross_exchange_funding_gap")

        if config.include_indicator_context:
            if context_open_time is None:
                flags.append("missing_indicator_context")
            elif (
                context_age_seconds is not None
                and context_age_seconds > config.max_indicator_age_seconds
            ):
                flags.append("stale_indicator_context")

        return flags

    @staticmethod
    def _has_blocking_quality_issue(flags: list[str]) -> bool:
        blocking_prefixes = (
            "missing_ticker",
            "stale_ticker",
            "missing_orderbook",
            "stale_orderbook",
            "missing_bid_ask",
            "cross_exchange_ticker_gap",
        )
        return any(
            flag.startswith(blocking_prefixes) or flag == "cross_exchange_ticker_gap"
            for flag in flags
        )

    def _resolve_signal_label(
        self,
        quality_flags: list[str],
        gross_spread_max_bps: Optional[float],
        net_cross_spread_max_bps: Optional[float],
        selected_liquidity_multiple: Optional[float],
        mid_diff_bps: Optional[float],
        is_actionable: bool,
        config: ExchangeComparisonConfig,
    ) -> str:
        if self._has_blocking_quality_issue(quality_flags):
            return "data_quality_warning"
        if is_actionable:
            return "tradable_spread"
        if (
            gross_spread_max_bps is not None
            and gross_spread_max_bps > 0
            and (
                selected_liquidity_multiple is None
                or selected_liquidity_multiple < config.liquidity_buffer_ratio
            )
        ):
            return "liquidity_warning"
        if mid_diff_bps is not None and abs(mid_diff_bps) >= config.divergence_alert_bps:
            return "price_divergence"
        if (
            net_cross_spread_max_bps is not None
            and net_cross_spread_max_bps > 0
            and selected_liquidity_multiple is not None
            and selected_liquidity_multiple >= config.low_liquidity_depth_ratio
        ):
            return "price_divergence"
        return "normal"

    def _resolve_signal_strength(
        self,
        signal_label: str,
        net_cross_spread_max_bps: Optional[float],
        gross_spread_max_bps: Optional[float],
        mid_diff_bps: Optional[float],
        quality_flags: list[str],
        config: ExchangeComparisonConfig,
    ) -> float:
        if signal_label == "tradable_spread":
            if net_cross_spread_max_bps is None:
                return 60.0
            return self._clamp(
                55.0
                + max(net_cross_spread_max_bps, 0.0)
                / max(config.min_actionable_net_spread_bps, 0.5)
                * 8.0,
                55.0,
                100.0,
            )
        if signal_label == "liquidity_warning":
            base = max(gross_spread_max_bps or 0.0, 0.0)
            return self._clamp(35.0 + base * 1.2, 35.0, 95.0)
        if signal_label == "price_divergence":
            return self._clamp(
                (abs(mid_diff_bps or 0.0) / max(config.divergence_alert_bps, 1.0)) * 60.0,
                20.0,
                100.0,
            )
        if signal_label == "data_quality_warning":
            return self._clamp(20.0 + len(quality_flags) * 12.0, 20.0, 100.0)
        return self._clamp(abs(mid_diff_bps or 0.0), 0.0, 25.0)

    def _resolve_anomaly_score(
        self,
        mid_diff_bps: Optional[float],
        funding_rate_diff_bps: Optional[float],
        quality_flags: list[str],
        selected_liquidity_multiple: Optional[float],
        context_age_seconds: Optional[float],
        config: ExchangeComparisonConfig,
        expects_funding: bool,
    ) -> float:
        score = 0.0
        if mid_diff_bps is not None:
            score += min(
                abs(mid_diff_bps) / max(config.anomaly_alert_bps, 1.0) * 55.0,
                55.0,
            )
        if expects_funding and funding_rate_diff_bps is not None:
            score += min(
                abs(funding_rate_diff_bps)
                / max(config.funding_divergence_alert_bps, 1.0)
                * 20.0,
                20.0,
            )
        if selected_liquidity_multiple is not None and selected_liquidity_multiple < 1.0:
            score += min((1.0 - selected_liquidity_multiple) * 15.0, 15.0)
        if context_age_seconds is not None and context_age_seconds > config.max_indicator_age_seconds:
            score += 5.0
        score += min(len(quality_flags) * 6.0, 30.0)
        return self._clamp(score, 0.0, 100.0)

    def _resolve_execution_preference_score(
        self,
        net_cross_spread_max_bps: Optional[float],
        selected_liquidity_multiple: Optional[float],
        spread_bps_a: Optional[float],
        spread_bps_b: Optional[float],
        quality_flags: list[str],
        config: ExchangeComparisonConfig,
    ) -> float:
        profitability_component = 0.0
        if net_cross_spread_max_bps is not None:
            profitability_component = self._clamp(
                (net_cross_spread_max_bps + config.min_actionable_net_spread_bps)
                / max(config.min_actionable_net_spread_bps * 8.0, 1.0),
                0.0,
                1.0,
            )
        liquidity_component = 0.0
        if selected_liquidity_multiple is not None:
            liquidity_component = self._clamp(
                selected_liquidity_multiple / max(config.liquidity_buffer_ratio, 0.1),
                0.0,
                1.0,
            )
        spread_component = 1.0 - self._clamp(
            (self._average(spread_bps_a, spread_bps_b) or 0.0) / 20.0,
            0.0,
            1.0,
        )
        quality_component = 0.0 if self._has_blocking_quality_issue(quality_flags) else 1.0
        score = 100.0 * (
            profitability_component * 0.4
            + liquidity_component * 0.3
            + spread_component * 0.15
            + quality_component * 0.15
        )
        return self._clamp(score, 0.0, 100.0)

    def _resolve_context_completeness_score(
        self,
        funding_ts_a: Optional[pd.Timestamp],
        funding_ts_b: Optional[pd.Timestamp],
        context_open_time: Optional[pd.Timestamp],
        context_age_seconds: Optional[float],
        as_of: pd.Timestamp,
        config: ExchangeComparisonConfig,
        expects_funding: bool,
    ) -> float:
        components: list[float] = []

        if config.include_indicator_context:
            components.append(
                1.0
                if context_open_time is not None
                and context_age_seconds is not None
                and context_age_seconds <= config.max_indicator_age_seconds
                else 0.0
            )

        if expects_funding:
            components.append(
                1.0
                if funding_ts_a is not None
                and (as_of - funding_ts_a).total_seconds() <= config.max_funding_age_seconds
                else 0.0
            )
            components.append(
                1.0
                if funding_ts_b is not None
                and (as_of - funding_ts_b).total_seconds() <= config.max_funding_age_seconds
                else 0.0
            )

        if not components:
            return 100.0
        return round(sum(components) / len(components) * 100.0, 4)

    def _resolve_market_regime_label(
        self,
        context_rsi_14: Optional[float],
        context_macd_hist: Optional[float],
        context_atr_pct_14: Optional[float],
        context_volatility_20: Optional[float],
        context_adx_14: Optional[float],
        context_price_zscore_20: Optional[float],
        config: ExchangeComparisonConfig,
    ) -> str:
        if (
            context_adx_14 is not None
            and context_macd_hist is not None
            and context_rsi_14 is not None
        ):
            if (
                context_adx_14 >= config.trend_adx_threshold
                and context_macd_hist > 0
                and context_rsi_14 >= 55
            ):
                return "trend_up"
            if (
                context_adx_14 >= config.trend_adx_threshold
                and context_macd_hist < 0
                and context_rsi_14 <= 45
            ):
                return "trend_down"

        if context_atr_pct_14 is not None and context_atr_pct_14 >= config.high_volatility_atr_pct:
            return "high_volatility"

        if (
            context_price_zscore_20 is not None
            and abs(context_price_zscore_20) >= config.extreme_price_zscore
        ):
            return "stretched"

        if context_volatility_20 is not None and context_volatility_20 >= 0.03:
            return "high_volatility"

        if any(
            value is not None
            for value in [
                context_rsi_14,
                context_macd_hist,
                context_atr_pct_14,
                context_volatility_20,
                context_adx_14,
                context_price_zscore_20,
            ]
        ):
            return "range"
        return "unknown"

    def _resolve_funding_regime_label(
        self,
        funding_rate_a: Optional[float],
        funding_rate_b: Optional[float],
        funding_rate_diff_bps: Optional[float],
        expects_funding: bool,
        config: ExchangeComparisonConfig,
    ) -> str:
        if not expects_funding:
            return "not_applicable"
        if funding_rate_a is None or funding_rate_b is None:
            return "unknown"
        if (
            funding_rate_a * funding_rate_b < 0
            and funding_rate_diff_bps is not None
            and abs(funding_rate_diff_bps) >= config.funding_divergence_alert_bps
        ):
            return "funding_direction_conflict"
        if (
            funding_rate_diff_bps is not None
            and abs(funding_rate_diff_bps) >= config.funding_divergence_alert_bps
        ):
            return "funding_divergence"

        funding_mean = (funding_rate_a + funding_rate_b) / 2.0
        if funding_mean > 0:
            return "long_crowded"
        if funding_mean < 0:
            return "short_crowded"
        return "neutral"

    @staticmethod
    def _expects_funding_context(config: ExchangeComparisonConfig) -> bool:
        return (
            config.include_funding_context
            and str(config.market_type).lower() in ExchangeComparator.FUNDING_MARKET_TYPES
        )

    def _select_direction(
        self,
        exchange_a: str,
        exchange_b: str,
        net_ab_bps: Optional[float],
        net_ba_bps: Optional[float],
        slippage_ab_bps: Optional[float],
        slippage_ba_bps: Optional[float],
        liquidity_multiple_ab: Optional[float],
        liquidity_multiple_ba: Optional[float],
    ) -> tuple[str, Optional[float], Optional[float]]:
        if net_ab_bps is None and net_ba_bps is None:
            return "none", None, None
        if net_ba_bps is None or (net_ab_bps is not None and net_ab_bps >= net_ba_bps):
            if net_ab_bps is not None and net_ab_bps > 0:
                return f"sell_{exchange_a}_buy_{exchange_b}", slippage_ab_bps, liquidity_multiple_ab
            if net_ba_bps is not None and net_ba_bps > 0:
                return f"sell_{exchange_b}_buy_{exchange_a}", slippage_ba_bps, liquidity_multiple_ba
            return "none", slippage_ab_bps, liquidity_multiple_ab
        if net_ba_bps > 0:
            return f"sell_{exchange_b}_buy_{exchange_a}", slippage_ba_bps, liquidity_multiple_ba
        return "none", slippage_ba_bps, liquidity_multiple_ba

    def _estimate_directional_slippage_bps(
        self,
        sell_depth_notional: Optional[float],
        buy_depth_notional: Optional[float],
        sell_spread_bps: Optional[float],
        buy_spread_bps: Optional[float],
        config: ExchangeComparisonConfig,
    ) -> tuple[Optional[float], Optional[float]]:
        min_depth = self._min_value(sell_depth_notional, buy_depth_notional)
        if min_depth is None:
            return None, None

        liquidity_multiple = min_depth / config.target_notional
        sell_pressure = config.target_notional / max(sell_depth_notional or 0.0, 1e-9)
        buy_pressure = config.target_notional / max(buy_depth_notional or 0.0, 1e-9)
        spread_penalty = (self._average(sell_spread_bps, buy_spread_bps) or 0.0) * 0.15
        depth_penalty = max(sell_pressure - 1.0, 0.0) * 10.0 + max(buy_pressure - 1.0, 0.0) * 10.0

        if liquidity_multiple < config.liquidity_buffer_ratio:
            depth_penalty += (
                (config.liquidity_buffer_ratio - liquidity_multiple)
                / max(config.liquidity_buffer_ratio, 0.1)
                * 8.0
            )

        return self._clamp(spread_penalty + depth_penalty, 0.0, 100.0), liquidity_multiple

    @staticmethod
    def _resolve_fee_rate(
        snapshot: dict[str, Any],
        config: ExchangeComparisonConfig,
    ) -> tuple[float, str]:
        taker_fee = snapshot.get("taker_fee")
        maker_fee = snapshot.get("maker_fee")
        if taker_fee is not None and not pd.isna(taker_fee):
            return float(taker_fee), "taker_fee"
        if maker_fee is not None and not pd.isna(maker_fee):
            return float(maker_fee), "maker_fee_fallback"
        return config.default_taker_fee_rate, "config_default"

    @staticmethod
    def _best_buy_exchange(
        exchange_a: str,
        exchange_b: str,
        ask_a: Optional[float],
        ask_b: Optional[float],
        mid_a: Optional[float],
        mid_b: Optional[float],
        last_price_a: Optional[float],
        last_price_b: Optional[float],
    ) -> Optional[str]:
        buy_price_a = ExchangeComparator._coalesce(ask_a, mid_a, last_price_a)
        buy_price_b = ExchangeComparator._coalesce(ask_b, mid_b, last_price_b)
        if buy_price_a is None and buy_price_b is None:
            return None
        if buy_price_b is None or (buy_price_a is not None and buy_price_a <= buy_price_b):
            return exchange_a
        return exchange_b

    @staticmethod
    def _best_sell_exchange(
        exchange_a: str,
        exchange_b: str,
        bid_a: Optional[float],
        bid_b: Optional[float],
        mid_a: Optional[float],
        mid_b: Optional[float],
        last_price_a: Optional[float],
        last_price_b: Optional[float],
    ) -> Optional[str]:
        sell_price_a = ExchangeComparator._coalesce(bid_a, mid_a, last_price_a)
        sell_price_b = ExchangeComparator._coalesce(bid_b, mid_b, last_price_b)
        if sell_price_a is None and sell_price_b is None:
            return None
        if sell_price_b is None or (sell_price_a is not None and sell_price_a >= sell_price_b):
            return exchange_a
        return exchange_b

    @staticmethod
    def _net_spread_bps(
        cross_spread_bps: Optional[float],
        fee_bps: Optional[float],
        slippage_bps: Optional[float],
    ) -> Optional[float]:
        if cross_spread_bps is None:
            return None
        return cross_spread_bps - (fee_bps or 0.0) - (slippage_bps or 0.0)

    @staticmethod
    def _coalesce(*values):
        for value in values:
            if value is None or pd.isna(value):
                continue
            return float(value)
        return None

    @staticmethod
    def _coalesce_str(*values) -> Optional[str]:
        for value in values:
            if value is None or pd.isna(value):
                continue
            return str(value)
        return None

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _difference(left: Optional[float], right: Optional[float]) -> Optional[float]:
        if left is None or right is None:
            return None
        return left - right

    @staticmethod
    def _average(*values: Optional[float]) -> Optional[float]:
        valid_values = [float(value) for value in values if value is not None]
        if not valid_values:
            return None
        return sum(valid_values) / len(valid_values)

    @staticmethod
    def _sum_values(*values: Optional[float]) -> Optional[float]:
        valid_values = [float(value) for value in values if value is not None]
        if not valid_values:
            return None
        return sum(valid_values)

    @staticmethod
    def _mid_from_bid_ask(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0

    @staticmethod
    def _spread_bps_from_bid_ask(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
        mid_price = ExchangeComparator._mid_from_bid_ask(bid, ask)
        if mid_price in (None, 0):
            return None
        return (ask - bid) / mid_price * 10000.0

    @staticmethod
    def _to_bps(value: Optional[float], reference: Optional[float]) -> Optional[float]:
        if value is None or reference in (None, 0):
            return None
        return value / reference * 10000.0

    @staticmethod
    def _safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator in (None, 0):
            return None
        return numerator / denominator

    @staticmethod
    def _max_value(*values: Optional[float]) -> Optional[float]:
        valid_values = [float(value) for value in values if value is not None]
        if not valid_values:
            return None
        return max(valid_values)

    @staticmethod
    def _min_value(*values: Optional[float]) -> Optional[float]:
        valid_values = [float(value) for value in values if value is not None]
        if not valid_values:
            return None
        return min(valid_values)

    @staticmethod
    def _latest_timestamp(*values: Optional[pd.Timestamp]) -> Optional[pd.Timestamp]:
        valid_values = [value for value in values if value is not None]
        if not valid_values:
            return None
        return max(valid_values)

    @staticmethod
    def _optional_timestamp(value) -> Optional[pd.Timestamp]:
        if value is None or pd.isna(value):
            return None
        return ExchangeComparator._normalize_timestamp(value)

    @staticmethod
    def _timestamp_gap_ms(
        left: Optional[pd.Timestamp],
        right: Optional[pd.Timestamp],
    ) -> Optional[float]:
        if left is None or right is None:
            return None
        return abs((left - right).total_seconds()) * 1000.0

    @staticmethod
    def _normalize_timestamp(value) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return timestamp

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    def _json_ready(self, value):
        if isinstance(value, dict):
            return {key: self._json_ready(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_ready(item) for item in value]
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        if value is None:
            return None
        if isinstance(value, (bool, int, float, str)):
            if isinstance(value, float) and pd.isna(value):
                return None
            return value
        if pd.isna(value):
            return None
        return value
