"""001_initial — 初始 schema 迁移（从现有 SQLite 表定义生成）。

Revision ID: 001_initial
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ["exchange_data", "market_data", "analytics"]


def upgrade() -> None:
    # 创建 schema
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    # === exchange_data schema ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.klines (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_time TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, exchange, timeframe, open_time)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.tickers (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            last_price REAL, mid_price REAL, spread_bps REAL,
            high_24h REAL, low_24h REAL, vwap_24h REAL,
            volume_24h REAL, quote_volume_24h REAL, change_24h REAL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.latest_tickers (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            last_price REAL, mid_price REAL, spread_bps REAL,
            high_24h REAL, low_24h REAL, vwap_24h REAL,
            volume_24h REAL, quote_volume_24h REAL, change_24h REAL,
            timestamp TEXT,
            PRIMARY KEY (symbol, exchange)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.funding_rates (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            funding_rate REAL,
            mark_price REAL,
            index_price REAL,
            timestamp TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.latest_funding_rates (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            funding_rate REAL,
            mark_price REAL,
            index_price REAL,
            timestamp TEXT,
            PRIMARY KEY (symbol, exchange)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.orderbook_snapshots (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            mid_price REAL, spread_bps REAL,
            bid_depth_notional REAL, ask_depth_notional REAL,
            depth_imbalance REAL, timestamp TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS exchange_data.latest_orderbook_snapshots (
            symbol TEXT NOT NULL,
            exchange TEXT NOT NULL,
            mid_price REAL, spread_bps REAL,
            bid_depth_notional REAL, ask_depth_notional REAL,
            depth_imbalance REAL, timestamp TEXT,
            PRIMARY KEY (symbol, exchange)
        )
    """)

    # === market_data schema ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_data.stablecoin_mint_burns (
            id SERIAL PRIMARY KEY,
            stablecoin TEXT, chain TEXT, action TEXT,
            amount REAL, tx_hash TEXT, timestamp TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_data.defi_liquidations (
            id SERIAL PRIMARY KEY,
            protocol TEXT, collateral_asset TEXT, debt_asset TEXT,
            liquidation_amount_usd REAL, health_factor REAL,
            timestamp TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_data.whale_portfolios (
            address TEXT PRIMARY KEY,
            total_value_usd REAL, pnl_24h REAL,
            updated_at TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_data.whale_pnl_history (
            id SERIAL PRIMARY KEY,
            address TEXT NOT NULL,
            total_value_usd REAL, pnl REAL,
            timestamp TEXT NOT NULL
        )
    """)

    # === analytics schema ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS analytics.technical_indicators (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_time TEXT NOT NULL,
            close REAL, rsi_14 REAL, macd REAL, macd_signal REAL,
            bb_upper REAL, bb_lower REAL, atr_14 REAL,
            PRIMARY KEY (symbol, timeframe, open_time)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS analytics.merged_klines (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            open_time TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            exchange_count INTEGER, source_exchanges TEXT,
            PRIMARY KEY (symbol, timeframe, open_time)
        )
    """)

    # Indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_klines_sym_tf_time ON exchange_data.klines(symbol, timeframe, open_time)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_funding_sym_ts ON exchange_data.funding_rates(symbol, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tickers_sym_ts ON exchange_data.tickers(symbol, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_defi_liq_ts ON market_data.defi_liquidations(timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_whale_hist_addr ON market_data.whale_pnl_history(address, timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tech_ind_sym_tf ON analytics.technical_indicators(symbol, timeframe, open_time)")


def downgrade() -> None:
    # Drop tables in reverse order
    op.execute("DROP TABLE IF EXISTS analytics.merged_klines")
    op.execute("DROP TABLE IF EXISTS analytics.technical_indicators")
    op.execute("DROP TABLE IF EXISTS market_data.whale_pnl_history")
    op.execute("DROP TABLE IF EXISTS market_data.whale_portfolios")
    op.execute("DROP TABLE IF EXISTS market_data.defi_liquidations")
    op.execute("DROP TABLE IF EXISTS market_data.stablecoin_mint_burns")
    op.execute("DROP TABLE IF EXISTS exchange_data.latest_orderbook_snapshots")
    op.execute("DROP TABLE IF EXISTS exchange_data.orderbook_snapshots")
    op.execute("DROP TABLE IF EXISTS exchange_data.latest_funding_rates")
    op.execute("DROP TABLE IF EXISTS exchange_data.funding_rates")
    op.execute("DROP TABLE IF EXISTS exchange_data.latest_tickers")
    op.execute("DROP TABLE IF EXISTS exchange_data.tickers")
    op.execute("DROP TABLE IF EXISTS exchange_data.klines")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
