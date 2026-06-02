"""深度 regime 数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class DepthRegimeRepository:
    """深度 regime 分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建深度 regime 分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS depth_regime_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT,
                regime TEXT,
                bid_wall_strength REAL,
                ask_wall_strength REAL,
                slippage_10k REAL,
                slippage_100k REAL,
                slippage_1m REAL,
                depth_price_divergence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存深度 regime 状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO depth_regime_states
               (ts, symbol, regime, bid_wall_strength, ask_wall_strength,
                slippage_10k, slippage_100k, slippage_1m,
                depth_price_divergence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("symbol"),
                entry.get("regime"),
                entry.get("bid_wall_strength"),
                entry.get("ask_wall_strength"),
                entry.get("slippage_10k"),
                entry.get("slippage_100k"),
                entry.get("slippage_1m"),
                entry.get("depth_price_divergence"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新深度 regime 状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, regime, bid_wall_strength, ask_wall_strength,
                      slippage_10k, slippage_100k, slippage_1m,
                      depth_price_divergence
               FROM depth_regime_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
