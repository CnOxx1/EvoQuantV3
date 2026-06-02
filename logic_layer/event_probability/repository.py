"""事件概率数据库读写。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager


class EventProbabilityRepository:
    """事件概率分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建事件概率分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS event_probability_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                market_id TEXT NOT NULL,
                question TEXT,
                probability REAL,
                prob_change_24h REAL,
                impact_score REAL,
                affected_assets TEXT,
                sentiment_validation TEXT,
                is_jump INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, market_id)
            )
        """)
        self.db.conn.commit()

    def save_states(self, entries: list[dict]):
        """批量保存事件概率状态。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO event_probability_states
                   (ts, market_id, question, probability, prob_change_24h,
                    impact_score, affected_assets, sentiment_validation,
                    is_jump)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["market_id"], e.get("question"),
                    e.get("probability"), e.get("prob_change_24h"),
                    e.get("impact_score"), e.get("affected_assets"),
                    e.get("sentiment_validation"), e.get("is_jump"),
                ),
            )
        self.db.conn.commit()

    def load_latest_states(self) -> list[dict]:
        """加载最新一批事件概率状态。"""
        rows = self.db.fetch_all(
            """SELECT ts, market_id, question, probability,
                      prob_change_24h, impact_score, affected_assets,
                      sentiment_validation, is_jump
               FROM event_probability_states
               WHERE ts = (SELECT MAX(ts) FROM event_probability_states)
               ORDER BY impact_score DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []
