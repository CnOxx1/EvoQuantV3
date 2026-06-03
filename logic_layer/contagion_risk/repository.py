"""传染风险数据库读写。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db_manager import DBManager


class ContagionRiskRepository:
    """传染风险分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建传染风险分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS contagion_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                covar_95 REAL,
                conditional_correlation REAL,
                tail_beta REAL,
                systemic_contribution REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS contagion_cascade_risk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                risk_type TEXT NOT NULL,
                risk_level REAL,
                affected_assets TEXT,
                trigger_conditions TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, risk_type)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 传染指标
    # ------------------------------------------------------------------

    def save_contagion_metrics(self, entries: list[dict]):
        """批量保存传染风险指标。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO contagion_metrics
                   (ts, symbol, covar_95, conditional_correlation,
                    tail_beta, systemic_contribution)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("covar_95"), e.get("conditional_correlation"),
                    e.get("tail_beta"), e.get("systemic_contribution"),
                ),
            )
        self.db.conn.commit()

    def load_latest_metrics(self) -> list[dict]:
        """加载最新一批传染风险指标。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, covar_95, conditional_correlation,
                      tail_beta, systemic_contribution
               FROM contagion_metrics
               WHERE ts = (SELECT MAX(ts) FROM contagion_metrics)
               ORDER BY symbol""",
            (),
        )
        return [dict(r) for r in rows] if rows else []

    # ------------------------------------------------------------------
    # 级联风险
    # ------------------------------------------------------------------

    def save_cascade_risk(self, entries: list[dict]):
        """批量保存级联风险评估。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO contagion_cascade_risk
                   (ts, risk_type, risk_level, affected_assets,
                    trigger_conditions)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["risk_type"],
                    e.get("risk_level"), e.get("affected_assets"),
                    e.get("trigger_conditions"),
                ),
            )
        self.db.conn.commit()

    def load_latest_cascade_risk(self) -> list[dict]:
        """加载最新一批级联风险评估。"""
        rows = self.db.fetch_all(
            """SELECT ts, risk_type, risk_level, affected_assets,
                      trigger_conditions
               FROM contagion_cascade_risk
               WHERE ts = (SELECT MAX(ts) FROM contagion_cascade_risk)
               ORDER BY risk_type""",
            (),
        )
        return [dict(r) for r in rows] if rows else []
