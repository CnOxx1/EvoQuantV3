from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from database.db_manager import DBManager
from logic_layer.exchange_comparison.models import ExchangeComparisonSnapshot


class ExchangeComparisonRepository:
    """交易所对比模块的数据读写层。"""

    TICKER_COLUMNS = [
        "symbol",
        "exchange",
        "last_price",
        "bid",
        "ask",
        "mid_price",
        "spread_bps",
        "quote_volume_24h",
        "timestamp",
    ]
    ORDERBOOK_COLUMNS = [
        "symbol",
        "exchange",
        "snapshot_depth",
        "best_bid",
        "best_ask",
        "mid_price",
        "spread",
        "spread_bps",
        "bid_depth_notional",
        "ask_depth_notional",
        "depth_imbalance",
        "timestamp",
    ]
    FUNDING_COLUMNS = [
        "symbol",
        "exchange",
        "funding_rate",
        "mark_price",
        "index_price",
        "timestamp",
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
    INDICATOR_COLUMNS = [
        "symbol",
        "timeframe",
        "open_time",
        "close",
        "rsi_14",
        "macd_hist",
        "atr_pct_14",
        "volatility_20",
        "adx_14",
        "bb_width",
        "price_zscore_20",
        "volume_ratio_20",
        "cross_exchange_last_price_range_bps",
        "funding_basis_bps_mean",
        "orderbook_total_depth_notional",
    ]

    def __init__(self, db: DBManager):
        self.db = db

    def fetch_latest_ticker_snapshots(self, symbol: Optional[str] = None) -> pd.DataFrame:
        sql = f"""
            SELECT {", ".join(self.TICKER_COLUMNS)}
            FROM latest_tickers
            {"WHERE symbol = ?" if symbol else ""}
            ORDER BY symbol, exchange
        """
        params = (symbol,) if symbol else ()
        frame = self._fetch_frame(sql, params, self.TICKER_COLUMNS)
        if not frame.empty:
            return frame

        return self._fetch_latest_partition_frame(
            table_name="tickers",
            select_columns=self.TICKER_COLUMNS,
            partition_columns=["symbol", "exchange"],
            order_columns=["timestamp DESC", "id DESC"],
            filters=["symbol = ?"] if symbol else [],
            params=params,
        )

    def fetch_orderbook_candidates(
        self,
        symbol: Optional[str] = None,
        lookback_seconds: int = 1800,
    ) -> pd.DataFrame:
        latest_sql = f"""
            SELECT {", ".join(self.ORDERBOOK_COLUMNS)}
            FROM latest_orderbook_snapshots
            {"WHERE symbol = ?" if symbol else ""}
        """
        latest_params = (symbol,) if symbol else ()
        latest_frame = self._fetch_frame(latest_sql, latest_params, self.ORDERBOOK_COLUMNS)
        if latest_frame.empty:
            latest_frame = self._fetch_latest_partition_frame(
                table_name="orderbook_snapshots",
                select_columns=self.ORDERBOOK_COLUMNS,
                partition_columns=["symbol", "exchange"],
                order_columns=["timestamp DESC", "id DESC"],
                filters=["symbol = ?"] if symbol else [],
                params=latest_params,
            )

        cutoff = self._normalize_db_timestamp(
            pd.Timestamp.utcnow() - pd.Timedelta(seconds=lookback_seconds)
        )
        recent_sql = f"""
            SELECT {", ".join(self.ORDERBOOK_COLUMNS)}
            FROM orderbook_snapshots
            WHERE timestamp >= ?
            {"AND symbol = ?" if symbol else ""}
        """
        recent_params = (cutoff, symbol) if symbol else (cutoff,)
        recent_frame = self._fetch_frame(recent_sql, recent_params, self.ORDERBOOK_COLUMNS)

        valid_frames = [frame for frame in [latest_frame, recent_frame] if not frame.empty]
        if not valid_frames:
            return pd.DataFrame(columns=self.ORDERBOOK_COLUMNS)

        combined = pd.concat(valid_frames, ignore_index=True)
        combined = combined.drop_duplicates(["symbol", "exchange", "timestamp"])
        return combined.sort_values(["symbol", "exchange", "timestamp"]).reset_index(drop=True)

    def fetch_funding_candidates(
        self,
        symbol: Optional[str] = None,
        lookback_seconds: int = 43200,
    ) -> pd.DataFrame:
        latest_sql = f"""
            SELECT {", ".join(self.FUNDING_COLUMNS)}
            FROM latest_funding_rates
            {"WHERE symbol = ?" if symbol else ""}
        """
        latest_params = (symbol,) if symbol else ()
        latest_frame = self._fetch_frame(latest_sql, latest_params, self.FUNDING_COLUMNS)
        if latest_frame.empty:
            latest_frame = self._fetch_latest_partition_frame(
                table_name="funding_rates",
                select_columns=self.FUNDING_COLUMNS,
                partition_columns=["symbol", "exchange"],
                order_columns=["timestamp DESC", "id DESC"],
                filters=["symbol = ?"] if symbol else [],
                params=latest_params,
            )

        cutoff = self._normalize_db_timestamp(
            pd.Timestamp.utcnow() - pd.Timedelta(seconds=lookback_seconds)
        )
        recent_sql = f"""
            SELECT {", ".join(self.FUNDING_COLUMNS)}
            FROM funding_rates
            WHERE timestamp >= ?
            {"AND symbol = ?" if symbol else ""}
        """
        recent_params = (cutoff, symbol) if symbol else (cutoff,)
        recent_frame = self._fetch_frame(recent_sql, recent_params, self.FUNDING_COLUMNS)

        valid_frames = [frame for frame in [latest_frame, recent_frame] if not frame.empty]
        if not valid_frames:
            return pd.DataFrame(columns=self.FUNDING_COLUMNS)

        combined = pd.concat(valid_frames, ignore_index=True)
        combined = combined.drop_duplicates(["symbol", "exchange", "timestamp"])
        return combined.sort_values(["symbol", "exchange", "timestamp"]).reset_index(drop=True)

    def fetch_market_info(
        self,
        symbol: Optional[str] = None,
        market_type: Optional[str] = "spot",
    ) -> pd.DataFrame:
        filters = []
        params: list = []
        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        if market_type:
            filters.append("market_type = ?")
            params.append(market_type)

        return self._fetch_latest_partition_frame(
            table_name="market_info",
            select_columns=self.MARKET_INFO_COLUMNS,
            partition_columns=["symbol", "exchange"],
            order_columns=["updated_at DESC", "id DESC"],
            filters=filters,
            params=tuple(params),
        )

    def fetch_indicator_context(
        self,
        symbol: Optional[str] = None,
        timeframe: str = "1h",
        as_of: Optional[datetime] = None,
        lookback_seconds: int = 21600,
    ) -> pd.DataFrame:
        reference_time = pd.Timestamp(as_of or pd.Timestamp.utcnow())
        cutoff = self._normalize_db_timestamp(
            reference_time - pd.Timedelta(seconds=max(int(lookback_seconds or 0), 0))
        )
        symbol_filter = " AND symbol = ?" if symbol else ""
        sql = f"""
            WITH latest_before_time AS (
                SELECT symbol, MAX(open_time) AS latest_open_time
                FROM technical_indicators
                WHERE timeframe = ?
                  AND open_time < ?{symbol_filter}
                GROUP BY symbol
            ),
            latest_before AS (
                SELECT MAX(source.id) AS latest_id
                FROM technical_indicators AS source
                INNER JOIN latest_before_time
                    ON source.symbol = latest_before_time.symbol
                    AND source.open_time = latest_before_time.latest_open_time
                WHERE source.timeframe = ?
                GROUP BY source.symbol
            )
            SELECT {", ".join(self.INDICATOR_COLUMNS)}
            FROM technical_indicators
            WHERE timeframe = ?
              AND open_time >= ?{symbol_filter}
            UNION ALL
            SELECT {", ".join(self.INDICATOR_COLUMNS)}
            FROM technical_indicators
            WHERE id IN (SELECT latest_id FROM latest_before)
            ORDER BY symbol, open_time
        """
        params: list[object] = [timeframe, cutoff]
        if symbol:
            params.append(symbol)
        params.append(timeframe)
        params.append(timeframe)
        params.append(cutoff)
        if symbol:
            params.append(symbol)
        return self._fetch_frame(sql, tuple(params), self.INDICATOR_COLUMNS)

    def save_comparison_snapshots(self, frame: pd.DataFrame):
        if frame.empty:
            logger.warning("没有可保存的 exchange_comparison_snapshots 数据")
            return

        ordered_columns = ExchangeComparisonSnapshot.TABLE_COLUMNS
        placeholders = ", ".join(["?"] * len(ordered_columns))
        conflict_columns = [
            "symbol",
            "exchange_a",
            "exchange_b",
            "compare_window_seconds",
            "timestamp",
        ]
        update_columns = [
            column for column in ordered_columns if column not in conflict_columns
        ]
        updates_sql = ",\n                ".join(
            f"{column} = excluded.{column}"
            for column in update_columns
        )
        sql = f"""
            INSERT INTO exchange_comparison_snapshots (
                {", ".join(ordered_columns)}
            ) VALUES ({placeholders})
            ON CONFLICT(symbol, exchange_a, exchange_b, compare_window_seconds, timestamp)
            DO UPDATE SET
                {updates_sql}
        """

        params_list = []
        for record in frame.to_dict("records"):
            params_list.append(
                tuple(self._to_db_value(record.get(column)) for column in ordered_columns)
            )

        self.db.execute_many(sql, params_list)
        self.db.commit()
        logger.info(f"已保存 {len(params_list)} 条 exchange_comparison_snapshots")

    @staticmethod
    def _to_db_value(value):
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            return ExchangeComparisonRepository._normalize_db_timestamp(value)
        if isinstance(value, datetime):
            return ExchangeComparisonRepository._normalize_db_timestamp(value)
        if isinstance(value, bool):
            return int(value)
        if pd.isna(value):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return float(value)
        return value

    @staticmethod
    def _normalize_db_timestamp(value) -> str:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return timestamp.isoformat()

    def _fetch_frame(
        self,
        sql: str,
        params: tuple,
        columns: list[str],
    ) -> pd.DataFrame:
        rows = self.db.fetch_all(sql, params)
        if not rows:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame([dict(row) for row in rows], columns=columns)

    def _fetch_latest_partition_frame(
        self,
        table_name: str,
        select_columns: list[str],
        partition_columns: list[str],
        order_columns: list[str],
        filters: list[str],
        params: tuple,
    ) -> pd.DataFrame:
        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
        select_sql = ", ".join(select_columns)
        partition_sql = ", ".join(partition_columns)
        order_sql = ", ".join(order_columns)
        sql = f"""
            WITH ranked AS (
                SELECT
                    {select_sql},
                    ROW_NUMBER() OVER (
                        PARTITION BY {partition_sql}
                        ORDER BY {order_sql}
                    ) AS row_num
                FROM {table_name}
                {where_sql}
            )
            SELECT {select_sql}
            FROM ranked
            WHERE row_num = 1
            ORDER BY {partition_sql}
        """
        return self._fetch_frame(sql, params, select_columns)
