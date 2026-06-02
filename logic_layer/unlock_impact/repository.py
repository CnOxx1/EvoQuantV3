"""代币解锁冲击数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class UnlockImpactRepository:
    """代币解锁冲击分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建代币解锁冲击分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS unlock_impact_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                token TEXT,
                unlock_amount_usd REAL,
                daily_volume REAL,
                sell_pressure_ratio REAL,
                liquidity_absorption REAL,
                impact_score REAL,
                expected_price_impact_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, token)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存代币解锁冲击状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO unlock_impact_states
               (ts, token, unlock_amount_usd, daily_volume,
                sell_pressure_ratio, liquidity_absorption,
                impact_score, expected_price_impact_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("token"),
                entry.get("unlock_amount_usd"),
                entry.get("daily_volume"),
                entry.get("sell_pressure_ratio"),
                entry.get("liquidity_absorption"),
                entry.get("impact_score"),
                entry.get("expected_price_impact_pct"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新代币解锁冲击状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, token, unlock_amount_usd, daily_volume,
                      sell_pressure_ratio, liquidity_absorption,
                      impact_score, expected_price_impact_pct
               FROM unlock_impact_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None

    def load_top_impacts(self, limit: int = 5) -> list[dict]:
        """加载冲击评分最高的代币记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, token, impact_score, expected_price_impact_pct,
                      sell_pressure_ratio, unlock_amount_usd
               FROM unlock_impact_states
               WHERE ts = (SELECT MAX(ts) FROM unlock_impact_states)
               ORDER BY impact_score DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]
