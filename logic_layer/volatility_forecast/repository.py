"""volatility_forecast 数据访问层。"""

from database.db_manager import DBManager


class VolatilityForecastRepository:
    """波动率预测数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS volatility_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                realized_vol_1d REAL DEFAULT 0,
                realized_vol_7d REAL DEFAULT 0,
                realized_vol_30d REAL DEFAULT 0,
                implied_vol REAL DEFAULT 0,
                rv_iv_spread REAL DEFAULT 0,
                vol_regime TEXT DEFAULT 'normal',
                forecast_1d REAL DEFAULT 0,
                forecast_7d REAL DEFAULT 0,
                vol_percentile REAL DEFAULT 50,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS volatility_cone (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                window_days INTEGER NOT NULL,
                current_val REAL DEFAULT 0,
                percentile_25 REAL DEFAULT 0,
                percentile_50 REAL DEFAULT 0,
                percentile_75 REAL DEFAULT 0,
                min_val REAL DEFAULT 0,
                max_val REAL DEFAULT 0,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, window_days, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vol_snap_entity
            ON volatility_snapshots(entity_key, as_of DESC)
        """)
        self.db.conn.commit()

    def save_snapshot(self, entity_key: str, data: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO volatility_snapshots
            (entity_key, realized_vol_1d, realized_vol_7d, realized_vol_30d,
             implied_vol, rv_iv_spread, vol_regime, forecast_1d, forecast_7d,
             vol_percentile, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, data["realized_vol_1d"], data["realized_vol_7d"],
              data["realized_vol_30d"], data["implied_vol"], data["rv_iv_spread"],
              data["vol_regime"], data["forecast_1d"], data["forecast_7d"],
              data["vol_percentile"], as_of))
        self.db.conn.commit()

    def save_cone(self, entity_key: str, cone: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO volatility_cone
            (entity_key, window_days, current_val, percentile_25, percentile_50,
             percentile_75, min_val, max_val, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, cone["window_days"], cone["current"],
              cone["percentile_25"], cone["percentile_50"], cone["percentile_75"],
              cone["min_val"], cone["max_val"], as_of))
        self.db.conn.commit()

    def fetch_latest_snapshots(self, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, realized_vol_1d, realized_vol_7d, realized_vol_30d,
                   implied_vol, rv_iv_spread, vol_regime, forecast_1d, forecast_7d,
                   vol_percentile, as_of
            FROM volatility_snapshots
            WHERE as_of = (SELECT MAX(as_of) FROM volatility_snapshots vs WHERE vs.entity_key = volatility_snapshots.entity_key)
            ORDER BY entity_key LIMIT ?
        """, (limit,))
        cols = ["entity_key", "realized_vol_1d", "realized_vol_7d", "realized_vol_30d",
                "implied_vol", "rv_iv_spread", "vol_regime", "forecast_1d", "forecast_7d",
                "vol_percentile", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_cone_data(self, entity_key: str) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT window_days, current_val, percentile_25, percentile_50,
                   percentile_75, min_val, max_val
            FROM volatility_cone
            WHERE entity_key = ? AND as_of = (SELECT MAX(as_of) FROM volatility_cone vc WHERE vc.entity_key = ?)
            ORDER BY window_days
        """, (entity_key, entity_key))
        cols = ["window_days", "current", "percentile_25", "percentile_50",
                "percentile_75", "min_val", "max_val"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
