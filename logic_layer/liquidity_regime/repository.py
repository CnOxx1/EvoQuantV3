"""流动性状态数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class LiquidityRegimeRepository:
    """流动性状态分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建流动性状态分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidity_regime_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                liquidity_score REAL,
                regime TEXT,
                defi_cefi_spread REAL,
                stablecoin_pulse REAL,
                staking_flow_impact REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存流动性状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO liquidity_regime_states
               (ts, liquidity_score, regime, defi_cefi_spread,
                stablecoin_pulse, staking_flow_impact)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("liquidity_score"),
                entry.get("regime"),
                entry.get("defi_cefi_spread"),
                entry.get("stablecoin_pulse"),
                entry.get("staking_flow_impact"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新流动性状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, liquidity_score, regime, defi_cefi_spread,
                      stablecoin_pulse, staking_flow_impact
               FROM liquidity_regime_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
