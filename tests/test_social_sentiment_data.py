"""Unit tests for SocialSentimentDataService."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.social_sentiment_data.service import SocialSentimentDataService


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _recent_iso(hours_ago=1):
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class StaticMockClient:
    """Static mock client returning fake social sentiment data."""

    def fetch_santiment_social_volume(self, slug, from_dt, to_dt):
        return [
            {"datetime": _recent_iso(2), "value": 150},
            {"datetime": _recent_iso(1), "value": 200},
        ]

    def fetch_santiment_sentiment(self, slug, from_dt, to_dt):
        return [
            {"datetime": _recent_iso(2), "value": 2.5},
            {"datetime": _recent_iso(1), "value": -1.0},
        ]

    def fetch_lunarcrush_social(self, symbol):
        return [
            {
                "time": _recent_iso(0),
                "posts_total": 3200,
                "sentiment": 0.65,
                "bullish": 0.7,
                "bearish": 0.3,
            },
        ]

    def close(self):
        pass


def test_init_storage_creates_tables(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SocialSentimentDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "social_mentions" in tables
    assert "social_sentiment_agg" in tables


def test_collect_once_stores_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SocialSentimentDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC"])

    agg_count = db.conn.execute(
        "SELECT COUNT(*) FROM social_sentiment_agg"
    ).fetchone()[0]
    assert agg_count >= 2


def test_load_latest_context_bundle_returns_expected_structure(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SocialSentimentDataService(client=StaticMockClient(), db=db)
    service.init_storage()
    service.collect_once(symbols=["BTC"])

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "ready"
    assert "summaries" in bundle
    assert "coverage" in bundle


def test_load_latest_context_bundle_no_data(tmp_path):
    db = DBManager(str(tmp_path / "test.sqlite"))
    service = SocialSentimentDataService(client=StaticMockClient(), db=db)
    service.init_storage()

    bundle = service.load_latest_context_bundle(symbols=["BTC"])
    assert bundle["status"] == "no_data"
