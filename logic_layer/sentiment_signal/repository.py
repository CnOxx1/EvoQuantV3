"""sentiment_signal 数据访问层。"""

from database.db_manager import DBManager


class SentimentSignalRepository:
    """情绪信号数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                strength REAL DEFAULT 0,
                sentiment_value REAL DEFAULT 0,
                sentiment_zscore REAL DEFAULT 0,
                price_correlation REAL DEFAULT 0,
                lead_lag_hours INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0,
                as_of TEXT NOT NULL
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS causality_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                direction TEXT NOT NULL,
                f_statistic REAL DEFAULT 0,
                p_value REAL DEFAULT 1,
                optimal_lag INTEGER DEFAULT 0,
                is_significant INTEGER DEFAULT 0,
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_signals_entity
            ON sentiment_signals(entity_key, as_of DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_causality_entity
            ON causality_results(entity_key, as_of DESC)
        """)
        self.db.conn.commit()

    def save_signal(self, entity_key: str, signal: dict, as_of: str):
        self.db.conn.execute("""
            INSERT INTO sentiment_signals
            (entity_key, signal_type, direction, strength, sentiment_value,
             sentiment_zscore, price_correlation, lead_lag_hours, confidence, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, signal["signal_type"], signal["direction"],
              signal["strength"], signal["sentiment_value"],
              signal.get("sentiment_zscore", 0), signal.get("price_correlation", 0),
              signal.get("lead_lag_hours", 0), signal.get("confidence", 0.5), as_of))
        self.db.conn.commit()

    def save_causality(self, entity_key: str, result: dict, as_of: str):
        self.db.conn.execute("""
            INSERT OR REPLACE INTO causality_results
            (entity_key, direction, f_statistic, p_value, optimal_lag, is_significant, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, result["direction"], result["f_statistic"],
              result["p_value"], result["optimal_lag"],
              int(result["is_significant"]), as_of))
        self.db.conn.commit()

    def fetch_recent_signals(self, hours: int = 24, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, signal_type, direction, strength,
                   sentiment_value, sentiment_zscore, confidence, as_of
            FROM sentiment_signals
            WHERE as_of >= datetime('now', ?)
            ORDER BY strength DESC, as_of DESC LIMIT ?
        """, (f"-{hours} hours", limit))
        cols = ["entity_key", "signal_type", "direction", "strength",
                "sentiment_value", "sentiment_zscore", "confidence", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_latest_causality(self, limit: int = 50) -> list[dict]:
        cursor = self.db.conn.execute("""
            SELECT entity_key, direction, f_statistic, p_value, optimal_lag, is_significant, as_of
            FROM causality_results
            WHERE as_of = (SELECT MAX(as_of) FROM causality_results cr WHERE cr.entity_key = causality_results.entity_key)
            ORDER BY f_statistic DESC LIMIT ?
        """, (limit,))
        cols = ["entity_key", "direction", "f_statistic", "p_value",
                "optimal_lag", "is_significant", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
