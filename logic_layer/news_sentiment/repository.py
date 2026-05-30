"""新闻情感标注数据访问层。"""

from __future__ import annotations

import json
import logging

from database.db_manager import DBManager

logger = logging.getLogger(__name__)


class NewsSentimentRepository:
    """新闻情感标注读写。"""

    def __init__(self, db: DBManager):
        self.db = db

    def ensure_tables(self):
        """确保情感标注表存在。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS news_sentiment_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                url_hash TEXT NOT NULL,
                title TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                confidence REAL NOT NULL,
                event_type TEXT NOT NULL,
                impact_scope TEXT NOT NULL,
                impact_duration TEXT NOT NULL,
                labeled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(url_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nsl_sentiment
            ON news_sentiment_labels(sentiment)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nsl_event_type
            ON news_sentiment_labels(event_type)
        """)
        self.db.conn.commit()

    def fetch_unlabeled_articles(self, limit: int = 200) -> list[dict]:
        """获取尚未标注的新闻文章。"""
        cursor = self.db.conn.execute("""
            SELECT a.id, a.url_hash, a.title, a.summary,
                   a.relevance_symbols, a.published_at
            FROM news_articles a
            LEFT JOIN news_sentiment_labels l ON a.url_hash = l.url_hash
            WHERE l.id IS NULL
            ORDER BY a.published_at DESC
            LIMIT ?
        """, (limit,))
        cols = [d[0] for d in cursor.description] if cursor.description else []
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def save_labels(self, labels: list[dict]):
        """批量保存情感标注结果。"""
        if not labels:
            return
        self.db.conn.executemany("""
            INSERT OR REPLACE INTO news_sentiment_labels
            (article_id, url_hash, title, sentiment, confidence,
             event_type, impact_scope, impact_duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (r["article_id"], r["url_hash"], r["title"], r["sentiment"],
             r["confidence"], r["event_type"], r["impact_scope"], r["impact_duration"])
            for r in labels
        ])
        self.db.conn.commit()

    def update_article_sentiment(self, url_hash: str, sentiment: str):
        """回写 sentiment_label 到 news_articles 表（若为视图则跳过）。"""
        try:
            self.db.conn.execute(
                "UPDATE news_articles SET sentiment_label = ? WHERE url_hash = ?",
                (sentiment, url_hash),
            )
            self.db.conn.commit()
        except Exception:
            # news_articles 可能是只读 TEMP VIEW（跨库路由场景），跳过回写
            pass

    def load_latest_sentiment_bundle(self, hours: int = 72, limit: int = 100) -> dict:
        """加载最近 N 小时的情感标注摘要。"""
        cursor = self.db.conn.execute("""
            SELECT l.sentiment, l.event_type, l.impact_scope,
                   l.impact_duration, l.confidence, l.title,
                   a.relevance_symbols, a.published_at
            FROM news_sentiment_labels l
            JOIN news_articles a ON l.url_hash = a.url_hash
            WHERE a.published_at >= datetime('now', ?)
            ORDER BY a.published_at DESC
            LIMIT ?
        """, (f"-{hours} hours", limit))
        cols = [d[0] for d in cursor.description] if cursor.description else []
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

