"""市场情绪复合指标数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class MarketSentimentCompositeRepository:
    """复合情绪状态的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建复合情绪状态所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS composite_sentiment_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                composite_score REAL,
                extreme_label TEXT,
                divergence_type TEXT,
                divergence_strength REAL,
                reversal_probability REAL,
                funding_consistency TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 状态落库
    # ------------------------------------------------------------------

    def save_state(self, state: dict):
        """保存复合情绪状态。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO composite_sentiment_states
               (ts, composite_score, extreme_label, divergence_type,
                divergence_strength, reversal_probability,
                funding_consistency)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                state["ts"],
                state.get("composite_score"),
                state.get("extreme_label"),
                state.get("divergence_type"),
                state.get("divergence_strength"),
                state.get("reversal_probability"),
                state.get("funding_consistency"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 状态读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新一条复合情绪状态。"""
        rows = self.db.fetch_all(
            """SELECT ts, composite_score, extreme_label,
                      divergence_type, divergence_strength,
                      reversal_probability, funding_consistency
               FROM composite_sentiment_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
