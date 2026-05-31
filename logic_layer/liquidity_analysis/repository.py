"""liquidity_analysis 数据访问层。"""

from database.db_manager import DBManager


class LiquidityAnalysisRepository:
    """流动性分析数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidity_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                exchange TEXT NOT NULL,
                bid_depth_usd REAL DEFAULT 0,
                ask_depth_usd REAL DEFAULT 0,
                spread_bps REAL DEFAULT 0,
                slippage_10k_bps REAL DEFAULT 0,
                slippage_100k_bps REAL DEFAULT 0,
                slippage_1m_bps REAL DEFAULT 0,
                liquidity_score REAL DEFAULT 0,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, exchange, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS liquidity_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                current_value REAL,
                normal_value REAL,
                description TEXT,
                detected_at TEXT NOT NULL
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_liq_profile_entity
            ON liquidity_profiles(entity_key, as_of DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_liq_alerts_entity
            ON liquidity_alerts(entity_key, detected_at DESC)
        """)
        self.db.conn.commit()

    def save_profile(self, entity_key: str, exchange: str, profile: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO liquidity_profiles
            (entity_key, exchange, bid_depth_usd, ask_depth_usd, spread_bps,
             slippage_10k_bps, slippage_100k_bps, slippage_1m_bps, liquidity_score, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, exchange, profile["bid_depth_usd"], profile["ask_depth_usd"],
              profile["spread_bps"], profile["slippage_10k_bps"],
              profile["slippage_100k_bps"], profile["slippage_1m_bps"],
              profile["liquidity_score"], as_of))
        self.db.conn.commit()

    def save_alert(self, entity_key: str, alert: dict, detected_at: str):
        self.db.conn.execute("""
            INSERT INTO liquidity_alerts
            (entity_key, alert_type, severity, current_value, normal_value, description, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, alert["alert_type"], alert["severity"],
              alert["current_value"], alert["normal_value"],
              alert["description"], detected_at))
        self.db.conn.commit()

    def fetch_latest_profiles(self, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, exchange, bid_depth_usd, ask_depth_usd, spread_bps,
                   slippage_10k_bps, slippage_100k_bps, slippage_1m_bps, liquidity_score, as_of
            FROM liquidity_profiles
            WHERE as_of = (SELECT MAX(as_of) FROM liquidity_profiles lp WHERE lp.entity_key = liquidity_profiles.entity_key)
            ORDER BY liquidity_score DESC
            LIMIT ?
        """, (limit,))
        cols = ["entity_key", "exchange", "bid_depth_usd", "ask_depth_usd", "spread_bps",
                "slippage_10k_bps", "slippage_100k_bps", "slippage_1m_bps", "liquidity_score", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_recent_alerts(self, hours: int = 24, limit: int = 30) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, alert_type, severity, current_value, normal_value, description, detected_at
            FROM liquidity_alerts
            WHERE detected_at >= datetime('now', ?)
            ORDER BY detected_at DESC LIMIT ?
        """, (f"-{hours} hours", limit))
        cols = ["entity_key", "alert_type", "severity", "current_value", "normal_value", "description", "detected_at"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_historical_depth(self, entity_key: str) -> float:
        """获取历史平均深度（用于对比）。"""
        cursor = self.db.conn.execute("""
            SELECT AVG(bid_depth_usd + ask_depth_usd)
            FROM liquidity_profiles
            WHERE entity_key = ?
        """, (entity_key,))
        row = cursor.fetchone()
        return float(row[0]) if row and row[0] else 0.0
