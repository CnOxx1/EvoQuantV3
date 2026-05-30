from __future__ import annotations

import pandas as pd

from logic_layer.exchange_comparison.models import ExchangeComparisonConfig


class SnapshotAligner:
    """将 ticker、orderbook、funding、market_info、indicator 对齐为每交易所单行快照。"""

    ORDERBOOK_RENAME_MAP = {
        "timestamp": "orderbook_timestamp",
        "best_bid": "orderbook_best_bid",
        "best_ask": "orderbook_best_ask",
        "mid_price": "orderbook_mid_price",
        "spread": "orderbook_spread",
        "spread_bps": "orderbook_spread_bps",
        "bid_depth_notional": "orderbook_bid_depth_notional",
        "ask_depth_notional": "orderbook_ask_depth_notional",
        "depth_imbalance": "orderbook_depth_imbalance",
    }
    ORDERBOOK_COLUMNS = [
        "symbol",
        "exchange",
        "snapshot_depth",
        "orderbook_timestamp",
        "orderbook_best_bid",
        "orderbook_best_ask",
        "orderbook_mid_price",
        "orderbook_spread",
        "orderbook_spread_bps",
        "orderbook_bid_depth_notional",
        "orderbook_ask_depth_notional",
        "orderbook_depth_imbalance",
    ]
    FUNDING_RENAME_MAP = {
        "timestamp": "funding_timestamp",
    }
    FUNDING_COLUMNS = [
        "symbol",
        "exchange",
        "funding_timestamp",
        "funding_rate",
        "mark_price",
        "index_price",
    ]
    MARKET_INFO_COLUMNS = [
        "symbol",
        "exchange",
        "market_type",
        "maker_fee",
        "taker_fee",
        "min_cost",
        "max_cost",
        "contract_size",
        "updated_at",
    ]
    INDICATOR_RENAME_MAP = {
        "timeframe": "context_timeframe",
        "open_time": "context_open_time",
        "close": "context_close",
        "rsi_14": "context_rsi_14",
        "macd_hist": "context_macd_hist",
        "atr_pct_14": "context_atr_pct_14",
        "volatility_20": "context_volatility_20",
        "adx_14": "context_adx_14",
        "bb_width": "context_bb_width",
        "price_zscore_20": "context_price_zscore_20",
        "volume_ratio_20": "context_volume_ratio_20",
        "cross_exchange_last_price_range_bps": "context_cross_exchange_last_price_range_bps",
        "funding_basis_bps_mean": "context_funding_basis_bps_mean",
        "orderbook_total_depth_notional": "context_orderbook_total_depth_notional",
    }
    INDICATOR_COLUMNS = [
        "symbol",
        "context_timeframe",
        "context_open_time",
        "context_close",
        "context_rsi_14",
        "context_macd_hist",
        "context_atr_pct_14",
        "context_volatility_20",
        "context_adx_14",
        "context_bb_width",
        "context_price_zscore_20",
        "context_volume_ratio_20",
        "context_cross_exchange_last_price_range_bps",
        "context_funding_basis_bps_mean",
        "context_orderbook_total_depth_notional",
    ]

    def align(
        self,
        tickers: pd.DataFrame,
        orderbooks: pd.DataFrame,
        market_info: pd.DataFrame,
        funding_rates: pd.DataFrame,
        indicator_context: pd.DataFrame,
        config: ExchangeComparisonConfig,
    ) -> pd.DataFrame:
        if tickers.empty:
            return pd.DataFrame()

        tickers = tickers.copy()
        tickers["timestamp"] = self._normalize_timestamp_series(tickers["timestamp"])
        tickers = tickers.dropna(subset=["symbol", "exchange", "timestamp"])
        if tickers.empty:
            return pd.DataFrame()
        aligned = tickers.sort_values(["symbol", "exchange", "timestamp"]).reset_index(drop=True)
        aligned = aligned.rename(columns={"timestamp": "ticker_timestamp"})

        aligned = self._merge_orderbooks(aligned, orderbooks, config)
        aligned = self._merge_market_info(aligned, market_info)
        aligned = self._merge_funding(aligned, funding_rates, config)
        aligned = self._merge_indicator_context(aligned, indicator_context, config)
        return aligned

    def _merge_orderbooks(
        self,
        aligned: pd.DataFrame,
        orderbooks: pd.DataFrame,
        config: ExchangeComparisonConfig,
    ) -> pd.DataFrame:
        if orderbooks.empty:
            for column in self.ORDERBOOK_COLUMNS[2:]:
                aligned[column] = pd.NA
            aligned["orderbook_alignment_gap_ms"] = pd.NA
            return aligned

        orderbooks = orderbooks.copy().rename(columns=self.ORDERBOOK_RENAME_MAP)
        orderbooks["orderbook_timestamp"] = self._normalize_timestamp_series(
            orderbooks["orderbook_timestamp"]
        )
        orderbooks = orderbooks.dropna(
            subset=["symbol", "exchange", "orderbook_timestamp"]
        )
        if orderbooks.empty:
            for column in self.ORDERBOOK_COLUMNS[2:]:
                aligned[column] = pd.NA
            aligned["orderbook_alignment_gap_ms"] = pd.NA
            return aligned
        orderbooks = orderbooks.sort_values(
            ["symbol", "exchange", "orderbook_timestamp"]
        ).reset_index(drop=True)
        aligned = pd.merge_asof(
            aligned.sort_values(["ticker_timestamp", "symbol", "exchange"]),
            orderbooks[self.ORDERBOOK_COLUMNS].sort_values(
                ["orderbook_timestamp", "symbol", "exchange"]
            ),
            left_on="ticker_timestamp",
            right_on="orderbook_timestamp",
            by=["symbol", "exchange"],
            direction="nearest",
            tolerance=pd.Timedelta(seconds=config.orderbook_window_seconds),
        )
        aligned["orderbook_alignment_gap_ms"] = (
            aligned["ticker_timestamp"] - aligned["orderbook_timestamp"]
        ).abs().dt.total_seconds() * 1000
        return aligned

    def _merge_market_info(
        self,
        aligned: pd.DataFrame,
        market_info: pd.DataFrame,
    ) -> pd.DataFrame:
        if market_info.empty:
            for column in self.MARKET_INFO_COLUMNS[2:]:
                aligned[column] = pd.NA
            return aligned

        market_info = market_info.copy()
        market_info["updated_at"] = self._normalize_timestamp_series(market_info["updated_at"])
        market_info = (
            market_info.sort_values(["symbol", "exchange", "updated_at"])
            .drop_duplicates(["symbol", "exchange"], keep="last")
            .reset_index(drop=True)
        )
        return aligned.merge(
            market_info[self.MARKET_INFO_COLUMNS],
            on=["symbol", "exchange"],
            how="left",
        )

    def _merge_funding(
        self,
        aligned: pd.DataFrame,
        funding_rates: pd.DataFrame,
        config: ExchangeComparisonConfig,
    ) -> pd.DataFrame:
        if funding_rates.empty:
            for column in self.FUNDING_COLUMNS[2:]:
                aligned[column] = pd.NA
            aligned["funding_alignment_gap_ms"] = pd.NA
            return aligned

        funding_rates = funding_rates.copy().rename(columns=self.FUNDING_RENAME_MAP)
        funding_rates["funding_timestamp"] = self._normalize_timestamp_series(
            funding_rates["funding_timestamp"]
        )
        funding_rates = funding_rates.dropna(
            subset=["symbol", "exchange", "funding_timestamp"]
        )
        if funding_rates.empty:
            for column in self.FUNDING_COLUMNS[2:]:
                aligned[column] = pd.NA
            aligned["funding_alignment_gap_ms"] = pd.NA
            return aligned
        funding_rates = funding_rates.sort_values(
            ["symbol", "exchange", "funding_timestamp"]
        ).reset_index(drop=True)
        aligned = pd.merge_asof(
            aligned.sort_values(["ticker_timestamp", "symbol", "exchange"]),
            funding_rates[self.FUNDING_COLUMNS].sort_values(
                ["funding_timestamp", "symbol", "exchange"]
            ),
            left_on="ticker_timestamp",
            right_on="funding_timestamp",
            by=["symbol", "exchange"],
            direction="nearest",
            tolerance=pd.Timedelta(seconds=config.funding_window_seconds),
        )
        aligned["funding_alignment_gap_ms"] = (
            aligned["ticker_timestamp"] - aligned["funding_timestamp"]
        ).abs().dt.total_seconds() * 1000
        return aligned

    def _merge_indicator_context(
        self,
        aligned: pd.DataFrame,
        indicator_context: pd.DataFrame,
        config: ExchangeComparisonConfig,
    ) -> pd.DataFrame:
        if indicator_context.empty:
            for column in self.INDICATOR_COLUMNS[1:]:
                aligned[column] = pd.NA
            aligned["context_alignment_gap_ms"] = pd.NA
            return aligned

        indicator_context = indicator_context.copy().rename(columns=self.INDICATOR_RENAME_MAP)
        indicator_context["context_open_time"] = self._normalize_timestamp_series(
            indicator_context["context_open_time"]
        )
        indicator_context = indicator_context.dropna(
            subset=["symbol", "context_open_time"]
        )
        if indicator_context.empty:
            for column in self.INDICATOR_COLUMNS[1:]:
                aligned[column] = pd.NA
            aligned["context_alignment_gap_ms"] = pd.NA
            return aligned
        indicator_context = indicator_context.sort_values(
            ["symbol", "context_open_time"]
        ).reset_index(drop=True)
        aligned = pd.merge_asof(
            aligned.sort_values(["ticker_timestamp", "symbol"]),
            indicator_context[self.INDICATOR_COLUMNS].sort_values(
                ["context_open_time", "symbol"]
            ),
            left_on="ticker_timestamp",
            right_on="context_open_time",
            by=["symbol"],
            direction="backward",
            tolerance=pd.Timedelta(seconds=config.max_indicator_age_seconds),
        )
        aligned["context_alignment_gap_ms"] = (
            aligned["ticker_timestamp"] - aligned["context_open_time"]
        ).dt.total_seconds() * 1000
        return aligned

    @staticmethod
    def _normalize_timestamp_series(series: pd.Series) -> pd.Series:
        return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_localize(None)
