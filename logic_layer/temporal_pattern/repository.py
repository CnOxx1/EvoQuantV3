"""时间模式分析数据库读写。"""

from __future__ import annotations

from database.db_manager import DBManager


class TemporalPatternRepository:
    """时间模式分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建时间模式分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS temporal_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                symbol TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                pattern_value REAL,
                confidence REAL,
                historical_avg REAL,
                current_deviation REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS seasonal_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                dimension TEXT NOT NULL,
                hour_of_day INTEGER,
                day_of_week INTEGER,
                month INTEGER,
                avg_value REAL,
                std_value REAL,
                sample_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, dimension, hour_of_day, day_of_week, month)
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 时间模式
    # ------------------------------------------------------------------

    def save_patterns(self, entries: list[dict]):
        """批量保存时间模式检测结果。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO temporal_patterns
                   (ts, symbol, pattern_type, pattern_value,
                    confidence, historical_avg, current_deviation)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["ts"], e["symbol"], e["pattern_type"],
                    e.get("pattern_value"), e.get("confidence"),
                    e.get("historical_avg"), e.get("current_deviation"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 季节性画像
    # ------------------------------------------------------------------

    def save_seasonal_profiles(self, entries: list[dict]):
        """批量保存季节性统计画像（UPSERT）。"""
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO seasonal_profiles
                   (symbol, dimension, hour_of_day, day_of_week, month,
                    avg_value, std_value, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(symbol, dimension, hour_of_day, day_of_week, month)
                   DO UPDATE SET avg_value=excluded.avg_value,
                                 std_value=excluded.std_value,
                                 sample_count=excluded.sample_count,
                                 created_at=CURRENT_TIMESTAMP""",
                (
                    e["symbol"], e["dimension"],
                    e.get("hour_of_day"), e.get("day_of_week"),
                    e.get("month"), e.get("avg_value"),
                    e.get("std_value"), e.get("sample_count"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def load_latest_patterns(self, symbol: str) -> list[dict]:
        """加载指定 symbol 最新的时间模式检测结果。"""
        rows = self.db.fetch_all(
            """SELECT ts, symbol, pattern_type, pattern_value,
                      confidence, historical_avg, current_deviation
               FROM temporal_patterns
               WHERE symbol = ?
               ORDER BY created_at DESC LIMIT 20""",
            (symbol,),
        )
        return [dict(r) for r in rows] if rows else []

    def load_seasonal_profile(self, symbol: str) -> list[dict]:
        """加载指定 symbol 的季节性画像。"""
        rows = self.db.fetch_all(
            """SELECT symbol, dimension, hour_of_day, day_of_week,
                      month, avg_value, std_value, sample_count
               FROM seasonal_profiles
               WHERE symbol = ?
               ORDER BY dimension, hour_of_day, day_of_week, month""",
            (symbol,),
        )
        return [dict(r) for r in rows] if rows else []
