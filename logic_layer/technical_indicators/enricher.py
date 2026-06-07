from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import SCHEDULER_CONFIG
from logic_layer.technical_indicators.utils import timeframe_to_timedelta


class MarketFeatureEnricher:
    """将 ticker / funding / orderbook 快照并入技术指标特征表。"""

    TICKER_MAX_CONTEXT_AGE_SECONDS = max(15, int(SCHEDULER_CONFIG["ticker_interval"]) * 3)
    ORDERBOOK_MAX_CONTEXT_AGE_SECONDS = max(
        15,
        int(SCHEDULER_CONFIG["orderbook_interval"]) * 3,
    )
    FUNDING_MAX_CONTEXT_AGE_SECONDS = max(
        60,
        int(SCHEDULER_CONFIG["funding_interval"]) * 3,
    )

    CONTEXT_COLUMNS = [
        "ticker_exchange_count",
        "ticker_last_price_mean",
        "ticker_mid_price_mean",
        "ticker_spread_bps_mean",
        "ticker_quote_volume_24h_sum",
        "ticker_quote_volume_24h_mean",
        "ticker_change_24h_mean",
        "ticker_vwap_24h_mean",
        "cross_exchange_last_price_std",
        "cross_exchange_last_price_range_bps",
        "funding_exchange_count",
        "funding_rate_mean",
        "funding_rate_std",
        "funding_basis_bps_mean",
        "orderbook_exchange_count",
        "orderbook_mid_price_mean",
        "orderbook_spread_bps_mean",
        "orderbook_bid_depth_notional_sum",
        "orderbook_ask_depth_notional_sum",
        "orderbook_total_depth_notional",
        "orderbook_depth_imbalance_mean",
    ]
    CONTEXT_QUALITY_COLUMNS = [
        "ticker_context_status",
        "ticker_context_known_exchange_count",
        "ticker_context_raw_exchange_count",
        "ticker_context_fresh_exchange_count",
        "ticker_context_stale_exchange_count",
        "ticker_context_missing_exchange_count",
        "ticker_context_fresh_exchange_ratio",
        "funding_context_status",
        "funding_context_known_exchange_count",
        "funding_context_raw_exchange_count",
        "funding_context_fresh_exchange_count",
        "funding_context_stale_exchange_count",
        "funding_context_missing_exchange_count",
        "funding_context_fresh_exchange_ratio",
        "orderbook_context_status",
        "orderbook_context_known_exchange_count",
        "orderbook_context_raw_exchange_count",
        "orderbook_context_fresh_exchange_count",
        "orderbook_context_stale_exchange_count",
        "orderbook_context_missing_exchange_count",
        "orderbook_context_fresh_exchange_ratio",
        "market_context_quality_flag",
        "market_context_quality_flags",
        "market_context_ready_source_count",
        "market_context_partial_source_count",
        "market_context_stale_only_source_count",
        "market_context_missing_source_count",
    ]
    TEXT_CONTEXT_QUALITY_COLUMNS = {
        "ticker_context_status",
        "funding_context_status",
        "orderbook_context_status",
        "market_context_quality_flag",
        "market_context_quality_flags",
    }

    def enrich(
        self,
        indicators: pd.DataFrame,
        tickers: pd.DataFrame,
        funding_rates: pd.DataFrame,
        orderbooks: pd.DataFrame,
    ) -> pd.DataFrame:
        if indicators.empty:
            return self._ensure_columns(indicators.copy())

        frame = indicators.copy()
        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
        frame["candle_close_time"] = frame["open_time"]
        for timeframe in frame["timeframe"].dropna().unique():
            mask = frame["timeframe"] == timeframe
            frame.loc[mask, "candle_close_time"] = (
                frame.loc[mask, "open_time"] + timeframe_to_timedelta(timeframe)
            )
        frame["candle_close_time"] = pd.to_datetime(
            frame["candle_close_time"],
            utc=True,
            errors="coerce",
        )

        tickers = self._prepare_tickers(tickers)
        funding_rates = self._prepare_funding_rates(funding_rates)
        orderbooks = self._prepare_orderbooks(orderbooks)

        # v4.5.0: 预分组辅助 DataFrame，避免 groupby 内部逐次 boolean mask 过滤
        _ticker_groups = dict(iter(tickers.groupby("symbol"))) if not tickers.empty else {}
        _funding_groups = dict(iter(funding_rates.groupby("symbol"))) if not funding_rates.empty else {}
        _orderbook_groups = dict(iter(orderbooks.groupby("symbol"))) if not orderbooks.empty else {}
        _empty_tickers = tickers.iloc[:0]
        _empty_funding = funding_rates.iloc[:0]
        _empty_orderbooks = orderbooks.iloc[:0]

        enriched_groups: list[pd.DataFrame] = []
        # v4.5.0: sort=False 避免已按 symbol 排序数据的冗余重排
        for symbol, group in frame.groupby("symbol", sort=False):
            enriched_groups.append(
                self._enrich_symbol_group(
                    group,
                    _ticker_groups.get(symbol, _empty_tickers),
                    _funding_groups.get(symbol, _empty_funding),
                    _orderbook_groups.get(symbol, _empty_orderbooks),
                )
            )

        result = pd.concat(enriched_groups, ignore_index=True)
        result = self._ensure_columns(result)
        return result.drop(columns=["candle_close_time"], errors="ignore")

    def _enrich_symbol_group(
        self,
        frame: pd.DataFrame,
        tickers: pd.DataFrame,
        funding_rates: pd.DataFrame,
        orderbooks: pd.DataFrame,
    ) -> pd.DataFrame:
        result = frame.sort_values("candle_close_time").reset_index(drop=True)

        result, ticker_map, ticker_quality = self._attach_snapshot_by_exchange(
            result,
            tickers,
            prefix="ticker",
            time_column="timestamp",
            max_snapshot_age_seconds=self.TICKER_MAX_CONTEXT_AGE_SECONDS,
            feature_columns=[
                "last_price",
                "mid_price",
                "spread_bps",
                "quote_volume_24h",
                "change_24h",
                "vwap_24h",
            ],
        )
        result["ticker_exchange_count"] = self._count(result, ticker_map["last_price"])
        result["ticker_last_price_mean"] = self._mean(result, ticker_map["last_price"])
        result["ticker_mid_price_mean"] = self._mean(result, ticker_map["mid_price"])
        result["ticker_spread_bps_mean"] = self._mean(result, ticker_map["spread_bps"])
        result["ticker_quote_volume_24h_sum"] = self._sum(result, ticker_map["quote_volume_24h"])
        result["ticker_quote_volume_24h_mean"] = self._mean(result, ticker_map["quote_volume_24h"])
        result["ticker_change_24h_mean"] = self._mean(result, ticker_map["change_24h"])
        result["ticker_vwap_24h_mean"] = self._mean(result, ticker_map["vwap_24h"])
        result["cross_exchange_last_price_std"] = self._std(result, ticker_map["last_price"])
        result["cross_exchange_last_price_range_bps"] = self._range_bps(
            result,
            ticker_map["last_price"],
        )
        self._apply_source_quality_summary(result, "ticker", ticker_quality)

        result, funding_map, funding_quality = self._attach_snapshot_by_exchange(
            result,
            funding_rates,
            prefix="funding",
            time_column="timestamp",
            max_snapshot_age_seconds=self.FUNDING_MAX_CONTEXT_AGE_SECONDS,
            feature_columns=[
                "funding_rate",
                "funding_basis_bps",
            ],
        )
        result["funding_exchange_count"] = self._count(result, funding_map["funding_rate"])
        result["funding_rate_mean"] = self._mean(result, funding_map["funding_rate"])
        result["funding_rate_std"] = self._std(result, funding_map["funding_rate"])
        result["funding_basis_bps_mean"] = self._mean(result, funding_map["funding_basis_bps"])
        self._apply_source_quality_summary(result, "funding", funding_quality)

        result, orderbook_map, orderbook_quality = self._attach_snapshot_by_exchange(
            result,
            orderbooks,
            prefix="orderbook",
            time_column="timestamp",
            max_snapshot_age_seconds=self.ORDERBOOK_MAX_CONTEXT_AGE_SECONDS,
            feature_columns=[
                "mid_price",
                "spread_bps",
                "bid_depth_notional",
                "ask_depth_notional",
                "depth_imbalance",
            ],
        )
        result["orderbook_exchange_count"] = self._count(result, orderbook_map["mid_price"])
        result["orderbook_mid_price_mean"] = self._mean(result, orderbook_map["mid_price"])
        result["orderbook_spread_bps_mean"] = self._mean(result, orderbook_map["spread_bps"])
        result["orderbook_bid_depth_notional_sum"] = self._sum(
            result,
            orderbook_map["bid_depth_notional"],
        )
        result["orderbook_ask_depth_notional_sum"] = self._sum(
            result,
            orderbook_map["ask_depth_notional"],
        )
        result["orderbook_total_depth_notional"] = (
            result["orderbook_bid_depth_notional_sum"] +
            result["orderbook_ask_depth_notional_sum"]
        )
        result["orderbook_depth_imbalance_mean"] = self._mean(
            result,
            orderbook_map["depth_imbalance"],
        )
        self._apply_source_quality_summary(result, "orderbook", orderbook_quality)
        self._apply_market_context_quality_summary(result)

        per_exchange_columns = [
            column
            for column in result.columns
            if "__" in column and (
                column.startswith("ticker__") or
                column.startswith("funding__") or
                column.startswith("orderbook__")
            )
        ]
        return result.drop(columns=per_exchange_columns, errors="ignore")

    def _attach_snapshot_by_exchange(
        self,
        frame: pd.DataFrame,
        snapshots: pd.DataFrame,
        prefix: str,
        time_column: str,
        max_snapshot_age_seconds: int,
        feature_columns: list[str],
    ) -> tuple[pd.DataFrame, dict[str, list[str]], dict[str, object]]:
        result = frame.sort_values("candle_close_time").reset_index(drop=True).copy()
        result["candle_close_time"] = pd.to_datetime(
            result["candle_close_time"],
            utc=True,
            errors="coerce",
        )
        column_map = {column: [] for column in feature_columns}
        quality_map = {
            "known_exchange_count": 0,
            "age_columns": [],
            "fresh_flag_columns": [],
        }

        if snapshots.empty or "exchange" not in snapshots.columns:
            return result, column_map, quality_map

        snapshot_frame = snapshots.copy()
        snapshot_frame[time_column] = pd.to_datetime(
            snapshot_frame[time_column],
            utc=True,
            errors="coerce",
        )
        snapshot_frame = snapshot_frame.dropna(subset=[time_column, "exchange"])
        snapshot_frame = snapshot_frame.sort_values(["exchange", time_column])
        quality_map["known_exchange_count"] = int(
            snapshot_frame["exchange"].dropna().nunique()
        )
        tolerance = (
            pd.Timedelta(seconds=max_snapshot_age_seconds)
            if int(max_snapshot_age_seconds or 0) > 0
            else None
        )

        for exchange in sorted(snapshot_frame["exchange"].dropna().unique()):
            exchange_frame = snapshot_frame[snapshot_frame["exchange"] == exchange].copy()
            if exchange_frame.empty:
                continue

            merge_time_column = f"{prefix}__{exchange}__{time_column}"
            rename_map = {
                column: f"{prefix}__{exchange}__{column}"
                for column in feature_columns
            }
            exchange_frame = exchange_frame[[time_column, *feature_columns]].rename(
                columns={time_column: merge_time_column, **rename_map}
            )
            exchange_frame[merge_time_column] = pd.to_datetime(
                exchange_frame[merge_time_column],
                utc=True,
                errors="coerce",
            )
            exchange_frame = exchange_frame.dropna(subset=[merge_time_column])
            age_column = f"{prefix}__{exchange}__age_seconds"
            fresh_flag_column = f"{prefix}__{exchange}__is_fresh"
            result = pd.merge_asof(
                result.sort_values("candle_close_time"),
                exchange_frame.sort_values(merge_time_column),
                left_on="candle_close_time",
                right_on=merge_time_column,
                direction="backward",
            )
            result[age_column] = (
                result["candle_close_time"] - result[merge_time_column]
            ).dt.total_seconds()
            result[fresh_flag_column] = result[age_column].notna()
            if tolerance is not None:
                result[fresh_flag_column] = (
                    result[fresh_flag_column] &
                    (result[age_column] <= float(tolerance.total_seconds()))
                )
            for column in feature_columns:
                result.loc[~result[fresh_flag_column], rename_map[column]] = np.nan
            result = result.drop(columns=[merge_time_column], errors="ignore")
            for column in feature_columns:
                column_map[column].append(rename_map[column])
            quality_map["age_columns"].append(age_column)
            quality_map["fresh_flag_columns"].append(fresh_flag_column)

        return result, column_map, quality_map

    @classmethod
    def _ensure_columns(cls, frame: pd.DataFrame) -> pd.DataFrame:
        for column in [*cls.CONTEXT_COLUMNS, *cls.CONTEXT_QUALITY_COLUMNS]:
            if column not in frame.columns:
                frame[column] = pd.NA
        return frame

    @classmethod
    def _apply_source_quality_summary(
        cls,
        frame: pd.DataFrame,
        prefix: str,
        quality_map: dict[str, object],
    ) -> None:
        age_columns = list(quality_map.get("age_columns") or [])
        fresh_flag_columns = list(quality_map.get("fresh_flag_columns") or [])
        known_exchange_count = int(quality_map.get("known_exchange_count") or 0)
        index = frame.index

        if age_columns:
            raw_exchange_count = frame[age_columns].notna().sum(axis=1).astype("Int64")
        else:
            raw_exchange_count = pd.Series(0, index=index, dtype="Int64")

        if fresh_flag_columns:
            fresh_exchange_count = (
                frame[fresh_flag_columns].fillna(False).astype(bool).sum(axis=1).astype("Int64")
            )
        else:
            fresh_exchange_count = pd.Series(0, index=index, dtype="Int64")

        stale_exchange_count = (raw_exchange_count - fresh_exchange_count).astype("Int64")
        missing_exchange_count = (known_exchange_count - raw_exchange_count).clip(lower=0).astype("Int64")
        if known_exchange_count > 0:
            fresh_exchange_ratio = (
                fresh_exchange_count.astype("float64") / float(known_exchange_count)
            ).round(4)
        else:
            fresh_exchange_ratio = pd.Series(pd.NA, index=index, dtype="object")

        status_values: list[str] = []
        for raw_count, fresh_count, stale_count, missing_count in zip(
            raw_exchange_count.tolist(),
            fresh_exchange_count.tolist(),
            stale_exchange_count.tolist(),
            missing_exchange_count.tolist(),
        ):
            raw_count = int(raw_count or 0)
            fresh_count = int(fresh_count or 0)
            stale_count = int(stale_count or 0)
            missing_count = int(missing_count or 0)
            if fresh_count > 0 and stale_count == 0 and missing_count == 0:
                status_values.append("ready")
            elif fresh_count > 0:
                status_values.append("partial")
            elif raw_count > 0:
                status_values.append("stale_only")
            else:
                status_values.append("missing")

        frame[f"{prefix}_context_status"] = pd.Series(status_values, index=index, dtype="object")
        frame[f"{prefix}_context_known_exchange_count"] = known_exchange_count
        frame[f"{prefix}_context_raw_exchange_count"] = raw_exchange_count
        frame[f"{prefix}_context_fresh_exchange_count"] = fresh_exchange_count
        frame[f"{prefix}_context_stale_exchange_count"] = stale_exchange_count
        frame[f"{prefix}_context_missing_exchange_count"] = missing_exchange_count
        frame[f"{prefix}_context_fresh_exchange_ratio"] = fresh_exchange_ratio

    @classmethod
    def _apply_market_context_quality_summary(cls, frame: pd.DataFrame) -> None:
        prefixes = ("ticker", "funding", "orderbook")
        overall_flags: list[str] = []
        overall_quality: list[str] = []
        ready_source_count: list[int] = []
        partial_source_count: list[int] = []
        stale_only_source_count: list[int] = []
        missing_source_count: list[int] = []

        for row in frame.itertuples(index=False):
            row_flags: list[str] = []
            status_map = {
                prefix: str(getattr(row, f"{prefix}_context_status", "missing") or "missing")
                for prefix in prefixes
            }
            ready_count = 0
            partial_count = 0
            stale_count = 0
            missing_count = 0
            for prefix, status in status_map.items():
                if status == "ready":
                    ready_count += 1
                    continue
                if status == "partial":
                    partial_count += 1
                elif status == "stale_only":
                    stale_count += 1
                else:
                    missing_count += 1
                row_flags.append(f"{prefix}_context_{status}")

            if status_map["ticker"] in {"missing", "stale_only"} or status_map["orderbook"] in {"missing", "stale_only"}:
                overall_quality.append("thin")
            elif row_flags:
                overall_quality.append("partial")
            else:
                overall_quality.append("ok")

            overall_flags.append("|".join(row_flags) if row_flags else "ok")
            ready_source_count.append(ready_count)
            partial_source_count.append(partial_count)
            stale_only_source_count.append(stale_count)
            missing_source_count.append(missing_count)

        frame["market_context_quality_flag"] = overall_quality
        frame["market_context_quality_flags"] = overall_flags
        frame["market_context_ready_source_count"] = ready_source_count
        frame["market_context_partial_source_count"] = partial_source_count
        frame["market_context_stale_only_source_count"] = stale_only_source_count
        frame["market_context_missing_source_count"] = missing_source_count

    @staticmethod
    def _prepare_tickers(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        result = frame.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
        for col in ["last_price", "mid_price", "spread_bps", "quote_volume_24h", "change_24h", "vwap_24h"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
        return result.sort_values(["symbol", "exchange", "timestamp"])

    @staticmethod
    def _prepare_funding_rates(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        result = frame.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
        for col in ["funding_rate", "mark_price", "index_price"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
        result["funding_basis_bps"] = (
            (result["mark_price"] - result["index_price"]) /
            result["index_price"].replace(0, pd.NA)
        ) * 10000
        return result.sort_values(["symbol", "exchange", "timestamp"])

    @staticmethod
    def _prepare_orderbooks(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        result = frame.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
        for col in ["mid_price", "spread_bps", "bid_depth_notional", "ask_depth_notional", "depth_imbalance"]:
            if col in result.columns:
                result[col] = pd.to_numeric(result[col], errors="coerce")
        return result.sort_values(["symbol", "exchange", "timestamp"])

    @staticmethod
    def _mean(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        if not columns:
            return pd.Series(float("nan"), index=frame.index, dtype="float64")
        return frame[columns].mean(axis=1)

    @staticmethod
    def _sum(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        if not columns:
            return pd.Series(float("nan"), index=frame.index, dtype="float64")
        return frame[columns].sum(axis=1, min_count=1)

    @staticmethod
    def _count(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        if not columns:
            return pd.Series(float("nan"), index=frame.index, dtype="float64")
        return frame[columns].count(axis=1)

    @staticmethod
    def _std(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        if not columns:
            return pd.Series(float("nan"), index=frame.index, dtype="float64")
        return frame[columns].std(axis=1, ddof=0)

    @staticmethod
    def _range_bps(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
        if not columns:
            return pd.Series(float("nan"), index=frame.index, dtype="float64")
        max_value = frame[columns].max(axis=1)
        min_value = frame[columns].min(axis=1)
        mean_value = frame[columns].mean(axis=1)
        return ((max_value - min_value) / mean_value.replace(0, pd.NA)) * 10000
