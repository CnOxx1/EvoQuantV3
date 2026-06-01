"""叙事状态机数据库读写。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager


class NarrativeRegimeRepository:
    """叙事状态机结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建叙事状态机所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS market_narratives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                narrative_id TEXT NOT NULL,
                narrative_name TEXT NOT NULL,
                lifecycle_phase TEXT NOT NULL,
                attention_score REAL,
                capital_flow_correlation REAL,
                related_tokens TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, narrative_id)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS narrative_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                narrative_id TEXT NOT NULL,
                from_phase TEXT NOT NULL,
                to_phase TEXT NOT NULL,
                trigger_event TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 叙事保存与加载
    # ------------------------------------------------------------------

    def save_narratives(self, entries: list[dict]):
        """批量保存市场叙事快照。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO market_narratives
                   (ts, narrative_id, narrative_name, lifecycle_phase,
                    attention_score, capital_flow_correlation, related_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["narrative_id"], e["narrative_name"],
                    e["lifecycle_phase"], e.get("attention_score"),
                    e.get("capital_flow_correlation"),
                    e.get("related_tokens", "[]"),
                ),
            )
        self.db.conn.commit()

    def save_transitions(self, entries: list[dict]):
        """批量保存叙事阶段转换记录。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO narrative_transitions
                   (ts, narrative_id, from_phase, to_phase, trigger_event)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["narrative_id"],
                    e["from_phase"], e["to_phase"],
                    e.get("trigger_event"),
                ),
            )
        self.db.conn.commit()

    def load_active_narratives(self) -> list[dict]:
        """加载当前活跃叙事（最新快照中 lifecycle_phase != decaying）。"""
        rows = self.db.fetch_all(
            """SELECT * FROM market_narratives
               WHERE lifecycle_phase != 'decaying'
               ORDER BY attention_score DESC""",
            (),
        )
        return [dict(row) for row in rows] if rows else []

    def load_recent_transitions(self, limit: int = 20) -> list[dict]:
        """加载最近的叙事阶段转换记录。"""
        rows = self.db.fetch_all(
            """SELECT * FROM narrative_transitions
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in rows] if rows else []
