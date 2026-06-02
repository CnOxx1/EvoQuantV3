"""散户 FOMO/FUD 复合指数数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class RetailFomoIndexRepository:
    """散户 FOMO/FUD 复合指数分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建散户 FOMO/FUD 复合指数分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS retail_fomo_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                fomo_index REAL,
                fud_index REAL,
                contrarian_signal_strength REAL,
                reversal_probability REAL,
                search_momentum REAL,
                social_volume_zscore REAL,
                listing_heat REAL,
                fear_greed_extreme INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存散户 FOMO/FUD 复合指数状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO retail_fomo_states
               (ts, fomo_index, fud_index, contrarian_signal_strength,
                reversal_probability, search_momentum,
                social_volume_zscore, listing_heat, fear_greed_extreme)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("fomo_index"),
                entry.get("fud_index"),
                entry.get("contrarian_signal_strength"),
                entry.get("reversal_probability"),
                entry.get("search_momentum"),
                entry.get("social_volume_zscore"),
                entry.get("listing_heat"),
                1 if entry.get("fear_greed_extreme") else 0,
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新散户 FOMO/FUD 复合指数状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, fomo_index, fud_index, contrarian_signal_strength,
                      reversal_probability, search_momentum,
                      social_volume_zscore, listing_heat, fear_greed_extreme
               FROM retail_fomo_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
