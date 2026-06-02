"""持有者行为分析数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class HolderBehaviorRepository:
    """持有者行为状态的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建持有者行为分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS holder_behavior_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                sth_lth_ratio REAL,
                mvrv_percentile REAL,
                sopr_state TEXT,
                supply_shock_prob REAL,
                market_phase TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 状态写入
    # ------------------------------------------------------------------

    def save_state(self, state: dict):
        """保存持有者行为状态。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO holder_behavior_states
               (ts, sth_lth_ratio, mvrv_percentile, sopr_state,
                supply_shock_prob, market_phase)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                state["ts"],
                state.get("sth_lth_ratio"),
                state.get("mvrv_percentile"),
                state.get("sopr_state"),
                state.get("supply_shock_prob"),
                state.get("market_phase"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 状态读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新一条持有者行为状态。"""
        rows = self.db.fetch_all(
            """SELECT ts, sth_lth_ratio, mvrv_percentile, sopr_state,
                      supply_shock_prob, market_phase
               FROM holder_behavior_states
               ORDER BY ts DESC
               LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
