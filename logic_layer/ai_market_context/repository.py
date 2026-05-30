import json
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.ai_market_context.models import AIMarketContextSnapshot


class AIMarketContextRepository:
    """AI 市场上下文聚合层读写。"""

    def __init__(self, db: DBManager):
        self.db = db

    def save_snapshots(self, snapshots: list[AIMarketContextSnapshot]):
        if not snapshots:
            return
        columns = AIMarketContextSnapshot.TABLE_COLUMNS
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"""
            INSERT INTO ai_market_context_snapshots (
                {", ".join(columns)}
            ) VALUES ({placeholders})
            ON CONFLICT(entity_key, snapshot_time) DO UPDATE SET
                coverage_score=excluded.coverage_score,
                data_quality_flag=excluded.data_quality_flag,
                bundle_json=excluded.bundle_json
        """
        self.db.execute_many(sql, [snapshot.to_db_tuple() for snapshot in snapshots])
        self.db.commit()

    def fetch_recent_news(self, entity_key: str, limit: int = 12) -> list[dict]:
        rows = self.db.fetch_all(
            """
            SELECT source, title, summary, url, published_at, collected_at, tags
            FROM news_articles
            WHERE relevance_symbols LIKE ?
            ORDER BY COALESCE(published_at, collected_at) DESC
            LIMIT ?
            """,
            (f'%"{entity_key.upper()}"%', limit),
        )
        return [dict(row) for row in rows]

    def fetch_upcoming_events(self, entity_key: str, limit: int = 12) -> list[dict]:
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        rows = self.db.fetch_all(
            """
            SELECT event_type, title, symbol, scheduled_at, importance_score, status, source_name
            FROM event_calendar_events
            WHERE status = 'scheduled'
              AND scheduled_at >= ?
              AND symbol IN (?, 'MARKET')
            ORDER BY scheduled_at ASC
            LIMIT ?
            """,
            (now, entity_key.upper(), limit),
        )
        return [dict(row) for row in rows]

    def fetch_latest_exchange_comparison(self, symbol: str, limit: int = 6) -> list[dict]:
        rows = self.db.fetch_all(
            """
            SELECT *
            FROM exchange_comparison_snapshots
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (symbol, limit),
        )
        return [dict(row) for row in rows]

    def load_latest_snapshots(self, entity_keys: list[str] | None = None) -> list[dict]:
        sql = """
            WITH ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY entity_key
                        ORDER BY snapshot_time DESC, id DESC
                    ) AS rn
                FROM ai_market_context_snapshots
            )
            SELECT *
            FROM ranked
            WHERE rn = 1
        """
        params: list[str] = []
        if entity_keys:
            placeholders = ",".join("?" for _ in entity_keys)
            sql = f"{sql} AND entity_key IN ({placeholders})"
            params.extend(entity_keys)
        sql = f"{sql} ORDER BY entity_key"
        rows = self.db.fetch_all(sql, tuple(params))
        parsed: list[dict] = []
        for row in rows:
            item = dict(row)
            bundle_json = item.get("bundle_json")
            item["bundle"] = json.loads(bundle_json) if bundle_json else {}
            parsed.append(item)
        return parsed
