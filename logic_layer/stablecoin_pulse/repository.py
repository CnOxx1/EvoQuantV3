"""稳定币脉冲数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class StablecoinPulseRepository:
    """稳定币脉冲分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建稳定币脉冲分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS stablecoin_pulse_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                net_mint_pulse REAL,
                chain_migration_direction TEXT,
                expansion_signal TEXT,
                pulse_amplitude REAL,
                btc_correlation REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def save_state(self, entry: dict):
        """保存稳定币脉冲状态记录。"""
        self.db.conn.execute(
            """INSERT OR REPLACE INTO stablecoin_pulse_states
               (ts, net_mint_pulse, chain_migration_direction,
                expansion_signal, pulse_amplitude, btc_correlation)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"],
                entry.get("net_mint_pulse"),
                entry.get("chain_migration_direction"),
                entry.get("expansion_signal"),
                entry.get("pulse_amplitude"),
                entry.get("btc_correlation"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_latest_state(self) -> dict | None:
        """加载最新稳定币脉冲状态记录。"""
        rows = self.db.fetch_all(
            """SELECT ts, net_mint_pulse, chain_migration_direction,
                      expansion_signal, pulse_amplitude, btc_correlation
               FROM stablecoin_pulse_states
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if rows:
            return dict(rows[0])
        return None
