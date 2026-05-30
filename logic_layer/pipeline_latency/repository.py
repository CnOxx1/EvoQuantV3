"""数据管道延迟追踪数据访问层 — 查询各域最新数据时间戳。"""

from __future__ import annotations

import logging
from typing import Any

from database.db_manager import DBManager

logger = logging.getLogger(__name__)


class PipelineLatencyRepository:
    """查询各域最新数据写入时间，计算端到端延迟。"""

    def __init__(self, db: DBManager):
        self.db = db

    def _safe_query(self, sql: str, params: tuple = ()) -> Any:
        """安全执行查询，表不存在时返回 None。"""
        try:
            cursor = self.db.conn.execute(sql, params)
            return cursor.fetchone()
        except Exception as e:
            logger.debug("查询失败 (表可能不存在): %s", e)
            return None

    def get_latest_klines_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(open_time) FROM merged_klines"
        )
        return row[0] if row else None

    def get_latest_technical_indicators_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(open_time) FROM technical_indicators"
        )
        return row[0] if row else None

    def get_latest_feature_std_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM feature_standardization_snapshots"
        )
        return row[0] if row else None

    def get_latest_cross_asset_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM cross_asset_correlation_snapshots"
        )
        return row[0] if row else None

    def get_latest_portfolio_risk_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM portfolio_risk_snapshots"
        )
        return row[0] if row else None

    def get_latest_macro_context_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM macro_context_snapshots"
        )
        return row[0] if row else None

    def get_latest_market_breadth_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM market_breadth_snapshots"
        )
        return row[0] if row else None

    def get_latest_asset_readiness_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM asset_readiness_snapshots"
        )
        return row[0] if row else None

    def get_latest_ai_context_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(snapshot_time) FROM ai_market_context_snapshots"
        )
        return row[0] if row else None

    def get_latest_exchange_comparison_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(timestamp) FROM exchange_comparison_snapshots"
        )
        return row[0] if row else None

    def get_latest_news_time(self) -> str | None:
        row = self._safe_query(
            "SELECT MAX(published_at) FROM news_articles"
        )
        return row[0] if row else None

    def get_klines_count_last_hour(self) -> int:
        row = self._safe_query(
            "SELECT COUNT(*) FROM merged_klines WHERE open_time >= datetime('now', '-1 hour')"
        )
        return row[0] if row else 0
