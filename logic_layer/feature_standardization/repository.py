"""特征标准化数据读写层。"""

from __future__ import annotations

import json

from database.db_manager import DBManager


class FeatureStandardizationRepository:
    """特征标准化数据访问层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建特征标准化相关表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                feature_name TEXT NOT NULL,
                raw_value REAL,
                zscore_7d REAL,
                zscore_30d REAL,
                percentile_30d REAL,
                cross_asset_rank INTEGER,
                cross_asset_rank_total INTEGER,
                regime_label TEXT,
                confidence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fsd_unique
            ON feature_standardization_details(snapshot_time, symbol, feature_name)
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_composites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                composite_name TEXT NOT NULL,
                composite_zscore REAL,
                composite_percentile REAL,
                cross_asset_rank INTEGER,
                cross_asset_rank_total INTEGER,
                regime_label TEXT,
                confidence TEXT,
                component_count INTEGER,
                component_names TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fsc_unique
            ON feature_standardization_composites(snapshot_time, symbol, composite_name)
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_standardization_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol_count INTEGER NOT NULL,
                feature_count INTEGER NOT NULL,
                composite_count INTEGER NOT NULL,
                bundle_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    def save_details(self, rows: list[dict]):
        """批量写入标准化特征明细。"""
        if not rows:
            return
        self.db.conn.executemany(
            """INSERT OR REPLACE INTO feature_standardization_details
               (snapshot_time, symbol, feature_name, raw_value,
                zscore_7d, zscore_30d, percentile_30d,
                cross_asset_rank, cross_asset_rank_total, regime_label, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    r["snapshot_time"], r["symbol"], r["feature_name"],
                    r["raw_value"], r["zscore_7d"], r["zscore_30d"],
                    r["percentile_30d"], r["cross_asset_rank"],
                    r["cross_asset_rank_total"], r["regime_label"], r["confidence"],
                )
                for r in rows
            ],
        )
        self.db.conn.commit()

    def save_composites(self, rows: list[dict]):
        """批量写入复合信号。"""
        if not rows:
            return
        self.db.conn.executemany(
            """INSERT OR REPLACE INTO feature_standardization_composites
               (snapshot_time, symbol, composite_name,
                composite_zscore, composite_percentile,
                cross_asset_rank, cross_asset_rank_total,
                regime_label, confidence, component_count, component_names)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    r["snapshot_time"], r["symbol"], r["composite_name"],
                    r["composite_zscore"], r["composite_percentile"],
                    r["cross_asset_rank"], r["cross_asset_rank_total"],
                    r["regime_label"], r["confidence"],
                    r["component_count"], r["component_names"],
                )
                for r in rows
            ],
        )
        self.db.conn.commit()

    def save_snapshot_bundle(self, snapshot_time: str, symbol_count: int,
                             feature_count: int, composite_count: int,
                             bundle_json: str):
        """保存 AI 消费用 JSON bundle。"""
        self.db.conn.execute(
            """INSERT INTO feature_standardization_snapshots
               (snapshot_time, symbol_count, feature_count, composite_count, bundle_json)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_time, symbol_count, feature_count, composite_count, bundle_json),
        )
        self.db.conn.commit()

    def load_latest_bundle(self) -> dict | None:
        """加载最新 AI bundle。"""
        cursor = self.db.conn.execute(
            """SELECT bundle_json FROM feature_standardization_snapshots
               ORDER BY snapshot_time DESC LIMIT 1"""
        )
        row = cursor.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def fetch_technical_indicators(self, timeframe: str = "1h",
                                   limit_per_symbol: int = 720) -> list[dict]:
        """从 technical_indicators 表读取最近数据。"""
        cursor = self.db.conn.execute(
            """SELECT * FROM technical_indicators
               WHERE timeframe = ?
               ORDER BY symbol, open_time DESC
               LIMIT ?""",
            (timeframe, limit_per_symbol * 20),
        )
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, r)) for r in rows]
