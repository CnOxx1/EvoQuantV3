"""anomaly_detection 数据访问层。"""

from database.db_manager import DBManager


class AnomalyDetectionRepository:
    """异常检测数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建所需表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS anomaly_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                anomaly_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                score REAL NOT NULL,
                description TEXT,
                metric_name TEXT,
                metric_value REAL,
                threshold REAL,
                zscore REAL,
                detected_at TEXT NOT NULL
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_anomaly_entity_time
            ON anomaly_events(entity_key, detected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_anomaly_severity
            ON anomaly_events(severity, detected_at DESC)
        """)
        self.db.conn.commit()

    def save_anomaly(self, entity_key: str, anomaly: dict, detected_at: str):
        """保存异常事件。"""
        self.db.conn.execute("""
            INSERT INTO anomaly_events
            (entity_key, anomaly_type, severity, score, description,
             metric_name, metric_value, threshold, zscore, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entity_key, anomaly["type"], anomaly["severity"], anomaly["score"],
            anomaly["description"], anomaly["metric_name"],
            anomaly["metric_value"], anomaly["threshold"],
            anomaly["zscore"], detected_at,
        ))
        self.db.conn.commit()

    def fetch_recent_anomalies(self, entity_key: str = None, hours: int = 24, limit: int = 50) -> list[dict]:
        """获取近期异常事件。"""
        if entity_key:
            cursor = self.db.conn.execute("""
                SELECT entity_key, anomaly_type, severity, score, description,
                       metric_name, metric_value, zscore, detected_at
                FROM anomaly_events
                WHERE entity_key = ? AND detected_at >= datetime('now', ?)
                ORDER BY detected_at DESC LIMIT ?
            """, (entity_key, f"-{hours} hours", limit))
        else:
            cursor = self.db.conn.execute("""
                SELECT entity_key, anomaly_type, severity, score, description,
                       metric_name, metric_value, zscore, detected_at
                FROM anomaly_events
                WHERE detected_at >= datetime('now', ?)
                ORDER BY score DESC, detected_at DESC LIMIT ?
            """, (f"-{hours} hours", limit))

        cols = ["entity_key", "anomaly_type", "severity", "score", "description",
                "metric_name", "metric_value", "zscore", "detected_at"]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetch_anomaly_counts(self, hours: int = 24) -> dict:
        """获取异常计数统计。"""
        cursor = self.db.conn.execute("""
            SELECT entity_key, severity, COUNT(*) as cnt
            FROM anomaly_events
            WHERE detected_at >= datetime('now', ?)
            GROUP BY entity_key, severity
        """, (f"-{hours} hours",))

        result = {}
        for row in cursor.fetchall():
            entity = row[0]
            if entity not in result:
                result[entity] = {"critical": 0, "warning": 0, "info": 0}
            result[entity][row[1]] = row[2]
        return result
