"""流量分解数据库读写。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager


class FlowDecompositionRepository:
    """流量分解结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建流量分解所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS flow_decomposition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                vpin REAL,
                informed_flow_ratio REAL,
                retail_flow_ratio REAL,
                smart_money_direction TEXT,
                accumulation_phase INTEGER,
                distribution_phase INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS vpin_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                vpin_value REAL,
                vpin_percentile REAL,
                alert_level TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    def save_decomposition(self, entries: list[dict]):
        """保存流量分解结果。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO flow_decomposition
                   (ts, symbol, vpin, informed_flow_ratio,
                    retail_flow_ratio, smart_money_direction,
                    accumulation_phase, distribution_phase)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("vpin"), e.get("informed_flow_ratio"),
                    e.get("retail_flow_ratio"),
                    e.get("smart_money_direction"),
                    e.get("accumulation_phase"),
                    e.get("distribution_phase"),
                ),
            )
        self.db.conn.commit()

    def save_vpin(self, entries: list[dict]):
        """保存 VPIN 历史记录。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO vpin_history
                   (ts, symbol, vpin_value, vpin_percentile, alert_level)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("vpin_value"), e.get("vpin_percentile"),
                    e.get("alert_level"),
                ),
            )
        self.db.conn.commit()

    def load_latest_decomposition(self, symbol: str) -> dict | None:
        """加载最新的流量分解结果。"""
        row = self.db.fetch_one(
            """SELECT * FROM flow_decomposition
               WHERE symbol = ?
               ORDER BY ts DESC LIMIT 1""",
            (symbol,),
        )
        if not row:
            return None
        return dict(row)

    def load_vpin_history(self, symbol: str, limit: int = 50) -> list[dict]:
        """加载 VPIN 历史记录。"""
        rows = self.db.fetch_all(
            """SELECT * FROM vpin_history
               WHERE symbol = ?
               ORDER BY ts DESC LIMIT ?""",
            (symbol, limit),
        )
        return [dict(r) for r in rows]
