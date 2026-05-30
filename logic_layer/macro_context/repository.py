from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from database.db_manager import DBManager
from logic_layer.macro_context.models import MacroContextSnapshot


class MacroContextRepository:
    """宏观上下文模块的数据读写层。"""

    def __init__(self, db: DBManager):
        self.db = db

    def fetch_latest_macro_points(
        self,
        factor_ids: list[str] | None = None,
        interval: str | None = None,
        include_disabled_factors: bool = False,
    ) -> list[dict]:
        sql = """
            SELECT
                latest.factor_id,
                catalog.name,
                catalog.category,
                latest.factor_type,
                latest.interval,
                latest.observation_time,
                latest.value,
                latest.unit,
                latest.currency,
                latest.quality_flag,
                latest.source_name,
                latest.source_symbol,
                latest.source_priority,
                latest.collected_at,
                catalog.staleness_ttl_seconds,
                catalog.enabled
            FROM latest_macro_timeseries AS latest
            INNER JOIN macro_factor_catalog AS catalog
                ON latest.factor_id = catalog.factor_id
        """
        clauses: list[str] = []
        params: list = []
        if factor_ids:
            placeholders = ",".join("?" for _ in factor_ids)
            clauses.append(f"latest.factor_id IN ({placeholders})")
            params.extend(factor_ids)
        if interval:
            clauses.append("latest.interval = ?")
            params.append(interval)
        if not include_disabled_factors:
            clauses.append("catalog.enabled = 1")

        if clauses:
            sql = f"{sql} WHERE {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY latest.factor_id, latest.interval"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]

    def fetch_reference_point(
        self,
        factor_id: str,
        interval: str,
        target_time: datetime,
    ) -> Optional[dict]:
        row = self.db.fetch_one(
            """
            SELECT observation_time, value
            FROM macro_timeseries
            WHERE factor_id = ?
              AND interval = ?
              AND observation_time <= ?
            ORDER BY observation_time DESC, id DESC
            LIMIT 1
            """,
            (factor_id, interval, target_time.isoformat()),
        )
        return dict(row) if row is not None else None

    def save_context_snapshots(self, snapshots: list[MacroContextSnapshot]):
        if not snapshots:
            logger.warning("没有可保存的 macro_context_snapshots 数据")
            return

        columns = MacroContextSnapshot.TABLE_COLUMNS
        placeholders = ", ".join(["?"] * len(columns))
        conflict_columns = ["factor_id", "interval", "observation_time"]
        update_columns = [
            column for column in columns if column not in conflict_columns
        ]
        updates_sql = ",\n                ".join(
            f"{column} = excluded.{column}"
            for column in update_columns
        )
        sql = f"""
            INSERT INTO macro_context_snapshots (
                {", ".join(columns)}
            ) VALUES ({placeholders})
            ON CONFLICT(factor_id, interval, observation_time)
            DO UPDATE SET
                {updates_sql}
        """
        self.db.execute_many(sql, [snapshot.to_db_tuple() for snapshot in snapshots])
        self.db.commit()
        logger.info(f"已保存 {len(snapshots)} 条 macro_context_snapshots")

    def fetch_latest_context_snapshots(
        self,
        factor_ids: list[str] | None = None,
        interval: str | None = None,
    ) -> list[dict]:
        sql = """
            WITH ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY factor_id, interval
                        ORDER BY observation_time DESC, id DESC
                    ) AS rn
                FROM macro_context_snapshots
            )
            SELECT *
            FROM ranked
            WHERE rn = 1
        """
        clauses: list[str] = []
        params: list = []
        if factor_ids:
            placeholders = ",".join("?" for _ in factor_ids)
            clauses.append(f"factor_id IN ({placeholders})")
            params.extend(factor_ids)
        if interval:
            clauses.append("interval = ?")
            params.append(interval)
        if clauses:
            sql = f"{sql} AND {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY factor_id, interval"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]
