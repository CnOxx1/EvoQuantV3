"""跨资产分析数据库读写。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

try:
    import orjson
    _dumps = lambda obj: orjson.dumps(obj).decode()
    _loads = orjson.loads
except ImportError:
    _dumps = json.dumps
    _loads = json.loads

from database.db_manager import DBManager


class CrossAssetRepository:
    """跨资产分析结果的读取与落库。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """创建跨资产分析所需的数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_correlation_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                window_hours INTEGER NOT NULL,
                matrix_json TEXT NOT NULL,
                symbols_json TEXT NOT NULL,
                avg_correlation REAL,
                max_correlation REAL,
                min_correlation REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_relative_strength (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset TEXT NOT NULL,
                sector TEXT,
                tier TEXT,
                rs_vs_btc_7d REAL,
                rs_vs_btc_3d REAL,
                rs_vs_btc_1d REAL,
                rs_rank INTEGER,
                rs_momentum TEXT,
                price_change_7d_pct REAL,
                volume_change_7d_pct REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_sector_rotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                sector TEXT NOT NULL,
                sector_return_7d REAL,
                sector_volatility_7d REAL,
                sector_momentum_score REAL,
                sector_net_flow_24h REAL,
                sector_oi_change_24h REAL,
                constituent_count INTEGER,
                rotation_phase TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_asset_fund_flow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                scope TEXT NOT NULL,
                net_taker_flow_1h REAL,
                net_taker_flow_24h REAL,
                oi_change_1h REAL,
                oi_change_24h REAL,
                aggressive_buy_share REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 相关性矩阵
    # ------------------------------------------------------------------

    def save_correlation_snapshot(
        self,
        snapshot_time: str,
        window_hours: int,
        matrix: dict[str, dict[str, float]],
        symbols: list[str],
        avg_correlation: float,
        max_correlation: float,
        min_correlation: float,
    ):
        self.db.conn.execute(
            """INSERT INTO cross_asset_correlation_snapshots
               (snapshot_time, window_hours, matrix_json, symbols_json,
                avg_correlation, max_correlation, min_correlation)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_time,
                window_hours,
                _dumps(matrix),
                _dumps(symbols),
                avg_correlation,
                max_correlation,
                min_correlation,
            ),
        )
        self.db.conn.commit()

    def load_latest_correlation(
        self, window_hours: int = 168
    ) -> dict | None:
        row = self.db.fetch_one(
            """SELECT * FROM cross_asset_correlation_snapshots
               WHERE window_hours = ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (window_hours,),
        )
        if not row:
            return None
        return {
            "snapshot_time": row["snapshot_time"],
            "window_hours": row["window_hours"],
            "matrix": _loads(row["matrix_json"]),
            "symbols": _loads(row["symbols_json"]),
            "avg_correlation": row["avg_correlation"],
            "max_correlation": row["max_correlation"],
            "min_correlation": row["min_correlation"],
        }

    # ------------------------------------------------------------------
    # 相对强弱
    # ------------------------------------------------------------------

    def save_relative_strength(self, entries: list[dict]):
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO cross_asset_relative_strength
                   (snapshot_time, symbol, asset, sector, tier,
                    rs_vs_btc_7d, rs_vs_btc_3d, rs_vs_btc_1d,
                    rs_rank, rs_momentum, price_change_7d_pct,
                    volume_change_7d_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["snapshot_time"], e["symbol"], e["asset"],
                    e.get("sector"), e.get("tier"),
                    e.get("rs_vs_btc_7d"), e.get("rs_vs_btc_3d"),
                    e.get("rs_vs_btc_1d"), e.get("rs_rank"),
                    e.get("rs_momentum"), e.get("price_change_7d_pct"),
                    e.get("volume_change_7d_pct"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 板块轮动
    # ------------------------------------------------------------------

    def save_sector_rotation(self, entries: list[dict]):
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO cross_asset_sector_rotation
                   (snapshot_time, sector, sector_return_7d,
                    sector_volatility_7d, sector_momentum_score,
                    sector_net_flow_24h, sector_oi_change_24h,
                    constituent_count, rotation_phase)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["snapshot_time"], e["sector"],
                    e.get("sector_return_7d"), e.get("sector_volatility_7d"),
                    e.get("sector_momentum_score"),
                    e.get("sector_net_flow_24h"),
                    e.get("sector_oi_change_24h"),
                    e.get("constituent_count"), e.get("rotation_phase"),
                ),
            )
        self.db.conn.commit()

    # ------------------------------------------------------------------
    # 资金流向
    # ------------------------------------------------------------------

    def save_fund_flow(self, entries: list[dict]):
        for e in entries:
            self.db.conn.execute(
                """INSERT INTO cross_asset_fund_flow
                   (snapshot_time, scope, net_taker_flow_1h,
                    net_taker_flow_24h, oi_change_1h, oi_change_24h,
                    aggressive_buy_share)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    e["snapshot_time"], e["scope"],
                    e.get("net_taker_flow_1h"), e.get("net_taker_flow_24h"),
                    e.get("oi_change_1h"), e.get("oi_change_24h"),
                    e.get("aggressive_buy_share"),
                ),
            )
        self.db.conn.commit()
