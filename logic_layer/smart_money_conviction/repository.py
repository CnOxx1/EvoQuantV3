"""Smart Money 信念指数数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class SmartMoneyConvictionRepository:
    """Smart Money 信念指数分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建 Smart Money 信念指数分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_money_conviction_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                conviction_index REAL,
                direction TEXT,
                pnl_trend TEXT,
                position_change TEXT,
                retail_divergence REAL,
                whale_count_bullish INTEGER,
                whale_count_bearish INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存 Smart Money 信念指数状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO smart_money_conviction_states
               (ts, conviction_index, direction, pnl_trend,
                position_change, retail_divergence,
                whale_count_bullish, whale_count_bearish)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("conviction_index"),
                entry.get("direction"),
                entry.get("pnl_trend"),
                entry.get("position_change"),
                entry.get("retail_divergence"),
                entry.get("whale_count_bullish"),
                entry.get("whale_count_bearish"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新 Smart Money 信念指数状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, conviction_index, direction, pnl_trend,
                      position_change, retail_divergence,
                      whale_count_bullish, whale_count_bearish
               FROM smart_money_conviction_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
