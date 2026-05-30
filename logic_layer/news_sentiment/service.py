"""新闻情感标注编排服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.news_sentiment.classifier import NewsSentimentClassifier
from logic_layer.news_sentiment.repository import NewsSentimentRepository

logger = logging.getLogger(__name__)


class NewsSentimentService:
    """新闻情感标注入口。"""

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = NewsSentimentRepository(self.db)
        self.classifier = NewsSentimentClassifier()

    def init_storage(self):
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_labeling(self, limit: int = 200, save: bool = True) -> dict:
        """对未标注新闻进行情感分类。"""
        articles = self.repository.fetch_unlabeled_articles(limit)
        if not articles:
            return {"status": "no_new_articles", "labeled_count": 0}

        labels: list[dict] = []
        for article in articles:
            result = self.classifier.classify(
                title=article["title"],
                summary=article.get("summary"),
            )
            labels.append({
                "article_id": article["id"],
                "url_hash": article["url_hash"],
                "title": article["title"],
                "sentiment": result.sentiment,
                "confidence": result.confidence,
                "event_type": result.event_type,
                "impact_scope": result.impact_scope,
                "impact_duration": result.impact_duration,
            })

        if save:
            self.repository.save_labels(labels)
            for label in labels:
                self.repository.update_article_sentiment(
                    label["url_hash"], label["sentiment"]
                )

        # 统计
        sentiments = {}
        events = {}
        for l in labels:
            sentiments[l["sentiment"]] = sentiments.get(l["sentiment"], 0) + 1
            events[l["event_type"]] = events.get(l["event_type"], 0) + 1

        return {
            "status": "ok",
            "labeled_count": len(labels),
            "sentiment_distribution": sentiments,
            "event_type_distribution": events,
        }

    def load_latest_context_bundle(self, hours: int = 72) -> dict:
        """加载最近情感标注的 AI bundle。"""
        rows = self.repository.load_latest_sentiment_bundle(hours)
        if not rows:
            return {"status": "no_data", "as_of": self._utc_now_iso()}

        sentiments = {}
        events = {}
        for r in rows:
            sentiments[r["sentiment"]] = sentiments.get(r["sentiment"], 0) + 1
            events[r["event_type"]] = events.get(r["event_type"], 0) + 1

        return {
            "status": "ready",
            "as_of": self._utc_now_iso(),
            "hours_covered": hours,
            "article_count": len(rows),
            "sentiment_distribution": sentiments,
            "event_type_distribution": events,
            "articles": rows,
        }

    def close(self):
        self.db.close()

