"""组合风险数据库读写。"""

from __future__ import annotations

import json

from database.db_manager import DBManager


class PortfolioRiskRepository:
    """组合风险快照的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建组合风险所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_risk_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                portfolio_name TEXT NOT NULL DEFAULT 'default',
                asset_count INTEGER NOT NULL,
                weights_json TEXT NOT NULL,
                annualized_volatility REAL,
                daily_var_95 REAL,
                daily_var_99 REAL,
                hhi REAL,
                effective_n REAL,
                max_weight REAL,
                diversification_ratio REAL,
                risk_contributions_json TEXT,
                sector_concentration_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    def save_snapshot(self, snapshot: dict):
        self.db.conn.execute(
            """INSERT INTO portfolio_risk_snapshots
               (snapshot_time, portfolio_name, asset_count, weights_json,
                annualized_volatility, daily_var_95, daily_var_99,
                hhi, effective_n, max_weight, diversification_ratio,
                risk_contributions_json, sector_concentration_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot["snapshot_time"],
                snapshot.get("portfolio_name", "default"),
                snapshot["asset_count"],
                json.dumps(snapshot["weights"]),
                snapshot.get("annualized_volatility"),
                snapshot.get("daily_var_95"),
                snapshot.get("daily_var_99"),
                snapshot.get("hhi"),
                snapshot.get("effective_n"),
                snapshot.get("max_weight"),
                snapshot.get("diversification_ratio"),
                json.dumps(snapshot.get("risk_contributions", {})),
                json.dumps(snapshot.get("sector_concentration", {})),
            ),
        )
        self.db.conn.commit()

    def load_latest_snapshot(self, portfolio_name: str = "default") -> dict | None:
        row = self.db.fetch_one(
            """SELECT * FROM portfolio_risk_snapshots
               WHERE portfolio_name = ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (portfolio_name,),
        )
        if not row:
            return None
        return {
            "snapshot_time": row["snapshot_time"],
            "portfolio_name": row["portfolio_name"],
            "asset_count": row["asset_count"],
            "weights": json.loads(row["weights_json"]),
            "annualized_volatility": row["annualized_volatility"],
            "daily_var_95": row["daily_var_95"],
            "daily_var_99": row["daily_var_99"],
            "hhi": row["hhi"],
            "effective_n": row["effective_n"],
            "max_weight": row["max_weight"],
            "diversification_ratio": row["diversification_ratio"],
            "risk_contributions": json.loads(row["risk_contributions_json"] or "{}"),
            "sector_concentration": json.loads(row["sector_concentration_json"] or "{}"),
        }
