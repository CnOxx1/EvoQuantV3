import os
import sqlite3
import threading
import time
from typing import Optional

from loguru import logger

from config.settings import DATABASE_PATH
from logic_layer.technical_indicators.calculator import TechnicalIndicatorCalculator


class DBManager:
    """SQLite 数据库连接与表管理"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DATABASE_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.Lock()

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
            with self._connections_lock:
                self._connections[threading.get_ident()] = conn
        return conn

    def init_tables(self):
        """创建所有数据表"""
        self._create_collection_runs_table()
        self._create_market_info_table()
        self._create_klines_table()
        self._create_tickers_table()
        self._create_latest_tickers_table()
        self._create_funding_rates_table()
        self._create_latest_funding_rates_table()
        self._create_orderbook_snapshots_table()
        self._create_latest_orderbook_snapshots_table()
        self._create_trade_flow_bars_table()
        self._create_latest_trade_flow_bars_table()
        self._create_open_interest_snapshots_table()
        self._create_latest_open_interest_snapshots_table()
        self._create_liquidation_bars_table()
        self._create_latest_liquidation_bars_table()
        self._create_positioning_snapshots_table()
        self._create_latest_positioning_snapshots_table()
        self._create_basis_snapshots_table()
        self._create_latest_basis_snapshots_table()
        self._create_news_articles_table()
        self._create_event_calendar_events_table()
        self._create_macro_factor_catalog_table()
        self._create_macro_timeseries_table()
        self._create_latest_macro_timeseries_table()
        self._create_alternative_factor_catalog_table()
        self._create_alternative_timeseries_table()
        self._create_latest_alternative_timeseries_table()
        self._create_onchain_factor_catalog_table()
        self._create_onchain_timeseries_table()
        self._create_latest_onchain_timeseries_table()
        self._create_tokenomics_factor_catalog_table()
        self._create_tokenomics_timeseries_table()
        self._create_latest_tokenomics_timeseries_table()
        self._create_options_factor_catalog_table()
        self._create_options_timeseries_table()
        self._create_latest_options_timeseries_table()
        self._create_token_unlock_events_table()
        self._create_macro_context_snapshots_table()
        self._create_ai_market_context_snapshots_table()
        self._create_market_breadth_snapshots_table()
        self._create_market_structure_snapshots_table()
        self._create_asset_readiness_snapshots_table()
        self._create_data_quality_audit_snapshots_table()
        self._create_merged_klines_table()
        self._create_technical_indicators_table()
        self._create_exchange_comparison_snapshots_table()
        self._sync_latest_snapshot_tables()
        self.conn.commit()
        logger.info("数据库表初始化完成")

    # ------------------------------------------------------------------
    # 域专用初始化方法（数据库拆分后各模块调用对应方法）
    # ------------------------------------------------------------------

    def init_exchange_data_tables(self):
        """仅创建 exchange_data 域的表（高频交易所数据）。"""
        from database.schemas import EXCHANGE_DATA_INIT_METHODS

        self._create_collection_runs_table()
        for method_name in EXCHANGE_DATA_INIT_METHODS:
            getattr(self, method_name)()
        try:
            self._sync_latest_snapshot_tables()
        except sqlite3.OperationalError as e:
            if "readonly" in str(e):
                logger.debug("跳过 latest 表同步（数据库只读）")
            else:
                raise
        self.conn.commit()

    def init_market_data_tables(self):
        """仅创建 market_data 域的表（宏观/链上/代币/期权/另类/新闻/事件）。"""
        from database.schemas import MARKET_DATA_INIT_METHODS

        self._create_collection_runs_table()
        for method_name in MARKET_DATA_INIT_METHODS:
            getattr(self, method_name)()
        self.conn.commit()

    def init_analytics_tables(self):
        """仅创建 analytics 域的表（逻辑层输出/审计/采集记录）。"""
        from database.schemas import ANALYTICS_INIT_METHODS

        for method_name in ANALYTICS_INIT_METHODS:
            getattr(self, method_name)()
        self.conn.commit()

    def attach_domain_views(
        self,
        exchange_db_path: str,
        market_db_path: str,
    ):
        """ATTACH 其他域数据库并创建同名 VIEW，使逻辑层 SQL 查询无需修改。"""
        from database.schemas import (
            EXCHANGE_DATA_TABLE_NAMES,
            MARKET_DATA_TABLE_NAMES,
        )

        # ATTACH（幂等：已 attach 则跳过）
        for schema_name, db_path in [
            ("exchange_db", exchange_db_path),
            ("market_db", market_db_path),
        ]:
            try:
                self.conn.execute(
                    f"ATTACH DATABASE '{db_path}' AS {schema_name}"
                )
            except sqlite3.OperationalError as exc:
                if "already" not in str(exc).lower():
                    raise

        # 为跨域表创建临时 VIEW（TEMP VIEW 是会话级，与 ATTACH 生命周期一致）
        for table_name in EXCHANGE_DATA_TABLE_NAMES:
            self.conn.execute(
                f"CREATE TEMP VIEW IF NOT EXISTS {table_name} "
                f"AS SELECT * FROM exchange_db.{table_name}"
            )
        for table_name in MARKET_DATA_TABLE_NAMES:
            self.conn.execute(
                f"CREATE TEMP VIEW IF NOT EXISTS {table_name} "
                f"AS SELECT * FROM market_db.{table_name}"
            )

    def _existing_columns(self, table_name: str) -> set[str]:
        rows = self.fetch_all(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in rows}

    @staticmethod
    def _is_duplicate_column_error(error: sqlite3.OperationalError) -> bool:
        return "duplicate column name" in str(error).lower()

    def _ensure_columns(self, table_name: str, columns: dict[str, str]):
        existing_columns = self._existing_columns(table_name)
        for column_name, column_sql in columns.items():
            if column_name in existing_columns:
                continue
            try:
                self.conn.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
                )
            except sqlite3.OperationalError as exc:
                if not self._is_duplicate_column_error(exc):
                    raise
                existing_columns = self._existing_columns(table_name)
                if column_name not in existing_columns:
                    raise
                logger.info(
                    f"数据表 {table_name} 字段已被并发创建，跳过重复补列: {column_name}"
                )
                continue
            existing_columns.add(column_name)
            logger.info(f"已为数据表 {table_name} 添加字段: {column_name}")

    @staticmethod
    def _technical_indicator_columns() -> dict[str, str]:
        market_context_columns = [
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
        market_context_quality_real_columns = [
            "ticker_context_known_exchange_count",
            "ticker_context_raw_exchange_count",
            "ticker_context_fresh_exchange_count",
            "ticker_context_stale_exchange_count",
            "ticker_context_missing_exchange_count",
            "ticker_context_fresh_exchange_ratio",
            "funding_context_known_exchange_count",
            "funding_context_raw_exchange_count",
            "funding_context_fresh_exchange_count",
            "funding_context_stale_exchange_count",
            "funding_context_missing_exchange_count",
            "funding_context_fresh_exchange_ratio",
            "orderbook_context_known_exchange_count",
            "orderbook_context_raw_exchange_count",
            "orderbook_context_fresh_exchange_count",
            "orderbook_context_stale_exchange_count",
            "orderbook_context_missing_exchange_count",
            "orderbook_context_fresh_exchange_ratio",
            "market_context_ready_source_count",
            "market_context_partial_source_count",
            "market_context_stale_only_source_count",
            "market_context_missing_source_count",
        ]
        market_context_quality_text_columns = [
            "ticker_context_status",
            "funding_context_status",
            "orderbook_context_status",
            "market_context_quality_flag",
            "market_context_quality_flags",
        ]
        return {
            **{column: "REAL" for column in TechnicalIndicatorCalculator.OUTPUT_COLUMNS[5:]},
            **{column: "REAL" for column in market_context_columns},
            **{column: "REAL" for column in market_context_quality_real_columns},
            **{column: "TEXT" for column in market_context_quality_text_columns},
        }

    @staticmethod
    def _exchange_comparison_snapshot_columns() -> dict[str, str]:
        return {
            "ticker_timestamp_a": "TIMESTAMP",
            "ticker_timestamp_b": "TIMESTAMP",
            "orderbook_timestamp_a": "TIMESTAMP",
            "orderbook_timestamp_b": "TIMESTAMP",
            "funding_timestamp_a": "TIMESTAMP",
            "funding_timestamp_b": "TIMESTAMP",
            "last_price_a": "REAL",
            "last_price_b": "REAL",
            "mid_price_a": "REAL",
            "mid_price_b": "REAL",
            "bid_a": "REAL",
            "ask_a": "REAL",
            "bid_b": "REAL",
            "ask_b": "REAL",
            "spread_bps_a": "REAL",
            "spread_bps_b": "REAL",
            "quote_volume_24h_a": "REAL",
            "quote_volume_24h_b": "REAL",
            "bid_depth_notional_a": "REAL",
            "bid_depth_notional_b": "REAL",
            "ask_depth_notional_a": "REAL",
            "ask_depth_notional_b": "REAL",
            "depth_imbalance_a": "REAL",
            "depth_imbalance_b": "REAL",
            "funding_rate_a": "REAL",
            "funding_rate_b": "REAL",
            "mark_price_a": "REAL",
            "mark_price_b": "REAL",
            "index_price_a": "REAL",
            "index_price_b": "REAL",
            "last_diff_abs": "REAL",
            "last_diff_bps": "REAL",
            "mid_diff_abs": "REAL",
            "mid_diff_bps": "REAL",
            "bid_diff_bps": "REAL",
            "ask_diff_bps": "REAL",
            "funding_rate_diff_abs": "REAL",
            "funding_rate_diff_bps": "REAL",
            "mark_price_diff_bps": "REAL",
            "index_price_diff_bps": "REAL",
            "cross_spread_ab_bps": "REAL",
            "cross_spread_ba_bps": "REAL",
            "estimated_fee_bps": "REAL",
            "estimated_slippage_ab_bps": "REAL",
            "estimated_slippage_ba_bps": "REAL",
            "estimated_slippage_bps": "REAL",
            "net_cross_spread_ab_bps": "REAL",
            "net_cross_spread_ba_bps": "REAL",
            "net_cross_spread_max_bps": "REAL",
            "quote_volume_ratio": "REAL",
            "bid_depth_ratio": "REAL",
            "ask_depth_ratio": "REAL",
            "total_depth_ratio": "REAL",
            "spread_bps_gap": "REAL",
            "depth_imbalance_gap": "REAL",
            "inter_exchange_ticker_gap_ms": "REAL",
            "inter_exchange_funding_gap_ms": "REAL",
            "context_timeframe": "TEXT",
            "context_open_time": "TIMESTAMP",
            "context_age_seconds": "REAL",
            "context_close": "REAL",
            "context_rsi_14": "REAL",
            "context_macd_hist": "REAL",
            "context_atr_pct_14": "REAL",
            "context_volatility_20": "REAL",
            "context_adx_14": "REAL",
            "context_bb_width": "REAL",
            "context_price_zscore_20": "REAL",
            "context_volume_ratio_20": "REAL",
            "context_cross_exchange_last_price_range_bps": "REAL",
            "context_funding_basis_bps_mean": "REAL",
            "context_orderbook_total_depth_notional": "REAL",
            "best_buy_exchange": "TEXT",
            "best_sell_exchange": "TEXT",
            "opportunity_type": "TEXT",
            "signal_label": "TEXT",
            "signal_strength": "REAL",
            "is_actionable": "INTEGER DEFAULT 0",
            "anomaly_score": "REAL",
            "execution_preference_score": "REAL",
            "market_regime_label": "TEXT",
            "funding_regime_label": "TEXT",
            "context_completeness_score": "REAL",
            "data_quality_flag": "TEXT",
            "raw_context_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }

    def _create_market_info_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange_symbol TEXT,
                base TEXT NOT NULL,
                quote TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT DEFAULT 'spot',
                status TEXT,
                is_spot INTEGER,
                is_margin INTEGER,
                is_swap INTEGER,
                is_future INTEGER,
                is_contract INTEGER,
                is_linear INTEGER,
                is_inverse INTEGER,
                price_precision REAL,
                min_price REAL,
                max_price REAL,
                amount_precision REAL,
                min_amount REAL,
                max_amount REAL,
                min_cost REAL,
                max_cost REAL,
                maker_fee REAL,
                taker_fee REAL,
                contract_size REAL,
                settle_currency TEXT,
                raw_info_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type)
            )
        """)
        self._ensure_columns("market_info", {
            "exchange_symbol": "TEXT",
            "is_spot": "INTEGER",
            "is_margin": "INTEGER",
            "is_swap": "INTEGER",
            "is_future": "INTEGER",
            "is_contract": "INTEGER",
            "is_linear": "INTEGER",
            "is_inverse": "INTEGER",
            "min_price": "REAL",
            "max_price": "REAL",
            "max_cost": "REAL",
            "raw_info_json": "TEXT",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_info_symbol_exchange
            ON market_info(symbol, exchange)
        """)

    def _create_collection_runs_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                source_name TEXT NOT NULL,
                job_name TEXT NOT NULL,
                status TEXT NOT NULL,
                item_count INTEGER DEFAULT 0,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP NOT NULL,
                duration_seconds REAL,
                message TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("collection_runs", {
            "item_count": "INTEGER DEFAULT 0",
            "started_at": "TIMESTAMP",
            "finished_at": "TIMESTAMP",
            "duration_seconds": "REAL",
            "message": "TEXT",
            "metadata_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_runs_module_time
            ON collection_runs(module_name, finished_at)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_runs_source_time
            ON collection_runs(source_name, finished_at)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_collection_runs_module_source
            ON collection_runs(module_name, source_name, finished_at)
        """)

    def _create_klines_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(symbol, exchange, timeframe, open_time)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_klines_lookup
            ON klines(symbol, exchange, timeframe, open_time)
        """)

    def _create_tickers_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                last_price REAL,
                open_24h REAL,
                bid REAL,
                bid_volume REAL,
                ask REAL,
                ask_volume REAL,
                previous_close REAL,
                high_24h REAL,
                low_24h REAL,
                vwap_24h REAL,
                volume_24h REAL,
                quote_volume_24h REAL,
                change_abs_24h REAL,
                change_24h REAL,
                mid_price REAL,
                spread REAL,
                spread_bps REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("tickers", {
            "open_24h": "REAL",
            "previous_close": "REAL",
            "vwap_24h": "REAL",
            "change_abs_24h": "REAL",
            "mid_price": "REAL",
            "spread": "REAL",
            "spread_bps": "REAL",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_lookup
            ON tickers(symbol, exchange, timestamp)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tickers_timestamp
            ON tickers(timestamp)
        """)

    def _create_latest_tickers_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                last_price REAL,
                open_24h REAL,
                bid REAL,
                bid_volume REAL,
                ask REAL,
                ask_volume REAL,
                previous_close REAL,
                high_24h REAL,
                low_24h REAL,
                vwap_24h REAL,
                volume_24h REAL,
                quote_volume_24h REAL,
                change_abs_24h REAL,
                change_24h REAL,
                mid_price REAL,
                spread REAL,
                spread_bps REAL,
                timestamp TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange)
            )
        """)
        self._ensure_columns("latest_tickers", {
            "open_24h": "REAL",
            "previous_close": "REAL",
            "vwap_24h": "REAL",
            "change_abs_24h": "REAL",
            "mid_price": "REAL",
            "spread": "REAL",
            "spread_bps": "REAL",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_tickers_lookup
            ON latest_tickers(symbol, exchange)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_tickers_timestamp
            ON latest_tickers(timestamp)
        """)

    def _create_funding_rates_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                funding_rate REAL,
                mark_price REAL,
                index_price REAL,
                next_funding_time TIMESTAMP,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("funding_rates", {
            "mark_price": "REAL",
            "index_price": "REAL",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_funding_lookup
            ON funding_rates(symbol, exchange, timestamp)
        """)
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_funding_rates_symbol_exchange_timestamp
            ON funding_rates(symbol, exchange, timestamp)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_funding_timestamp
            ON funding_rates(timestamp)
        """)

    def _create_latest_funding_rates_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_funding_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                funding_rate REAL,
                mark_price REAL,
                index_price REAL,
                next_funding_time TIMESTAMP,
                timestamp TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange)
            )
        """)
        self._ensure_columns("latest_funding_rates", {
            "mark_price": "REAL",
            "index_price": "REAL",
            "next_funding_time": "TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_funding_lookup
            ON latest_funding_rates(symbol, exchange)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_funding_timestamp
            ON latest_funding_rates(timestamp)
        """)

    def _create_orderbook_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                snapshot_depth INTEGER,
                best_bid REAL,
                best_ask REAL,
                mid_price REAL,
                spread REAL,
                spread_bps REAL,
                bid_depth_notional REAL,
                ask_depth_notional REAL,
                depth_imbalance REAL,
                bids_json TEXT NOT NULL,
                asks_json TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("orderbook_snapshots", {
            "snapshot_depth": "INTEGER",
            "best_bid": "REAL",
            "best_ask": "REAL",
            "mid_price": "REAL",
            "spread": "REAL",
            "spread_bps": "REAL",
            "bid_depth_notional": "REAL",
            "ask_depth_notional": "REAL",
            "depth_imbalance": "REAL",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orderbook_lookup
            ON orderbook_snapshots(symbol, exchange, timestamp)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orderbook_timestamp
            ON orderbook_snapshots(timestamp)
        """)

    def _create_latest_orderbook_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_orderbook_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                snapshot_depth INTEGER,
                best_bid REAL,
                best_ask REAL,
                mid_price REAL,
                spread REAL,
                spread_bps REAL,
                bid_depth_notional REAL,
                ask_depth_notional REAL,
                depth_imbalance REAL,
                bids_json TEXT NOT NULL,
                asks_json TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange)
            )
        """)
        self._ensure_columns("latest_orderbook_snapshots", {
            "snapshot_depth": "INTEGER",
            "best_bid": "REAL",
            "best_ask": "REAL",
            "mid_price": "REAL",
            "spread": "REAL",
            "spread_bps": "REAL",
            "bid_depth_notional": "REAL",
            "ask_depth_notional": "REAL",
            "depth_imbalance": "REAL",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_orderbook_lookup
            ON latest_orderbook_snapshots(symbol, exchange)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_orderbook_timestamp
            ON latest_orderbook_snapshots(timestamp)
        """)

    def _create_trade_flow_bars_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_flow_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'spot',
                interval TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                trade_count INTEGER DEFAULT 0,
                buy_trade_count INTEGER DEFAULT 0,
                sell_trade_count INTEGER DEFAULT 0,
                buy_notional REAL DEFAULT 0,
                sell_notional REAL DEFAULT 0,
                aggressive_buy_notional REAL DEFAULT 0,
                aggressive_sell_notional REAL DEFAULT 0,
                net_taker_notional REAL DEFAULT 0,
                cvd REAL DEFAULT 0,
                avg_trade_notional REAL DEFAULT 0,
                largest_trade_notional REAL DEFAULT 0,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval, open_time)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trade_flow_bars_lookup
            ON trade_flow_bars(symbol, exchange, market_type, interval, open_time)
        """)

    def _create_latest_trade_flow_bars_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_trade_flow_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'spot',
                interval TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                trade_count INTEGER DEFAULT 0,
                buy_trade_count INTEGER DEFAULT 0,
                sell_trade_count INTEGER DEFAULT 0,
                buy_notional REAL DEFAULT 0,
                sell_notional REAL DEFAULT 0,
                aggressive_buy_notional REAL DEFAULT 0,
                aggressive_sell_notional REAL DEFAULT 0,
                net_taker_notional REAL DEFAULT 0,
                cvd REAL DEFAULT 0,
                avg_trade_notional REAL DEFAULT 0,
                largest_trade_notional REAL DEFAULT 0,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_trade_flow_bars_lookup
            ON latest_trade_flow_bars(symbol, exchange, market_type, interval)
        """)

    def _create_open_interest_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS open_interest_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open_interest_contracts REAL,
                open_interest_usd REAL,
                open_interest_change_5m REAL,
                open_interest_change_1h REAL,
                open_interest_change_24h REAL,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval, timestamp)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_open_interest_snapshots_lookup
            ON open_interest_snapshots(symbol, exchange, market_type, interval, timestamp)
        """)

    def _create_latest_open_interest_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_open_interest_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open_interest_contracts REAL,
                open_interest_usd REAL,
                open_interest_change_5m REAL,
                open_interest_change_1h REAL,
                open_interest_change_24h REAL,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_open_interest_snapshots_lookup
            ON latest_open_interest_snapshots(symbol, exchange, market_type, interval)
        """)

    def _create_liquidation_bars_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                long_liquidation_notional REAL,
                short_liquidation_notional REAL,
                long_liquidation_count INTEGER,
                short_liquidation_count INTEGER,
                total_liquidation_notional REAL,
                max_single_liquidation_notional REAL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval, open_time)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_liquidation_bars_lookup
            ON liquidation_bars(symbol, exchange, market_type, interval, open_time)
        """)

    def _create_latest_liquidation_bars_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_liquidation_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                long_liquidation_notional REAL,
                short_liquidation_notional REAL,
                long_liquidation_count INTEGER,
                short_liquidation_count INTEGER,
                total_liquidation_notional REAL,
                max_single_liquidation_notional REAL,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_liquidation_bars_lookup
            ON latest_liquidation_bars(symbol, exchange, market_type, interval)
        """)

    def _create_positioning_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS positioning_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                ratio_scope TEXT NOT NULL DEFAULT 'accounts',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                long_ratio REAL,
                short_ratio REAL,
                long_short_ratio REAL,
                top_trader_long_ratio REAL,
                top_trader_short_ratio REAL,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, ratio_scope, interval, timestamp)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positioning_snapshots_lookup
            ON positioning_snapshots(symbol, exchange, market_type, ratio_scope, interval, timestamp)
        """)

    def _create_latest_positioning_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_positioning_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                ratio_scope TEXT NOT NULL DEFAULT 'accounts',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                long_ratio REAL,
                short_ratio REAL,
                long_short_ratio REAL,
                top_trader_long_ratio REAL,
                top_trader_short_ratio REAL,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, ratio_scope, interval)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_positioning_snapshots_lookup
            ON latest_positioning_snapshots(symbol, exchange, market_type, ratio_scope, interval)
        """)

    def _create_basis_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS basis_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                spot_price REAL,
                mark_price REAL,
                index_price REAL,
                basis_abs REAL,
                basis_bps REAL,
                annualized_basis_bps REAL,
                funding_rate REAL,
                next_funding_time TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval, timestamp)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_basis_snapshots_lookup
            ON basis_snapshots(symbol, exchange, market_type, interval, timestamp)
        """)

    def _create_latest_basis_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_basis_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'linear_swap',
                interval TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                spot_price REAL,
                mark_price REAL,
                index_price REAL,
                basis_abs REAL,
                basis_bps REAL,
                annualized_basis_bps REAL,
                funding_rate REAL,
                next_funding_time TIMESTAMP,
                raw_payload_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange, market_type, interval)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_basis_snapshots_lookup
            ON latest_basis_snapshots(symbol, exchange, market_type, interval)
        """)

    def _create_news_articles_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_type TEXT DEFAULT 'rss',
                feed_url TEXT,
                category TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                content_text TEXT,
                url TEXT NOT NULL,
                url_hash TEXT NOT NULL,
                author TEXT,
                published_at TIMESTAMP,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                language TEXT,
                sentiment_label TEXT,
                relevance_symbols TEXT,
                tags TEXT,
                image_url TEXT,
                external_id TEXT,
                raw_payload_json TEXT,
                UNIQUE(url_hash)
            )
        """)
        self._ensure_columns("news_articles", {
            "source_type": "TEXT",
            "feed_url": "TEXT",
            "category": "TEXT",
            "summary": "TEXT",
            "content_text": "TEXT",
            "url_hash": "TEXT",
            "author": "TEXT",
            "published_at": "TIMESTAMP",
            "collected_at": "TIMESTAMP",
            "language": "TEXT",
            "sentiment_label": "TEXT",
            "relevance_symbols": "TEXT",
            "tags": "TEXT",
            "image_url": "TEXT",
            "external_id": "TEXT",
            "raw_payload_json": "TEXT",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_news_articles_url_hash
            ON news_articles(url_hash)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_articles_source_published_at
            ON news_articles(source, published_at)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_articles_published_at
            ON news_articles(published_at)
        """)

    def _create_event_calendar_events_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS event_calendar_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                symbol TEXT NOT NULL DEFAULT 'MARKET',
                scheduled_at TIMESTAMP NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                importance_score REAL,
                source_name TEXT NOT NULL,
                status TEXT DEFAULT 'scheduled',
                source_url TEXT,
                external_id TEXT,
                tags TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_key)
            )
        """)
        self._ensure_columns("event_calendar_events", {
            "event_type": "TEXT",
            "title": "TEXT",
            "description": "TEXT",
            "symbol": "TEXT DEFAULT 'MARKET'",
            "scheduled_at": "TIMESTAMP",
            "timezone": "TEXT DEFAULT 'UTC'",
            "importance_score": "REAL",
            "source_name": "TEXT",
            "status": "TEXT DEFAULT 'scheduled'",
            "source_url": "TEXT",
            "external_id": "TEXT",
            "tags": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "raw_payload_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_event_calendar_events_event_key
            ON event_calendar_events(event_key)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_calendar_events_scheduled_at
            ON event_calendar_events(status, scheduled_at)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_calendar_events_symbol_time
            ON event_calendar_events(symbol, scheduled_at)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_calendar_events_source_type
            ON event_calendar_events(source_name, event_type, scheduled_at)
        """)

    def _create_macro_factor_catalog_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_factor_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                description TEXT,
                default_interval TEXT NOT NULL,
                unit TEXT,
                currency TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                market_region TEXT,
                market_session TEXT,
                staleness_ttl_seconds INTEGER,
                is_intraday_enabled INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                raw_meta_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_id)
            )
        """)
        self._ensure_columns("macro_factor_catalog", {
            "factor_type": "TEXT",
            "description": "TEXT",
            "default_interval": "TEXT",
            "unit": "TEXT",
            "currency": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "market_region": "TEXT",
            "market_session": "TEXT",
            "staleness_ttl_seconds": "INTEGER",
            "is_intraday_enabled": "INTEGER DEFAULT 0",
            "enabled": "INTEGER DEFAULT 1",
            "raw_meta_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_macro_factor_catalog_factor_id
            ON macro_factor_catalog(factor_id)
        """)

    def _create_macro_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                session_date TEXT,
                value REAL NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                unit TEXT,
                currency TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                available_at TIMESTAMP,
                is_revision INTEGER DEFAULT 0,
                revision_seq INTEGER DEFAULT 0,
                quality_flag TEXT DEFAULT 'ok',
                is_market_open INTEGER,
                ingest_run_id TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_payload_json TEXT,
                UNIQUE(factor_id, interval, observation_time)
            )
        """)
        self._ensure_columns("macro_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "session_date": "TEXT",
            "value": "REAL",
            "open": "REAL",
            "high": "REAL",
            "low": "REAL",
            "close": "REAL",
            "volume": "REAL",
            "unit": "TEXT",
            "currency": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "available_at": "TIMESTAMP",
            "is_revision": "INTEGER DEFAULT 0",
            "revision_seq": "INTEGER DEFAULT 0",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "is_market_open": "INTEGER",
            "ingest_run_id": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "raw_payload_json": "TEXT",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_macro_timeseries_point
            ON macro_timeseries(factor_id, interval, observation_time)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_macro_timeseries_lookup
            ON macro_timeseries(factor_id, interval, observation_time)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_macro_timeseries_observation_time
            ON macro_timeseries(observation_time)
        """)

    def _create_latest_macro_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_macro_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                unit TEXT,
                currency TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                quality_flag TEXT DEFAULT 'ok',
                is_market_open INTEGER,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_id, interval)
            )
        """)
        self._ensure_columns("latest_macro_timeseries", {
            "factor_type": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "open": "REAL",
            "high": "REAL",
            "low": "REAL",
            "close": "REAL",
            "unit": "TEXT",
            "currency": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "is_market_open": "INTEGER",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_macro_timeseries_factor_interval
            ON latest_macro_timeseries(factor_id, interval)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_macro_timeseries_lookup
            ON latest_macro_timeseries(factor_id, interval)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_macro_timeseries_observation_time
            ON latest_macro_timeseries(observation_time)
        """)

    def _create_alternative_factor_catalog_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS alternative_factor_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_scope TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                default_interval TEXT NOT NULL,
                unit TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                config_version TEXT DEFAULT 'v1',
                staleness_ttl_seconds INTEGER,
                enabled INTEGER DEFAULT 1,
                raw_meta_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_id)
            )
        """)
        self._ensure_columns("alternative_factor_catalog", {
            "factor_type": "TEXT",
            "entity_scope": "TEXT",
            "entity_type": "TEXT",
            "description": "TEXT",
            "default_interval": "TEXT",
            "unit": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "config_version": "TEXT DEFAULT 'v1'",
            "staleness_ttl_seconds": "INTEGER",
            "enabled": "INTEGER DEFAULT 1",
            "raw_meta_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_alternative_factor_catalog_factor_id
            ON alternative_factor_catalog(factor_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alternative_factor_catalog_lookup
            ON alternative_factor_catalog(category, source_name, enabled)
        """)

    def _create_alternative_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS alternative_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    observation_time,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("alternative_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_alternative_timeseries_point
            ON alternative_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alternative_timeseries_lookup
            ON alternative_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_alternative_timeseries_observation_time
            ON alternative_timeseries(observation_time)
        """)

    def _create_latest_alternative_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_alternative_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("latest_alternative_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_alternative_timeseries_identity
            ON latest_alternative_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_alternative_timeseries_lookup
            ON latest_alternative_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_alternative_timeseries_observation_time
            ON latest_alternative_timeseries(observation_time)
        """)

    def _create_onchain_factor_catalog_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS onchain_factor_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_scope TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                default_interval TEXT NOT NULL,
                unit TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                config_version TEXT DEFAULT 'v1',
                staleness_ttl_seconds INTEGER,
                enabled INTEGER DEFAULT 1,
                raw_meta_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_id)
            )
        """)
        self._ensure_columns("onchain_factor_catalog", {
            "factor_type": "TEXT",
            "entity_scope": "TEXT",
            "entity_type": "TEXT",
            "description": "TEXT",
            "default_interval": "TEXT",
            "unit": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "config_version": "TEXT DEFAULT 'v1'",
            "staleness_ttl_seconds": "INTEGER",
            "enabled": "INTEGER DEFAULT 1",
            "raw_meta_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_onchain_factor_catalog_factor_id
            ON onchain_factor_catalog(factor_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onchain_factor_catalog_lookup
            ON onchain_factor_catalog(category, source_name, enabled)
        """)

    def _create_onchain_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS onchain_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    observation_time,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("onchain_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_onchain_timeseries_point
            ON onchain_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onchain_timeseries_lookup
            ON onchain_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onchain_timeseries_observation_time
            ON onchain_timeseries(observation_time)
        """)

    def _create_latest_onchain_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_onchain_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("latest_onchain_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_onchain_timeseries_identity
            ON latest_onchain_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_onchain_timeseries_lookup
            ON latest_onchain_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_onchain_timeseries_observation_time
            ON latest_onchain_timeseries(observation_time)
        """)

    def _create_tokenomics_factor_catalog_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tokenomics_factor_catalog (
                factor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_scope TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                default_interval TEXT NOT NULL,
                unit TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                config_version TEXT DEFAULT 'v1',
                staleness_ttl_seconds INTEGER DEFAULT 86400,
                enabled INTEGER DEFAULT 1,
                raw_meta_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("tokenomics_factor_catalog", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_scope": "TEXT",
            "entity_type": "TEXT",
            "description": "TEXT",
            "default_interval": "TEXT",
            "unit": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "config_version": "TEXT DEFAULT 'v1'",
            "staleness_ttl_seconds": "INTEGER DEFAULT 86400",
            "enabled": "INTEGER DEFAULT 1",
            "raw_meta_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tokenomics_factor_catalog_source
            ON tokenomics_factor_catalog(source_name, enabled)
        """)

    def _create_tokenomics_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tokenomics_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    observation_time,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("tokenomics_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tokenomics_timeseries_identity
            ON tokenomics_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tokenomics_timeseries_lookup
            ON tokenomics_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tokenomics_timeseries_observation_time
            ON tokenomics_timeseries(observation_time)
        """)

    def _create_latest_tokenomics_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_tokenomics_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("latest_tokenomics_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_tokenomics_timeseries_identity
            ON latest_tokenomics_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_tokenomics_timeseries_lookup
            ON latest_tokenomics_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_tokenomics_timeseries_observation_time
            ON latest_tokenomics_timeseries(observation_time)
        """)

    def _create_options_factor_catalog_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS options_factor_catalog (
                factor_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_scope TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                description TEXT,
                default_interval TEXT NOT NULL,
                unit TEXT,
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                config_version TEXT DEFAULT 'v1',
                staleness_ttl_seconds INTEGER DEFAULT 14400,
                enabled INTEGER DEFAULT 1,
                raw_meta_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("options_factor_catalog", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_scope": "TEXT",
            "entity_type": "TEXT",
            "description": "TEXT",
            "default_interval": "TEXT",
            "unit": "TEXT",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "config_version": "TEXT DEFAULT 'v1'",
            "staleness_ttl_seconds": "INTEGER DEFAULT 14400",
            "enabled": "INTEGER DEFAULT 1",
            "raw_meta_json": "TEXT",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_options_factor_catalog_source
            ON options_factor_catalog(source_name, enabled)
        """)

    def _create_options_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS options_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    observation_time,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("options_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_options_timeseries_identity
            ON options_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_options_timeseries_lookup
            ON options_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                observation_time
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_options_timeseries_observation_time
            ON options_timeseries(observation_time)
        """)

    def _create_latest_options_timeseries_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS latest_options_timeseries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_flag TEXT DEFAULT 'ok',
                dimensions_key TEXT NOT NULL DEFAULT 'base',
                dimensions_json TEXT,
                config_version TEXT DEFAULT 'v1',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(
                    factor_id,
                    entity_type,
                    entity_key,
                    interval,
                    dimensions_key,
                    source_name,
                    config_version
                )
            )
        """)
        self._ensure_columns("latest_options_timeseries", {
            "category": "TEXT",
            "factor_type": "TEXT",
            "entity_type": "TEXT",
            "entity_key": "TEXT",
            "interval": "TEXT",
            "observation_time": "TIMESTAMP",
            "value": "REAL",
            "unit": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "dimensions_key": "TEXT DEFAULT 'base'",
            "dimensions_json": "TEXT",
            "config_version": "TEXT DEFAULT 'v1'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_latest_options_timeseries_identity
            ON latest_options_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval,
                dimensions_key,
                source_name,
                config_version
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_options_timeseries_lookup
            ON latest_options_timeseries(
                factor_id,
                entity_type,
                entity_key,
                interval
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_latest_options_timeseries_observation_time
            ON latest_options_timeseries(observation_time)
        """)

    def _create_token_unlock_events_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS token_unlock_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                event_type TEXT NOT NULL,
                scheduled_at TIMESTAMP NOT NULL,
                unlock_amount REAL,
                unlock_value_usd REAL,
                unlock_pct_float REAL,
                beneficiary_group TEXT,
                status TEXT DEFAULT 'scheduled',
                source_name TEXT NOT NULL,
                source_url TEXT,
                raw_payload_json TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset, event_type, scheduled_at, source_name)
            )
        """)
        self._ensure_columns("token_unlock_events", {
            "unlock_amount": "REAL",
            "unlock_value_usd": "REAL",
            "unlock_pct_float": "REAL",
            "beneficiary_group": "TEXT",
            "status": "TEXT DEFAULT 'scheduled'",
            "source_url": "TEXT",
            "raw_payload_json": "TEXT",
            "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_token_unlock_events_identity
            ON token_unlock_events(asset, event_type, scheduled_at, source_name)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_token_unlock_events_lookup
            ON token_unlock_events(asset, scheduled_at, status)
        """)

    def _create_macro_context_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS macro_context_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                factor_type TEXT NOT NULL,
                interval TEXT NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,
                observation_time TIMESTAMP NOT NULL,
                latest_value REAL NOT NULL,
                unit TEXT,
                currency TEXT,
                quality_flag TEXT DEFAULT 'ok',
                source_name TEXT NOT NULL,
                source_symbol TEXT NOT NULL,
                source_priority TEXT DEFAULT 'primary',
                freshness_seconds REAL,
                staleness_ttl_seconds INTEGER,
                is_stale INTEGER DEFAULT 0,
                reference_1d_time TIMESTAMP,
                reference_1d_value REAL,
                change_1d_abs REAL,
                change_1d_pct REAL,
                change_1d_bps REAL,
                reference_5d_time TIMESTAMP,
                reference_5d_value REAL,
                change_5d_abs REAL,
                change_5d_pct REAL,
                change_5d_bps REAL,
                context_completeness_score REAL,
                raw_context_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(factor_id, interval, observation_time)
            )
        """)
        self._ensure_columns("macro_context_snapshots", {
            "name": "TEXT",
            "category": "TEXT",
            "factor_type": "TEXT",
            "interval": "TEXT",
            "snapshot_time": "TIMESTAMP",
            "observation_time": "TIMESTAMP",
            "latest_value": "REAL",
            "unit": "TEXT",
            "currency": "TEXT",
            "quality_flag": "TEXT DEFAULT 'ok'",
            "source_name": "TEXT",
            "source_symbol": "TEXT",
            "source_priority": "TEXT DEFAULT 'primary'",
            "freshness_seconds": "REAL",
            "staleness_ttl_seconds": "INTEGER",
            "is_stale": "INTEGER DEFAULT 0",
            "reference_1d_time": "TIMESTAMP",
            "reference_1d_value": "REAL",
            "change_1d_abs": "REAL",
            "change_1d_pct": "REAL",
            "change_1d_bps": "REAL",
            "reference_5d_time": "TIMESTAMP",
            "reference_5d_value": "REAL",
            "change_5d_abs": "REAL",
            "change_5d_pct": "REAL",
            "change_5d_bps": "REAL",
            "context_completeness_score": "REAL",
            "raw_context_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_macro_context_snapshots_point
            ON macro_context_snapshots(factor_id, interval, observation_time)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_macro_context_snapshots_lookup
            ON macro_context_snapshots(factor_id, interval, observation_time)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_macro_context_snapshots_snapshot_time
            ON macro_context_snapshots(snapshot_time)
        """)

    def _create_ai_market_context_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_market_context_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,
                coverage_score REAL,
                data_quality_flag TEXT,
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_key, snapshot_time)
            )
        """)
        self._ensure_columns("ai_market_context_snapshots", {
            "coverage_score": "REAL",
            "data_quality_flag": "TEXT",
            "bundle_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_market_context_snapshots_identity
            ON ai_market_context_snapshots(entity_key, snapshot_time)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_market_context_snapshots_lookup
            ON ai_market_context_snapshots(entity_key, snapshot_time)
        """)

    def _create_market_breadth_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_breadth_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TIMESTAMP NOT NULL,
                scope_kind TEXT NOT NULL DEFAULT 'default',
                breadth_status TEXT NOT NULL DEFAULT 'limited',
                asset_count INTEGER DEFAULT 0,
                ai_ready_asset_count INTEGER DEFAULT 0,
                article_asset_count INTEGER DEFAULT 0,
                unlock_asset_count INTEGER DEFAULT 0,
                breadth_score REAL,
                data_quality_flag TEXT DEFAULT 'partial',
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_time, scope_kind)
            )
        """)
        self._ensure_columns("market_breadth_snapshots", {
            "snapshot_time": "TIMESTAMP",
            "scope_kind": "TEXT NOT NULL DEFAULT 'default'",
            "breadth_status": "TEXT NOT NULL DEFAULT 'limited'",
            "asset_count": "INTEGER DEFAULT 0",
            "ai_ready_asset_count": "INTEGER DEFAULT 0",
            "article_asset_count": "INTEGER DEFAULT 0",
            "unlock_asset_count": "INTEGER DEFAULT 0",
            "breadth_score": "REAL",
            "data_quality_flag": "TEXT DEFAULT 'partial'",
            "bundle_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_market_breadth_snapshots_identity
            ON market_breadth_snapshots(snapshot_time, scope_kind)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_breadth_snapshots_lookup
            ON market_breadth_snapshots(snapshot_time, scope_kind)
        """)

    def _create_market_structure_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_structure_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TIMESTAMP NOT NULL,
                scope_kind TEXT NOT NULL DEFAULT 'default',
                asset_count INTEGER DEFAULT 0,
                data_quality_flag TEXT DEFAULT 'thin',
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_time, scope_kind)
            )
        """)
        self._ensure_columns("market_structure_snapshots", {
            "snapshot_time": "TIMESTAMP",
            "scope_kind": "TEXT NOT NULL DEFAULT 'default'",
            "asset_count": "INTEGER DEFAULT 0",
            "data_quality_flag": "TEXT DEFAULT 'thin'",
            "bundle_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_market_structure_snapshots_identity
            ON market_structure_snapshots(snapshot_time, scope_kind)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_structure_snapshots_lookup
            ON market_structure_snapshots(snapshot_time, scope_kind)
        """)

    def _create_asset_readiness_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_readiness_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TIMESTAMP NOT NULL,
                scope_kind TEXT NOT NULL DEFAULT 'default',
                market_world_status TEXT NOT NULL DEFAULT 'blocked',
                asset_count INTEGER DEFAULT 0,
                ready_asset_count INTEGER DEFAULT 0,
                partial_asset_count INTEGER DEFAULT 0,
                thin_asset_count INTEGER DEFAULT 0,
                blocked_asset_count INTEGER DEFAULT 0,
                average_readiness_score REAL,
                data_quality_flag TEXT DEFAULT 'blocked',
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(snapshot_time, scope_kind)
            )
        """)
        self._ensure_columns("asset_readiness_snapshots", {
            "snapshot_time": "TIMESTAMP",
            "scope_kind": "TEXT NOT NULL DEFAULT 'default'",
            "market_world_status": "TEXT NOT NULL DEFAULT 'blocked'",
            "asset_count": "INTEGER DEFAULT 0",
            "ready_asset_count": "INTEGER DEFAULT 0",
            "partial_asset_count": "INTEGER DEFAULT 0",
            "thin_asset_count": "INTEGER DEFAULT 0",
            "blocked_asset_count": "INTEGER DEFAULT 0",
            "average_readiness_score": "REAL",
            "data_quality_flag": "TEXT DEFAULT 'blocked'",
            "bundle_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_readiness_snapshots_identity
            ON asset_readiness_snapshots(snapshot_time, scope_kind)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_asset_readiness_snapshots_lookup
            ON asset_readiness_snapshots(snapshot_time, scope_kind)
        """)

    def _create_data_quality_audit_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_audit_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_scope TEXT NOT NULL,
                snapshot_time TIMESTAMP NOT NULL,
                world_model_status TEXT,
                is_market_data_ready_for_ai INTEGER DEFAULT 0,
                required_band_count INTEGER DEFAULT 0,
                required_ready_band_count INTEGER DEFAULT 0,
                optional_band_count INTEGER DEFAULT 0,
                optional_ready_band_count INTEGER DEFAULT 0,
                critical_gap_count INTEGER DEFAULT 0,
                critical_gap_band_names_json TEXT,
                blocked_band_names_json TEXT,
                partial_band_names_json TEXT,
                bands_json TEXT,
                raw_audit_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._ensure_columns("data_quality_audit_snapshots", {
            "audit_scope": "TEXT",
            "snapshot_time": "TIMESTAMP",
            "world_model_status": "TEXT",
            "is_market_data_ready_for_ai": "INTEGER DEFAULT 0",
            "required_band_count": "INTEGER DEFAULT 0",
            "required_ready_band_count": "INTEGER DEFAULT 0",
            "optional_band_count": "INTEGER DEFAULT 0",
            "optional_ready_band_count": "INTEGER DEFAULT 0",
            "critical_gap_count": "INTEGER DEFAULT 0",
            "critical_gap_band_names_json": "TEXT",
            "blocked_band_names_json": "TEXT",
            "partial_band_names_json": "TEXT",
            "bands_json": "TEXT",
            "raw_audit_json": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        })
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_data_quality_audit_snapshots_lookup
            ON data_quality_audit_snapshots(audit_scope, snapshot_time)
        """)

    def _create_cross_asset_analysis_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_correlation_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                window_hours INTEGER NOT NULL,
                matrix_json TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                avg_correlation REAL,
                max_correlation REAL,
                min_correlation REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_relative_strength (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset TEXT NOT NULL,
                sector TEXT,
                tier TEXT,
                rs_vs_btc_7d REAL,
                rs_vs_btc_3d REAL,
                rs_vs_btc_1d REAL,
                rs_rank INTEGER,
                rs_momentum TEXT,
                price_change_7d_pct REAL,
                volume_change_7d_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_sector_rotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                sector TEXT NOT NULL,
                sector_return_7d REAL,
                sector_volatility_7d REAL,
                sector_momentum_score REAL,
                sector_net_flow_24h REAL,
                sector_oi_change_24h REAL,
                constituent_count INTEGER,
                rotation_phase TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_fund_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                scope TEXT NOT NULL,
                net_taker_flow_1h REAL,
                net_taker_flow_24h REAL,
                oi_change_1h REAL,
                oi_change_24h REAL,
                aggressive_buy_share REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_portfolio_risk_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                portfolio_name TEXT NOT NULL DEFAULT 'default',
                asset_count INTEGER NOT NULL,
                weights_json TEXT NOT NULL,
                annualized_volatility REAL,
                daily_var_95 REAL,
                daily_var_99 REAL,
                hhi REAL,
                effective_n REAL,
                max_weight REAL,
                diversification_ratio REAL,
                risk_contributions_json TEXT,
                sector_concentration_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_feature_standardization_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                raw_value REAL,
                zscore_7d REAL,
                zscore_30d REAL,
                percentile_30d REAL,
                cross_asset_rank INTEGER,
                cross_asset_rank_total INTEGER,
                regime_label TEXT,
                confidence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fsd_unique
            ON feature_standardization_details(snapshot_time, symbol, feature_name)
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_composites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                composite_name TEXT NOT NULL,
                composite_zscore REAL,
                composite_percentile REAL,
                cross_asset_rank INTEGER,
                cross_asset_rank_total INTEGER,
                regime_label TEXT,
                confidence TEXT,
                component_count INTEGER,
                component_names TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fsc_unique
            ON feature_standardization_composites(snapshot_time, symbol, composite_name)
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                feature_count INTEGER NOT NULL,
                composite_count INTEGER NOT NULL,
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_merged_klines_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS merged_klines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                exchange_count INTEGER NOT NULL,
                source_exchanges TEXT NOT NULL,
                merge_method TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe, open_time)
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_merged_klines_lookup
            ON merged_klines(symbol, timeframe, open_time)
        """)

    def _create_technical_indicators_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS technical_indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TIMESTAMP NOT NULL,
                close REAL,
                volume REAL,
                sma_5 REAL,
                sma_10 REAL,
                sma_20 REAL,
                sma_60 REAL,
                ema_7 REAL,
                ema_20 REAL,
                ema_50 REAL,
                macd_line REAL,
                macd_signal REAL,
                macd_hist REAL,
                rsi_14 REAL,
                bb_middle REAL,
                bb_upper REAL,
                bb_lower REAL,
                bb_width REAL,
                atr_14 REAL,
                relative_volatility_index_14 REAL,
                stoch_k REAL,
                stoch_d REAL,
                stoch_j REAL,
                plus_di_14 REAL,
                minus_di_14 REAL,
                adx_14 REAL,
                obv REAL,
                return_1 REAL,
                return_5 REAL,
                return_20 REAL,
                volatility_20 REAL,
                sma_120 REAL,
                ema_100 REAL,
                dema_20 REAL,
                tema_20 REAL,
                hma_21 REAL,
                zlema_20 REAL,
                vwma_20 REAL,
                rolling_vwap_20 REAL,
                rolling_vwap_deviation_20 REAL,
                roc_12 REAL,
                momentum_10 REAL,
                rmi_14_5 REAL,
                cfo_20 REAL,
                awesome_oscillator_5_34 REAL,
                accelerator_oscillator_5_34 REAL,
                pfe_10 REAL,
                cci_20 REAL,
                mfi_14 REAL,
                williams_r_14 REAL,
                cmf_20 REAL,
                donchian_high_20 REAL,
                donchian_low_20 REAL,
                donchian_mid_20 REAL,
                ichimoku_tenkan_9 REAL,
                ichimoku_kijun_26 REAL,
                ichimoku_senkou_a REAL,
                ichimoku_senkou_b_52 REAL,
                ppo_line REAL,
                ppo_signal REAL,
                ppo_hist REAL,
                volume_ratio_20 REAL,
                price_zscore_20 REAL,
                atr_pct_14 REAL,
                parkinson_volatility_20 REAL,
                garman_klass_volatility_20 REAL,
                rogers_satchell_volatility_20 REAL,
                keltner_middle_20 REAL,
                keltner_upper_20 REAL,
                keltner_lower_20 REAL,
                stoch_rsi_k_14 REAL,
                stoch_rsi_d_14 REAL,
                aroon_up_25 REAL,
                aroon_down_25 REAL,
                aroon_osc_25 REAL,
                tsi_line REAL,
                tsi_signal REAL,
                stc_10_23_50 REAL,
                ultimate_osc REAL,
                adl REAL,
                chaikin_oscillator REAL,
                bb_percent_b REAL,
                donchian_width_20 REAL,
                donchian_position_20 REAL,
                vhf_28 REAL,
                linear_reg_slope_20 REAL,
                linear_reg_r2_20 REAL,
                regression_distance_20 REAL,
                ema_20_slope_5 REAL,
                sma_20_slope_5 REAL,
                rolling_drawdown_20 REAL,
                cmo_14 REAL,
                force_index_13 REAL,
                supertrend_10_3 REAL,
                supertrend_direction_10_3 REAL,
                psar REAL,
                psar_trend REAL,
                trix_30 REAL,
                dpo_20 REAL,
                vortex_plus_14 REAL,
                vortex_minus_14 REAL,
                kama_10_2_30 REAL,
                mass_index_25 REAL,
                efficiency_ratio_10 REAL,
                choppiness_index_14 REAL,
                ulcer_index_14 REAL,
                fisher_transform_9 REAL,
                fisher_trigger_9 REAL,
                coppock_curve_11_14_10 REAL,
                coppock_signal_10 REAL,
                kst_line REAL,
                kst_signal REAL,
                qstick_10 REAL,
                demarker_14 REAL,
                rvi_10 REAL,
                rvi_signal_4 REAL,
                squeeze_on_20 REAL,
                squeeze_off_20 REAL,
                price_percent_rank_20 REAL,
                volume_percent_rank_20 REAL,
                atr_percent_rank_20 REAL,
                volume_zscore_20 REAL,
                balance_of_power REAL,
                price_volume_trend REAL,
                nvi REAL,
                pvi REAL,
                kvo_line REAL,
                kvo_signal REAL,
                ease_of_movement_14 REAL,
                volume_oscillator_5_20 REAL,
                pvo_line REAL,
                pvo_signal REAL,
                pvo_hist REAL,
                downside_deviation_20 REAL,
                upside_deviation_20 REAL,
                sharpe_like_20 REAL,
                sortino_like_20 REAL,
                calmar_like_20 REAL,
                gain_to_pain_ratio_20 REAL,
                median_return_20 REAL,
                mad_return_20 REAL,
                return_iqr_20 REAL,
                tail_ratio_20 REAL,
                return_skew_20 REAL,
                return_kurtosis_20 REAL,
                bull_power_13 REAL,
                bear_power_13 REAL,
                ticker_exchange_count REAL,
                ticker_last_price_mean REAL,
                ticker_mid_price_mean REAL,
                ticker_spread_bps_mean REAL,
                ticker_quote_volume_24h_sum REAL,
                ticker_quote_volume_24h_mean REAL,
                ticker_change_24h_mean REAL,
                ticker_vwap_24h_mean REAL,
                cross_exchange_last_price_std REAL,
                cross_exchange_last_price_range_bps REAL,
                funding_exchange_count REAL,
                funding_rate_mean REAL,
                funding_rate_std REAL,
                funding_basis_bps_mean REAL,
                orderbook_exchange_count REAL,
                orderbook_mid_price_mean REAL,
                orderbook_spread_bps_mean REAL,
                orderbook_bid_depth_notional_sum REAL,
                orderbook_ask_depth_notional_sum REAL,
                orderbook_total_depth_notional REAL,
                orderbook_depth_imbalance_mean REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe, open_time)
            )
        """)
        self._ensure_columns("technical_indicators", self._technical_indicator_columns())
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_technical_indicators_lookup
            ON technical_indicators(symbol, timeframe, open_time)
        """)

    def _create_exchange_comparison_snapshots_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_comparison_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange_a TEXT NOT NULL,
                exchange_b TEXT NOT NULL,
                compare_window_seconds INTEGER NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                ticker_timestamp_a TIMESTAMP,
                ticker_timestamp_b TIMESTAMP,
                orderbook_timestamp_a TIMESTAMP,
                orderbook_timestamp_b TIMESTAMP,
                funding_timestamp_a TIMESTAMP,
                funding_timestamp_b TIMESTAMP,
                last_price_a REAL,
                last_price_b REAL,
                mid_price_a REAL,
                mid_price_b REAL,
                bid_a REAL,
                ask_a REAL,
                bid_b REAL,
                ask_b REAL,
                spread_bps_a REAL,
                spread_bps_b REAL,
                quote_volume_24h_a REAL,
                quote_volume_24h_b REAL,
                bid_depth_notional_a REAL,
                bid_depth_notional_b REAL,
                ask_depth_notional_a REAL,
                ask_depth_notional_b REAL,
                depth_imbalance_a REAL,
                depth_imbalance_b REAL,
                funding_rate_a REAL,
                funding_rate_b REAL,
                mark_price_a REAL,
                mark_price_b REAL,
                index_price_a REAL,
                index_price_b REAL,
                last_diff_abs REAL,
                last_diff_bps REAL,
                mid_diff_abs REAL,
                mid_diff_bps REAL,
                bid_diff_bps REAL,
                ask_diff_bps REAL,
                funding_rate_diff_abs REAL,
                funding_rate_diff_bps REAL,
                mark_price_diff_bps REAL,
                index_price_diff_bps REAL,
                cross_spread_ab_bps REAL,
                cross_spread_ba_bps REAL,
                estimated_fee_bps REAL,
                estimated_slippage_ab_bps REAL,
                estimated_slippage_ba_bps REAL,
                estimated_slippage_bps REAL,
                net_cross_spread_ab_bps REAL,
                net_cross_spread_ba_bps REAL,
                net_cross_spread_max_bps REAL,
                quote_volume_ratio REAL,
                bid_depth_ratio REAL,
                ask_depth_ratio REAL,
                total_depth_ratio REAL,
                spread_bps_gap REAL,
                depth_imbalance_gap REAL,
                inter_exchange_ticker_gap_ms REAL,
                inter_exchange_funding_gap_ms REAL,
                context_timeframe TEXT,
                context_open_time TIMESTAMP,
                context_age_seconds REAL,
                context_close REAL,
                context_rsi_14 REAL,
                context_macd_hist REAL,
                context_atr_pct_14 REAL,
                context_volatility_20 REAL,
                context_adx_14 REAL,
                context_bb_width REAL,
                context_price_zscore_20 REAL,
                context_volume_ratio_20 REAL,
                context_cross_exchange_last_price_range_bps REAL,
                context_funding_basis_bps_mean REAL,
                context_orderbook_total_depth_notional REAL,
                best_buy_exchange TEXT,
                best_sell_exchange TEXT,
                opportunity_type TEXT,
                signal_label TEXT,
                signal_strength REAL,
                is_actionable INTEGER DEFAULT 0,
                anomaly_score REAL,
                execution_preference_score REAL,
                market_regime_label TEXT,
                funding_regime_label TEXT,
                context_completeness_score REAL,
                data_quality_flag TEXT,
                raw_context_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, exchange_a, exchange_b, compare_window_seconds, timestamp)
            )
        """)
        self._ensure_columns(
            "exchange_comparison_snapshots",
            self._exchange_comparison_snapshot_columns(),
        )
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_comparison_snapshot_lookup
            ON exchange_comparison_snapshots(symbol, timestamp)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_comparison_pair_lookup
            ON exchange_comparison_snapshots(exchange_a, exchange_b, timestamp)
        """)

    def _sync_latest_snapshot_tables(self):
        self._sync_latest_snapshot_table(
            source_table="tickers",
            latest_table="latest_tickers",
            columns=[
                "symbol",
                "exchange",
                "last_price",
                "open_24h",
                "bid",
                "bid_volume",
                "ask",
                "ask_volume",
                "previous_close",
                "high_24h",
                "low_24h",
                "vwap_24h",
                "volume_24h",
                "quote_volume_24h",
                "change_abs_24h",
                "change_24h",
                "mid_price",
                "spread",
                "spread_bps",
                "timestamp",
            ],
        )
        self._sync_latest_snapshot_table(
            source_table="funding_rates",
            latest_table="latest_funding_rates",
            columns=[
                "symbol",
                "exchange",
                "funding_rate",
                "mark_price",
                "index_price",
                "next_funding_time",
                "timestamp",
            ],
        )
        self._sync_latest_snapshot_table(
            source_table="orderbook_snapshots",
            latest_table="latest_orderbook_snapshots",
            columns=[
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
                "bids_json",
                "asks_json",
                "timestamp",
            ],
        )

    def _sync_latest_snapshot_table(
        self,
        source_table: str,
        latest_table: str,
        columns: list[str],
    ):
        update_columns = [
            column
            for column in columns
            if column not in {"symbol", "exchange"}
        ]
        self.conn.execute(f"""
            WITH latest_time AS (
                SELECT symbol, exchange, MAX(timestamp) AS latest_timestamp
                FROM {source_table}
                GROUP BY symbol, exchange
            ),
            latest_rows AS (
                SELECT MAX(source.id) AS latest_id
                FROM {source_table} AS source
                INNER JOIN latest_time
                    ON source.symbol = latest_time.symbol
                    AND source.exchange = latest_time.exchange
                    AND source.timestamp = latest_time.latest_timestamp
                GROUP BY source.symbol, source.exchange
            )
            INSERT INTO {latest_table} ({", ".join(columns)})
            SELECT {", ".join(columns)}
            FROM {source_table}
            WHERE id IN (SELECT latest_id FROM latest_rows)
            ON CONFLICT(symbol, exchange) DO UPDATE SET
                {", ".join(f"{column}=excluded.{column}" for column in update_columns)},
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= {latest_table}.timestamp
        """)

    # ------------------------------------------------------------------
    # 慢查询阈值（秒）
    # ------------------------------------------------------------------
    _SLOW_QUERY_THRESHOLD = float(os.environ.get("DB_SLOW_QUERY_THRESHOLD_MS", "100")) / 1000.0

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句"""
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        self._log_slow_query(sql, start)
        return cursor

    def execute_many(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """批量执行 SQL 语句"""
        start = time.monotonic()
        cursor = self.conn.executemany(sql, params_list)
        self._log_slow_query(sql, start)
        return cursor

    def execute_many_chunked(
        self,
        sql: str,
        params_list: list[tuple],
        chunk_size: int = 500,
        commit_per_chunk: bool = False,
    ) -> int:
        """分块批量执行，适用于大批量写入（>1000 条）。

        Parameters
        ----------
        sql : str
            INSERT/UPDATE SQL
        params_list : list[tuple]
            参数列表
        chunk_size : int
            每块大小，默认 500（SQLite 最优实践）
        commit_per_chunk : bool
            是否每块提交一次（降低 WAL 积压，代价是非原子性）

        Returns
        -------
        int
            总写入行数
        """
        if not params_list:
            return 0
        total = 0
        start = time.monotonic()
        for i in range(0, len(params_list), chunk_size):
            chunk = params_list[i:i + chunk_size]
            self.conn.executemany(sql, chunk)
            total += len(chunk)
            if commit_per_chunk:
                self.conn.commit()
        self._log_slow_query(f"chunked({len(params_list)}): {sql[:100]}", start)
        return total

    def commit(self):
        """提交事务"""
        self.conn.commit()

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录"""
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        row = cursor.fetchone()
        self._log_slow_query(sql, start)
        return row

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """查询所有记录"""
        start = time.monotonic()
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()
        self._log_slow_query(sql, start)
        return rows

    def _log_slow_query(self, sql: str, start: float) -> None:
        elapsed = time.monotonic() - start
        if elapsed >= self._SLOW_QUERY_THRESHOLD:
            logger.warning(
                "slow query ({:.0f}ms): {}",
                elapsed * 1000,
                sql[:200].replace("\n", " ").strip(),
            )

    def record_collection_run(
        self,
        module_name: str,
        source_name: str,
        job_name: str,
        status: str,
        started_at: str,
        finished_at: str,
        item_count: int = 0,
        duration_seconds: float | None = None,
        message: str | None = None,
        metadata_json: str | None = None,
        commit: bool = True,
    ):
        self.execute(
            """
            INSERT INTO collection_runs (
                module_name, source_name, job_name, status, item_count,
                started_at, finished_at, duration_seconds, message, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module_name,
                source_name,
                job_name,
                status,
                item_count,
                started_at,
                finished_at,
                duration_seconds,
                message,
                metadata_json,
            ),
        )
        if commit:
            self.commit()

    def close(self):
        """关闭数据库连接"""
        with self._connections_lock:
            connections = list(self._connections.items())
            self._connections.clear()

        for thread_id, conn in connections:
            try:
                conn.close()
                logger.debug(f"数据库连接已关闭 [thread={thread_id}]")
            except Exception as e:
                logger.warning(f"关闭数据库连接失败 [thread={thread_id}]: {e}")

        self._local.conn = None
