"""新闻情感标注模块单元测试。"""

import pytest
from unittest.mock import MagicMock, patch

from logic_layer.news_sentiment.classifier import NewsSentimentClassifier
from logic_layer.news_sentiment.models import SentimentLabel


class TestNewsSentimentClassifier:
    """分类器测试。"""

    def setup_method(self):
        self.classifier = NewsSentimentClassifier()

    def test_bullish_sentiment(self):
        result = self.classifier.classify("Bitcoin surges past $100k, new all-time high")
        assert result.sentiment == "bullish"
        assert result.confidence >= 0.6

    def test_bearish_sentiment(self):
        result = self.classifier.classify("Major exchange hacked, $500M stolen in exploit")
        assert result.sentiment == "bearish"
        assert result.confidence >= 0.6

    def test_neutral_sentiment(self):
        result = self.classifier.classify("Crypto trading volume remains steady today")
        assert result.sentiment == "neutral"

    def test_event_type_regulatory(self):
        result = self.classifier.classify("SEC files lawsuit against major crypto exchange")
        assert result.event_type == "regulatory"

    def test_event_type_hack(self):
        result = self.classifier.classify("DeFi protocol exploited for $10M")
        assert result.event_type == "hack"

    def test_event_type_partnership(self):
        result = self.classifier.classify("Ethereum collaborates with major firm in new partnership")
        assert result.event_type == "partnership"

    def test_event_type_tokenomics(self):
        result = self.classifier.classify("Token burn event reduces supply by 5%")
        assert result.event_type == "tokenomics"

    def test_event_type_macro(self):
        result = self.classifier.classify("Fed raises interest rate by 25 basis points")
        assert result.event_type == "macro"

    def test_impact_scope_market_wide(self):
        result = self.classifier.classify("Bitcoin market crashes across all exchanges")
        assert result.impact_scope == "market_wide"

    def test_impact_scope_sector(self):
        result = self.classifier.classify("DeFi sector sees massive inflows")
        assert result.impact_scope == "sector_wide"

    def test_impact_scope_asset_specific(self):
        result = self.classifier.classify("Cardano launches new staking pool")
        assert result.impact_scope == "asset_specific"

    def test_impact_duration_mapping(self):
        result = self.classifier.classify("SEC announces new regulation framework")
        assert result.impact_duration == "long_term"

    def test_chinese_bullish_keywords(self):
        result = self.classifier.classify("比特币突破历史新高，市场利好不断")
        assert result.sentiment == "bullish"

    def test_chinese_bearish_keywords(self):
        result = self.classifier.classify("交易所遭黑客攻击，资金暴跌")
        assert result.sentiment == "bearish"

    def test_returns_sentiment_label_dataclass(self):
        result = self.classifier.classify("Normal crypto news update")
        assert isinstance(result, SentimentLabel)
        assert hasattr(result, "sentiment")
        assert hasattr(result, "confidence")
        assert hasattr(result, "event_type")
        assert hasattr(result, "impact_scope")
        assert hasattr(result, "impact_duration")


class TestNewsSentimentService:
    """服务层测试。"""

    def test_run_labeling_no_articles(self):
        mock_db = MagicMock()
        mock_db.conn = MagicMock()
        from logic_layer.news_sentiment.service import NewsSentimentService

        service = NewsSentimentService(db=mock_db)
        service.repository.fetch_unlabeled_articles = MagicMock(return_value=[])
        result = service.run_labeling()
        assert result["status"] == "no_new_articles"
        assert result["labeled_count"] == 0

    def test_run_labeling_with_articles(self):
        mock_db = MagicMock()
        mock_db.conn = MagicMock()
        from logic_layer.news_sentiment.service import NewsSentimentService

        service = NewsSentimentService(db=mock_db)
        service.repository.fetch_unlabeled_articles = MagicMock(return_value=[
            {"id": 1, "url_hash": "abc", "title": "Bitcoin surges to new ATH", "summary": None},
            {"id": 2, "url_hash": "def", "title": "Exchange hacked for $100M", "summary": None},
        ])
        service.repository.save_labels = MagicMock()
        service.repository.update_article_sentiment = MagicMock()

        result = service.run_labeling(save=True)
        assert result["status"] == "ok"
        assert result["labeled_count"] == 2
        service.repository.save_labels.assert_called_once()

