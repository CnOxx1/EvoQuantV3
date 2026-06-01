"""清算级联预测数据库读写。"""

from __future__ import annotations

from database.db_manager import DBManager


class LiquidationCascadeRepository:
    """清算级联分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建清算级联分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price_level REAL,
                total_size_usd REAL,
                leverage_avg REAL,
                distance_pct REAL,
                direction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, price_level)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cascade_risk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                cascade_probability REAL,
                estimated_liquidation_usd REAL,
                price_trigger REAL,
                direction TEXT,
                severity TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, direction)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidation_heatmap (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price_from REAL,
                price_to REAL,
                long_liq_usd REAL,
                short_liq_usd REAL,
                net_pressure REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ts, symbol, price_from)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 清算聚集区
    # ------------------------------------------------------------------

    def save_clusters(self, entries: list[dict]):
        """批量保存清算聚集区数据。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO liquidation_clusters
                   (ts, symbol, price_level, total_size_usd,
                    leverage_avg, distance_pct, direction)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("price_level"), e.get("total_size_usd"),
                    e.get("leverage_avg"), e.get("distance_pct"),
                    e.get("direction"),
                ),
            )
        self.db.conn.commit()

    def load_latest_clusters(self, symbol: str | None = None) -> list[dict]:
        """加载最新一批清算聚集区数据。"""
        if symbol:
            rows = self.db.fetch_all(
                """SELECT ts, symbol, price_level, total_size_usd,
                          leverage_avg, distance_pct, direction
                   FROM liquidation_clusters
                   WHERE ts = (SELECT MAX(ts) FROM liquidation_clusters
                               WHERE symbol = ?)
                     AND symbol = ?
                   ORDER BY distance_pct""",
                (symbol, symbol),
            )
        else:
            rows = self.db.fetch_all(
                """SELECT ts, symbol, price_level, total_size_usd,
                          leverage_avg, distance_pct, direction
                   FROM liquidation_clusters
                   WHERE ts = (SELECT MAX(ts) FROM liquidation_clusters)
                   ORDER BY distance_pct""",
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
                """INSERT OR REPLACE INTO cascade_risk
                   (ts, symbol, cascade_probability,
                    estimated_liquidation_usd, price_trigger,
                    direction, severity)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("cascade_probability"),
                    e.get("estimated_liquidation_usd"),
                    e.get("price_trigger"), e.get("direction"),
                    e.get("severity"),
                ),
            )
        self.db.conn.commit()

    def load_latest_cascade_risk(self) -> list[dict]:
        """加载最新一批级联风险评估。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, cascade_probability,
                      estimated_liquidation_usd, price_trigger,
                      direction, severity
               FROM cascade_risk
               WHERE ts = (SELECT MAX(ts) FROM cascade_risk)
               ORDER BY cascade_probability DESC""",
            (),
        )
        return [dict(r) for r in rows] if rows else []

    # ------------------------------------------------------------------
    # 清算热力图
    # ------------------------------------------------------------------

    def save_heatmap(self, entries: list[dict]):
        """批量保存清算热力图数据。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT OR REPLACE INTO liquidation_heatmap
                   (ts, symbol, price_from, price_to,
                    long_liq_usd, short_liq_usd, net_pressure)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"],
                    e.get("price_from"), e.get("price_to"),
                    e.get("long_liq_usd"), e.get("short_liq_usd"),
                    e.get("net_pressure"),
                ),
            )
        self.db.conn.commit()

    def load_latest_heatmap(self, symbol: str) -> list[dict]:
        """加载指定标的最新清算热力图。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, price_from, price_to,
                      long_liq_usd, short_liq_usd, net_pressure
               FROM liquidation_heatmap
               WHERE ts = (SELECT MAX(ts) FROM liquidation_heatmap
                           WHERE symbol = ?)
                 AND symbol = ?
               ORDER BY price_from""",
            (symbol, symbol),
        )
        return [dict(r) for r in rows] if rows else []
