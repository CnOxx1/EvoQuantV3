from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from loguru import logger

from database.db_manager import DBManager
from logic_layer.technical_indicators.calculator import TechnicalIndicatorCalculator


class TechnicalIndicatorRepository:
    """技术指标模块的数据访问层。"""

    TICKER_SNAPSHOT_COLUMNS = [
        "symbol",
        "exchange",
        "last_price",
        "mid_price",
        "spread_bps",
        "quote_volume_24h",
        "change_24h",
        "vwap_24h",
        "timestamp",
    ]
    FUNDING_SNAPSHOT_COLUMNS = [
        "symbol",
        "exchange",
        "funding_rate",
        "mark_price",
        "index_price",
        "timestamp",
    ]
    ORDERBOOK_SNAPSHOT_COLUMNS = [
        "symbol",
        "exchange",
        "mid_price",
        "spread_bps",
        "bid_depth_notional",
        "ask_depth_notional",
        "depth_imbalance",
        "timestamp",
    ]
    MARKET_CONTEXT_COLUMNS = [
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
    MARKET_CONTEXT_QUALITY_COLUMNS = [
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
    INDICATOR_COLUMNS = [
        *TechnicalIndicatorCalculator.OUTPUT_COLUMNS[5:],
        *MARKET_CONTEXT_COLUMNS,
        *MARKET_CONTEXT_QUALITY_COLUMNS,
    ]

    def __init__(self, db: DBManager):
        self.db = db

    def fetch_raw_klines(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        since_days: Optional[int] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT symbol, exchange, timeframe, open_time, open, high, low, close, volume
            FROM klines
            WHERE 1 = 1
        """
        params: list = []

        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if timeframe:
            sql += " AND timeframe = ?"
            params.append(timeframe)
        if since_time is not None:
            sql += " AND open_time >= ?"
            params.append(self._normalize_db_timestamp(since_time))
        if since_days is not None:
            since_time = datetime.utcnow() - timedelta(days=since_days)
            sql += " AND open_time >= ?"
            params.append(self._normalize_db_timestamp(since_time))

        sql += " ORDER BY symbol, timeframe, open_time, exchange"
        rows = self.db.fetch_all(sql, tuple(params))
        return pd.DataFrame([dict(row) for row in rows])

    def fetch_merged_klines(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        since_days: Optional[int] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        sql = """
            SELECT symbol, timeframe, open_time, open, high, low, close, volume,
                   exchange_count, source_exchanges, merge_method
            FROM merged_klines
            WHERE 1 = 1
        """
        params: list = []

        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if timeframe:
            sql += " AND timeframe = ?"
            params.append(timeframe)
        if since_time is not None:
            sql += " AND open_time >= ?"
            params.append(self._normalize_db_timestamp(since_time))
        if since_days is not None:
            since_time = datetime.utcnow() - timedelta(days=since_days)
            sql += " AND open_time >= ?"
            params.append(self._normalize_db_timestamp(since_time))

        sql += " ORDER BY symbol, timeframe, open_time"
        rows = self.db.fetch_all(sql, tuple(params))
        return pd.DataFrame([dict(row) for row in rows])

    def fetch_targets(self, table_name: str) -> list[tuple[str, str]]:
        if table_name not in {"klines", "merged_klines", "technical_indicators"}:
            raise ValueError(f"不支持的表名: {table_name}")

        if table_name == "klines":
            sql = """
                SELECT DISTINCT symbol, timeframe
                FROM klines
                ORDER BY symbol, timeframe
            """
        else:
            sql = f"""
                SELECT DISTINCT symbol, timeframe
                FROM {table_name}
                ORDER BY symbol, timeframe
            """
        rows = self.db.fetch_all(sql)
        return [(row["symbol"], row["timeframe"]) for row in rows]

    def fetch_latest_open_time(
        self,
        table_name: str,
        symbol: str,
        timeframe: str,
    ) -> Optional[pd.Timestamp]:
        if table_name not in {"klines", "merged_klines", "technical_indicators"}:
            raise ValueError(f"不支持的表名: {table_name}")

        row = self.db.fetch_one(
            f"""
                SELECT MAX(open_time) AS latest_open_time
                FROM {table_name}
                WHERE symbol = ? AND timeframe = ?
            """,
            (symbol, timeframe),
        )
        if row is None or row["latest_open_time"] is None:
            return None
        return pd.Timestamp(row["latest_open_time"])

    def fetch_ticker_snapshots(
        self,
        symbol: Optional[str] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        return self._fetch_snapshot_frame(
            table_name="tickers",
            columns=self.TICKER_SNAPSHOT_COLUMNS,
            symbol=symbol,
            since_time=since_time,
        )

    def fetch_funding_snapshots(
        self,
        symbol: Optional[str] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        return self._fetch_snapshot_frame(
            table_name="funding_rates",
            columns=self.FUNDING_SNAPSHOT_COLUMNS,
            symbol=symbol,
            since_time=since_time,
        )

    def fetch_orderbook_snapshots(
        self,
        symbol: Optional[str] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        return self._fetch_snapshot_frame(
            table_name="orderbook_snapshots",
            columns=self.ORDERBOOK_SNAPSHOT_COLUMNS,
            symbol=symbol,
            since_time=since_time,
        )

    def save_merged_klines(self, frame: pd.DataFrame):
        if frame.empty:
            logger.warning("没有可保存的 merged_klines 数据")
            return

        sql = """
            INSERT INTO merged_klines (
                symbol, timeframe, open_time, open, high, low, close, volume,
                exchange_count, source_exchanges, merge_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, open_time) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                exchange_count = excluded.exchange_count,
                source_exchanges = excluded.source_exchanges,
                merge_method = excluded.merge_method
        """

        # v4.3.0: 预转换 open_time 列为 ISO 字符串，避免循环内逐行 pd.Timestamp()
        # Series 必须用 .dt.strftime，不能直接 .strftime
        open_time_iso = pd.to_datetime(frame["open_time"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
        params_list = [
            (
                row.symbol,
                row.timeframe,
                open_time_iso.iloc[i],
                self._to_scalar(row.open),
                self._to_scalar(row.high),
                self._to_scalar(row.low),
                self._to_scalar(row.close),
                self._to_scalar(row.volume),
                int(row.exchange_count),
                row.source_exchanges,
                row.merge_method,
            )
            for i, row in enumerate(frame.itertuples(index=False))
        ]
        self.db.execute_many(sql, params_list)
        self.db.commit()
        logger.info(f"已保存 {len(params_list)} 条 merged_klines")

    def save_technical_indicators(self, frame: pd.DataFrame):
        if frame.empty:
            logger.warning("没有可保存的 technical_indicators 数据")
            return

        ordered_columns = [
            "symbol",
            "timeframe",
            "open_time",
            "close",
            "volume",
            *self.INDICATOR_COLUMNS,
        ]
        placeholders = ", ".join(["?"] * len(ordered_columns))
        update_columns = ["close", "volume", *self.INDICATOR_COLUMNS]
        updates_sql = ",\n                ".join(
            f"{column} = excluded.{column}"
            for column in update_columns
        )
        sql = f"""
            INSERT INTO technical_indicators (
                {", ".join(ordered_columns)}
            ) VALUES ({placeholders})
            ON CONFLICT(symbol, timeframe, open_time) DO UPDATE SET
                {updates_sql}
        """

        params_list = []
        for row in frame.itertuples(index=False):
            row_values = []
            for column in ordered_columns:
                value = getattr(row, column)
                if column == "open_time":
                    row_values.append(pd.Timestamp(value).isoformat())
                elif column in {"symbol", "timeframe"}:
                    row_values.append(value)
                elif column in self.MARKET_CONTEXT_QUALITY_COLUMNS and isinstance(value, str):
                    row_values.append(value)
                else:
                    row_values.append(self._to_scalar(value))
            params_list.append(tuple(row_values))
        self.db.execute_many(sql, params_list)
        self.db.commit()
        logger.info(f"已保存 {len(params_list)} 条 technical_indicators")

    @staticmethod
    def _to_scalar(value):
        if pd.isna(value):
            return None
        if isinstance(value, str):
            return value
        return float(value)

    @staticmethod
    def _normalize_db_timestamp(value) -> str:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return timestamp.isoformat()

    def _fetch_snapshot_frame(
        self,
        table_name: str,
        columns: list[str],
        symbol: Optional[str] = None,
        since_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        select_columns = ", ".join(columns)

        if since_time is None:
            sql = f"""
                SELECT {select_columns}
                FROM {table_name}
                WHERE 1 = 1
            """
            params: list = []
            if symbol:
                sql += " AND symbol = ?"
                params.append(symbol)
            sql += " ORDER BY symbol, exchange, timestamp"
            rows = self.db.fetch_all(sql, tuple(params))
            return pd.DataFrame([dict(row) for row in rows], columns=columns)

        cutoff = self._normalize_db_timestamp(since_time)
        symbol_filter = " AND symbol = ?" if symbol else ""
        sql = f"""
            WITH latest_before_time AS (
                SELECT symbol, exchange, MAX(timestamp) AS latest_timestamp
                FROM {table_name}
                WHERE timestamp < ?{symbol_filter}
                GROUP BY symbol, exchange
            ),
            latest_before AS (
                SELECT MAX(source.id) AS latest_id
                FROM {table_name} AS source
                INNER JOIN latest_before_time
                    ON source.symbol = latest_before_time.symbol
                    AND source.exchange = latest_before_time.exchange
                    AND source.timestamp = latest_before_time.latest_timestamp
                GROUP BY source.symbol, source.exchange
            )
            SELECT {select_columns}
            FROM {table_name}
            WHERE timestamp >= ?{symbol_filter}
            UNION ALL
            SELECT {select_columns}
            FROM {table_name}
            WHERE id IN (SELECT latest_id FROM latest_before)
            ORDER BY symbol, exchange, timestamp
        """
        params = [cutoff]
        if symbol:
            params.append(symbol)
        params.append(cutoff)
        if symbol:
            params.append(symbol)
        rows = self.db.fetch_all(sql, tuple(params))
        return pd.DataFrame([dict(row) for row in rows], columns=columns)
