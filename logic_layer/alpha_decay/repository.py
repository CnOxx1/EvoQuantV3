"""信号衰减与拥挤度数据库读写。"""

from __future__ import annotations

from database.db_manager import DBManager


class AlphaDecayRepository:
    """信号衰减与拥挤度分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建信号衰减与拥挤度所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_decay (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                signal_name TEXT NOT NULL,
                module_source TEXT,
                half_life_hours REAL,
                autocorrelation REAL,
                current_strength REAL,
                decay_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, signal_name)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS crowding_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                crowding_score REAL,
                agreeing_signals INTEGER,
                disagreeing_signals INTEGER,
                contrarian_signal TEXT,
                signal_surprise_index REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 信号衰减
    # ------------------------------------------------------------------

    def save_signal_decay(self, entries: list[dict]):
        """批量保存信号衰减分析结果。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO signal_decay
                   (ts, signal_name, module_source, half_life_hours,
                    autocorrelation, current_strength, decay_rate)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["signal_name"], e.get("module_source"),
                    e.get("half_life_hours"), e.get("autocorrelation"),
                    e.get("current_strength"), e.get("decay_rate"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 拥挤度指标
    # ------------------------------------------------------------------

    def save_crowding_index(self, entry: dict):
        """保存拥挤度指标。"""
        self.db.conn.execute(
            """INSERT INTO crowding_index
               (ts, crowding_score, agreeing_signals, disagreeing_signals,
                contrarian_signal, signal_surprise_index)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry["ts"], entry.get("crowding_score"),
                entry.get("agreeing_signals"), entry.get("disagreeing_signals"),
                entry.get("contrarian_signal"), entry.get("signal_surprise_index"),
            ),
        )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def load_latest_decay(self) -> list[dict]:
        """加载最新一批信号衰减记录。"""
        rows = self.db.fetch_all(
            """SELECT * FROM signal_decay
               WHERE ts = (SELECT MAX(ts) FROM signal_decay)
               ORDER BY signal_name""",
            (),
        )
        return [dict(row) for row in rows] if rows else []

    def load_latest_crowding(self) -> dict | None:
        """加载最新拥挤度指标。"""
        row = self.db.fetch_one(
            """SELECT * FROM crowding_index
               ORDER BY ts DESC LIMIT 1""",
            (),
        )
        if not row:
            return None
        return dict(row)
