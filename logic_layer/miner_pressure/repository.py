"""矿工压力数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class MinerPressureRepository:
    """矿工压力分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建矿工压力分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS miner_pressure_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                puell_percentile REAL,
                puell_zone TEXT,
                halving_days_until_next INTEGER,
                halving_cycle_pct REAL,
                capitulation_index REAL,
                hash_price_ratio REAL,
                pressure_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    def save_state(self, state: dict):
        """保存矿工压力状态。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO miner_pressure_states
               (ts, puell_percentile, puell_zone, halving_days_until_next,
                halving_cycle_pct, capitulation_index, hash_price_ratio,
                pressure_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                state["ts"],
                state.get("puell_percentile"),
                state.get("puell_zone"),
                state.get("halving_days_until_next"),
                state.get("halving_cycle_pct"),
                state.get("capitulation_index"),
                state.get("hash_price_ratio"),
                state.get("pressure_score"),
            ),
        )
        self.db.conn.commit()

    def load_latest_state(self) -> dict | None:
        """加载最新矿工压力状态。"""
        rows = self.db.fetch_all(
            """SELECT ts, puell_percentile, puell_zone,
                      halving_days_until_next, halving_cycle_pct,
                      capitulation_index, hash_price_ratio, pressure_score
               FROM miner_pressure_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
