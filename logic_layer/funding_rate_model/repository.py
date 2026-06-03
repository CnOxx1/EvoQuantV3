"""funding_rate_model 数据访问层。"""

from database.db_manager import DBManager


class FundingRateModelRepository:
    """资金费率模型数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_model_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                current_rate REAL DEFAULT 0,
                predicted_next REAL DEFAULT 0,
                rate_zscore REAL DEFAULT 0,
                rate_percentile REAL DEFAULT 50,
                cumulative_7d REAL DEFAULT 0,
                direction_bias TEXT DEFAULT 'neutral',
                mean_reversion_signal REAL DEFAULT 0,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_basis_model (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                spot_price REAL DEFAULT 0,
                futures_price REAL DEFAULT 0,
                basis_pct REAL DEFAULT 0,
                basis_zscore REAL DEFAULT 0,
                annualized_basis REAL DEFAULT 0,
                basis_regime TEXT DEFAULT 'flat',
                mean_reversion_signal REAL DEFAULT 0,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_funding_model_snap_entity
            ON funding_model_snapshots(entity_key, as_of DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_funding_basis_model_entity
            ON funding_basis_model(entity_key, as_of DESC)
        """)
        self.db.conn.commit()

    def save_funding_snapshot(self, entity_key: str, data: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO funding_model_snapshots
            (entity_key, current_rate, predicted_next, rate_zscore, rate_percentile,
             cumulative_7d, direction_bias, mean_reversion_signal, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, data["current_rate"], data["predicted_next"],
              data["rate_zscore"], data["rate_percentile"], data["cumulative_7d"],
              data["direction_bias"], data["mean_reversion_signal"], as_of))
        self.db.conn.commit()

    def save_basis_snapshot(self, entity_key: str, data: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO funding_basis_model
            (entity_key, spot_price, futures_price, basis_pct, basis_zscore,
             annualized_basis, basis_regime, mean_reversion_signal, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, data["spot_price"], data["futures_price"],
              data["basis_pct"], data["basis_zscore"], data["annualized_basis"],
              data["basis_regime"], data["mean_reversion_signal"], as_of))
        self.db.conn.commit()

    def fetch_latest_funding(self, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, current_rate, predicted_next, rate_zscore,
                   rate_percentile, cumulative_7d, direction_bias,
                   mean_reversion_signal, as_of
            FROM funding_model_snapshots
            WHERE as_of = (SELECT MAX(as_of) FROM funding_model_snapshots fs WHERE fs.entity_key = funding_model_snapshots.entity_key)
            ORDER BY abs(current_rate) DESC LIMIT ?
        """, (limit,))
        cols = ["entity_key", "current_rate", "predicted_next", "rate_zscore",
                "rate_percentile", "cumulative_7d", "direction_bias",
                "mean_reversion_signal", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_latest_basis(self, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, spot_price, futures_price, basis_pct,
                   basis_zscore, annualized_basis, basis_regime,
                   mean_reversion_signal, as_of
            FROM funding_basis_model
            WHERE as_of = (SELECT MAX(as_of) FROM funding_basis_model bs WHERE bs.entity_key = funding_basis_model.entity_key)
            ORDER BY abs(basis_pct) DESC LIMIT ?
        """, (limit,))
        cols = ["entity_key", "spot_price", "futures_price", "basis_pct",
                "basis_zscore", "annualized_basis", "basis_regime",
                "mean_reversion_signal", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
