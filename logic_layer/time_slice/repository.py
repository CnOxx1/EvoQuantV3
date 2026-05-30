"""时间切片查询数据访问层 — 各域 point-in-time SQL 查询。"""

from __future__ import annotations

import json
import logging
from typing import Any

from database.db_manager import DBManager

logger = logging.getLogger(__name__)


class TimeSliceRepository:
    """纯只读 repository，对现有数据表做 point-in-time 查询。"""

    def __init__(self, db: DBManager):
        self.db = db

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _rows_to_dicts(self, cursor) -> list[dict]:
        """将 cursor 结果转为 list[dict]。"""
        if not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _symbol_filter_sql(self, symbols: list[str] | None, col: str = "symbol") -> tuple[str, list]:
        """生成可选的 symbol IN (...) 子句。"""
        if not symbols:
            return "", []
        placeholders = ",".join("?" * len(symbols))
        return f"AND {col} IN ({placeholders})", list(symbols)

    # ------------------------------------------------------------------
    # merged_klines (OHLCV)
    # ------------------------------------------------------------------

    def fetch_klines_at(
        self, timestamp: str, symbols: list[str] | None = None, timeframe: str = "1h"
    ) -> list[dict]:
        sym_sql, sym_params = self._symbol_filter_sql(symbols)
        sql = f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY open_time DESC
                ) AS rn
                FROM merged_klines
                WHERE timeframe = ? AND open_time <= ? {sym_sql}
            )
            SELECT * FROM ranked WHERE rn = 1
        """
        cursor = self.db.conn.execute(sql, [timeframe, timestamp] + sym_params)
        rows = self._rows_to_dicts(cursor)
        for r in rows:
            r.pop("rn", None)
        return rows

    # ------------------------------------------------------------------
    # technical_indicators
    # ------------------------------------------------------------------

    def fetch_technical_indicators_at(
        self, timestamp: str, symbols: list[str] | None = None, timeframe: str = "1h"
    ) -> list[dict]:
        sym_sql, sym_params = self._symbol_filter_sql(symbols)
        sql = f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY open_time DESC
                ) AS rn
                FROM technical_indicators
                WHERE timeframe = ? AND open_time <= ? {sym_sql}
            )
            SELECT * FROM ranked WHERE rn = 1
        """
        cursor = self.db.conn.execute(sql, [timeframe, timestamp] + sym_params)
        rows = self._rows_to_dicts(cursor)
        for r in rows:
            r.pop("rn", None)
        return rows

    # ------------------------------------------------------------------
    # feature_standardization (bundle_json)
    # ------------------------------------------------------------------

    def fetch_feature_std_bundle_at(self, timestamp: str) -> dict | None:
        cursor = self.db.conn.execute(
            """SELECT bundle_json, snapshot_time
               FROM feature_standardization_snapshots
               WHERE snapshot_time <= ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (timestamp,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"bundle": json.loads(row[0]), "snapshot_time": row[1]}

    # ------------------------------------------------------------------
    # cross_asset_correlation
    # ------------------------------------------------------------------

    def fetch_correlation_at(self, timestamp: str, window_hours: int = 168) -> dict | None:
        cursor = self.db.conn.execute(
            """SELECT * FROM cross_asset_correlation_snapshots
               WHERE snapshot_time <= ? AND window_hours = ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (timestamp, window_hours),
        )
        rows = self._rows_to_dicts(cursor)
        if not rows:
            return None
        row = rows[0]
        for key in ("matrix_json", "symbols_json"):
            if key in row and isinstance(row[key], str):
                row[key] = json.loads(row[key])
        return row

    # ------------------------------------------------------------------
    # cross_asset_relative_strength
    # ------------------------------------------------------------------

    def fetch_relative_strength_at(
        self, timestamp: str, symbols: list[str] | None = None
    ) -> list[dict]:
        # 先找最近的 snapshot_time
        cursor = self.db.conn.execute(
            """SELECT MAX(snapshot_time) FROM cross_asset_relative_strength
               WHERE snapshot_time <= ?""",
            (timestamp,),
        )
        max_row = cursor.fetchone()
        if not max_row or not max_row[0]:
            return []
        snap_time = max_row[0]
        sym_sql, sym_params = self._symbol_filter_sql(symbols)
        cursor = self.db.conn.execute(
            f"""SELECT * FROM cross_asset_relative_strength
                WHERE snapshot_time = ? {sym_sql}""",
            [snap_time] + sym_params,
        )
        return self._rows_to_dicts(cursor)

    # ------------------------------------------------------------------
    # cross_asset_sector_rotation
    # ------------------------------------------------------------------

    def fetch_sector_rotation_at(self, timestamp: str) -> list[dict]:
        cursor = self.db.conn.execute(
            """SELECT MAX(snapshot_time) FROM cross_asset_sector_rotation
               WHERE snapshot_time <= ?""",
            (timestamp,),
        )
        max_row = cursor.fetchone()
        if not max_row or not max_row[0]:
            return []
        snap_time = max_row[0]
        cursor = self.db.conn.execute(
            "SELECT * FROM cross_asset_sector_rotation WHERE snapshot_time = ?",
            (snap_time,),
        )
        return self._rows_to_dicts(cursor)

    # ------------------------------------------------------------------
    # cross_asset_fund_flow
    # ------------------------------------------------------------------

    def fetch_fund_flow_at(self, timestamp: str) -> list[dict]:
        cursor = self.db.conn.execute(
            """SELECT MAX(snapshot_time) FROM cross_asset_fund_flow
               WHERE snapshot_time <= ?""",
            (timestamp,),
        )
        max_row = cursor.fetchone()
        if not max_row or not max_row[0]:
            return []
        snap_time = max_row[0]
        cursor = self.db.conn.execute(
            "SELECT * FROM cross_asset_fund_flow WHERE snapshot_time = ?",
            (snap_time,),
        )
        return self._rows_to_dicts(cursor)

    # ------------------------------------------------------------------
    # portfolio_risk
    # ------------------------------------------------------------------

    def fetch_portfolio_risk_at(
        self, timestamp: str, portfolio_name: str = "default"
    ) -> dict | None:
        cursor = self.db.conn.execute(
            """SELECT * FROM portfolio_risk_snapshots
               WHERE snapshot_time <= ? AND portfolio_name = ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (timestamp, portfolio_name),
        )
        rows = self._rows_to_dicts(cursor)
        if not rows:
            return None
        row = rows[0]
        for key in ("weights_json", "risk_contributions_json", "concentration_json"):
            if key in row and isinstance(row[key], str):
                try:
                    row[key] = json.loads(row[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return row

    # ------------------------------------------------------------------
    # macro_context
    # ------------------------------------------------------------------

    def fetch_macro_context_at(self, timestamp: str) -> list[dict]:
        cursor = self.db.conn.execute(
            """SELECT * FROM macro_context_snapshots
               WHERE snapshot_time <= ?
               ORDER BY snapshot_time DESC
               LIMIT 50""",
            (timestamp,),
        )
        return self._rows_to_dicts(cursor)

    # ------------------------------------------------------------------
    # market_breadth
    # ------------------------------------------------------------------

    def fetch_market_breadth_at(self, timestamp: str) -> dict | None:
        cursor = self.db.conn.execute(
            """SELECT * FROM market_breadth_snapshots
               WHERE snapshot_time <= ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (timestamp,),
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # asset_readiness
    # ------------------------------------------------------------------

    def fetch_asset_readiness_at(self, timestamp: str) -> dict | None:
        cursor = self.db.conn.execute(
            """SELECT * FROM asset_readiness_snapshots
               WHERE snapshot_time <= ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (timestamp,),
        )
        rows = self._rows_to_dicts(cursor)
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # ai_market_context
    # ------------------------------------------------------------------

    def fetch_ai_context_at(
        self, timestamp: str, entity_keys: list[str] | None = None
    ) -> list[dict]:
        ek_sql, ek_params = self._symbol_filter_sql(entity_keys, col="entity_key")
        sql = f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY entity_key ORDER BY snapshot_time DESC
                ) AS rn
                FROM ai_market_context_snapshots
                WHERE snapshot_time <= ? {ek_sql}
            )
            SELECT * FROM ranked WHERE rn = 1
        """
        cursor = self.db.conn.execute(sql, [timestamp] + ek_params)
        rows = self._rows_to_dicts(cursor)
        for r in rows:
            r.pop("rn", None)
            if "bundle_json" in r and isinstance(r["bundle_json"], str):
                try:
                    r["bundle_json"] = json.loads(r["bundle_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
        return rows

    # ------------------------------------------------------------------
    # exchange_comparison
    # ------------------------------------------------------------------

    def fetch_exchange_comparison_at(
        self, timestamp: str, symbols: list[str] | None = None
    ) -> list[dict]:
        sym_sql, sym_params = self._symbol_filter_sql(symbols)
        sql = f"""
            WITH ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol, exchange_a, exchange_b
                    ORDER BY timestamp DESC
                ) AS rn
                FROM exchange_comparison_snapshots
                WHERE timestamp <= ? {sym_sql}
            )
            SELECT * FROM ranked WHERE rn = 1
        """
        cursor = self.db.conn.execute(sql, [timestamp] + sym_params)
        rows = self._rows_to_dicts(cursor)
        for r in rows:
            r.pop("rn", None)
        return rows

    # ------------------------------------------------------------------
    # 特征历史序列查询
    # ------------------------------------------------------------------

    def fetch_klines_history(
        self, symbol: str, start: str, end: str, timeframe: str = "1h"
    ) -> list[dict]:
        """获取指定资产在时间范围内的 K 线历史。"""
        sql = """
            SELECT open_time, open, high, low, close, volume
            FROM merged_klines
            WHERE symbol = ? AND timeframe = ? AND open_time >= ? AND open_time <= ?
            ORDER BY open_time ASC
        """
        cursor = self.db.conn.execute(sql, [symbol, timeframe, start, end])
        return self._rows_to_dicts(cursor)

    def fetch_technical_indicators_history(
        self, symbol: str, start: str, end: str, features: list[str] | None = None,
        timeframe: str = "1h"
    ) -> list[dict]:
        """获取指定资产在时间范围内的技术指标历史。"""
        sql = """
            SELECT * FROM technical_indicators
            WHERE symbol = ? AND timeframe = ? AND open_time >= ? AND open_time <= ?
            ORDER BY open_time ASC
        """
        cursor = self.db.conn.execute(sql, [symbol, timeframe, start, end])
        rows = self._rows_to_dicts(cursor)
        if features and rows:
            keep_cols = {"open_time", "symbol", "timeframe"} | set(features)
            rows = [{k: v for k, v in r.items() if k in keep_cols} for r in rows]
        return rows

    def fetch_feature_std_history(
        self, symbol: str, start: str, end: str
    ) -> list[dict]:
        """获取标准化特征历史序列。"""
        cursor = self.db.conn.execute(
            """SELECT bundle_json, snapshot_time
               FROM feature_standardization_snapshots
               WHERE snapshot_time >= ? AND snapshot_time <= ?
               ORDER BY snapshot_time ASC""",
            (start, end),
        )
        results = []
        for row in cursor.fetchall():
            bundle = json.loads(row[0])
            assets = bundle.get("assets", [])
            for asset in assets:
                if asset.get("symbol") == symbol:
                    results.append({
                        "snapshot_time": row[1],
                        **asset,
                    })
                    break
        return results
