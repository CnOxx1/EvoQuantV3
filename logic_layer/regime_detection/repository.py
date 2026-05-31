"""regime_detection 数据访问层。"""

from database.db_manager import DBManager


class RegimeDetectionRepository:
    """状态识别数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建所需表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS regime_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                regime TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                duration_hours INTEGER DEFAULT 0,
                volatility_regime TEXT DEFAULT 'normal',
                correlation_regime TEXT DEFAULT 'moderate_corr',
                momentum_regime TEXT DEFAULT 'neutral',
                as_of TEXT NOT NULL,
                UNIQUE(entity_key, as_of)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS regime_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                from_regime TEXT NOT NULL,
                to_regime TEXT NOT NULL,
                transition_time TEXT NOT NULL,
                trigger_factors TEXT DEFAULT '',
                transition_speed TEXT DEFAULT 'gradual'
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_regime_states_entity
            ON regime_states(entity_key, as_of DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_regime_transitions_entity
            ON regime_transitions(entity_key, transition_time DESC)
        """)
        self.db.conn.commit()

    def fetch_latest_regime(self, entity_key: str) -> dict | None:
        """获取某标的最新状态。"""
        cursor = self.db.conn.execute("""
            SELECT regime, confidence, duration_hours, volatility_regime,
                   correlation_regime, momentum_regime, as_of
            FROM regime_states WHERE entity_key = ?
            ORDER BY as_of DESC LIMIT 1
        """, (entity_key,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "regime": row[0], "confidence": row[1], "duration_hours": row[2],
            "volatility_regime": row[3], "correlation_regime": row[4],
            "momentum_regime": row[5], "as_of": row[6],
        }

    def fetch_regime_history(self, entity_key: str, limit: int = 100) -> list[str]:
        """获取状态历史序列。"""
        cursor = self.db.conn.execute("""
            SELECT regime FROM regime_states WHERE entity_key = ?
            ORDER BY as_of ASC LIMIT ?
        """, (entity_key, limit))
        return [row[0] for row in cursor.fetchall()]

    def save_regime_state(self, entity_key: str, regime: str, confidence: float,
                          duration_hours: int, vol_regime: str, corr_regime: str,
                          momentum_regime: str, as_of: str):
        """保存状态分类结果。"""
        self.db.conn.execute("""
            INSERT OR REPLACE INTO regime_states
            (entity_key, regime, confidence, duration_hours,
             volatility_regime, correlation_regime, momentum_regime, as_of)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (entity_key, regime, confidence, duration_hours,
              vol_regime, corr_regime, momentum_regime, as_of))
        self.db.conn.commit()

    def save_transition(self, entity_key: str, from_regime: str, to_regime: str,
                        transition_time: str, triggers: str, speed: str):
        """保存状态转换记录。"""
        self.db.conn.execute("""
            INSERT INTO regime_transitions
            (entity_key, from_regime, to_regime, transition_time,
             trigger_factors, transition_speed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (entity_key, from_regime, to_regime, transition_time, triggers, speed))
        self.db.conn.commit()

    def fetch_recent_transitions(self, entity_key: str, limit: int = 10) -> list[dict]:
        """获取近期状态转换。"""
        cursor = self.db.conn.execute("""
            SELECT from_regime, to_regime, transition_time, trigger_factors, transition_speed
            FROM regime_transitions WHERE entity_key = ?
            ORDER BY transition_time DESC LIMIT ?
        """, (entity_key, limit))
        cols = ["from_regime", "to_regime", "transition_time", "trigger_factors", "transition_speed"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_all_latest_regimes(self, limit: int = 50) -> list[dict]:
        """获取所有标的的最新状态。"""
        cursor = self.db.conn.execute("""
            SELECT entity_key, regime, confidence, duration_hours,
                   volatility_regime, correlation_regime, momentum_regime, as_of
            FROM regime_states
            WHERE as_of = (SELECT MAX(as_of) FROM regime_states rs WHERE rs.entity_key = regime_states.entity_key)
            ORDER BY entity_key
            LIMIT ?
        """, (limit,))
        cols = ["entity_key", "regime", "confidence", "duration_hours",
                "volatility_regime", "correlation_regime", "momentum_regime", "as_of"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
