"""DeFi 压力指数数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class DefiStressRepository:
    """DeFi 压力指数分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建 DeFi 压力指数分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS defi_stress_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                stress_index REAL,
                cascade_prob_5pct REAL,
                cascade_prob_10pct REAL,
                cascade_prob_20pct REAL,
                highest_risk_protocol TEXT,
                systemic_threshold_breached INTEGER,
                total_at_risk_usd REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存 DeFi 压力指数状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO defi_stress_states
               (ts, stress_index, cascade_prob_5pct, cascade_prob_10pct,
                cascade_prob_20pct, highest_risk_protocol,
                systemic_threshold_breached, total_at_risk_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("stress_index"),
                entry.get("cascade_prob_5pct"),
                entry.get("cascade_prob_10pct"),
                entry.get("cascade_prob_20pct"),
                entry.get("highest_risk_protocol"),
                1 if entry.get("systemic_threshold_breached") else 0,
                entry.get("total_at_risk_usd"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新 DeFi 压力指数状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, stress_index, cascade_prob_5pct, cascade_prob_10pct,
                      cascade_prob_20pct, highest_risk_protocol,
                      systemic_threshold_breached, total_at_risk_usd
               FROM defi_stress_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
