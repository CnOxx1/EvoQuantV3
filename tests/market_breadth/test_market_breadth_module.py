import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from logic_layer.market_breadth.service import MarketBreadthService


class StubService:
    def __init__(self, payload):
        self.payload = payload

    def load_latest_market_context_bundle(self, *args, **kwargs):
        return self.payload

    def load_latest_context_bundle(self, *args, **kwargs):
        return self.payload


def test_market_breadth_only_counts_ai_ready_bundle_views(tmp_path):
    db = DBManager(str(tmp_path / "market_breadth.sqlite"))
    db.init_tables()

    exchange_payload = {
        "as_of": "2026-05-19T12:00:00",
        "raw_row_count": 12,
        "ai_ready_source_names": ["ticker", "orderbook"],
        "ai_excluded_source_names": ["funding"],
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "row_count": 2,
                "raw_row_count": 6,
                "spot": [{"last_price": 100000.0}],
                "orderbook": [{"mid_price": 100001.0}],
                "funding": [],
                "trade_flow": [],
                "trade_flow_spot": [],
                "trade_flow_derivatives": [],
                "open_interest": [],
                "liquidations": [],
                "positioning": [],
                "basis": [],
                "coverage_summary": {
                    "configured_section_count": 7,
                    "complete_sections": ["spot", "orderbook"],
                    "partial_sections": [],
                },
                "data_quality_flags": [],
                "quality_notes": [],
            },
            {
                "symbol": "ETH/USDT",
                "row_count": 0,
                "raw_row_count": 6,
                "spot": [],
                "orderbook": [],
                "funding": [],
                "trade_flow": [],
                "trade_flow_spot": [],
                "trade_flow_derivatives": [],
                "open_interest": [],
                "liquidations": [],
                "positioning": [],
                "basis": [],
                "coverage_summary": {
                    "configured_section_count": 7,
                    "complete_sections": [
                        "spot",
                        "orderbook",
                        "funding",
                        "trade_flow_spot",
                        "trade_flow_derivatives",
                        "open_interest",
                        "basis",
                    ],
                    "partial_sections": [],
                },
                "data_quality_flags": ["stale_subsection_present"],
                "quality_notes": ["ETH 只有 raw 快照，没有 AI-ready section。"],
            },
        ],
    }
    news_payload = {
        "raw_article_count": 5,
        "ai_ready_source_names": ["CoinDesk"],
        "ai_excluded_source_names": ["Blockworks"],
        "latest_articles": [
            {
                "source": "CoinDesk",
                "title": "btc-news",
                "relevance_symbols": ["BTC"],
                "published_at": "2026-05-19T10:00:00",
            }
        ],
    }
    tokenomics_payload = {
        "raw_upcoming_unlock_event_count": 3,
        "ai_ready_source_names": ["unlock_schedule"],
        "ai_excluded_source_names": ["treasury_wallet_flow"],
        "upcoming_unlock_events": [
            {
                "entity_key": "ETH",
                "source_name": "unlock_schedule",
                "unlock_value_usd": 50000000.0,
            }
        ],
        "entities": [
            {
                "entity_key": "ETH",
                "scheduled_unlock_usd_7d": 50000000.0,
                "staking_ratio": 0.61,
                "quality_flag": "ok",
            }
        ],
    }

    service = MarketBreadthService(db=db)
    service.exchange_service = StubService(exchange_payload)
    service.news_service = StubService(news_payload)
    service.tokenomics_service = StubService(tokenomics_payload)

    bundle = service.build_latest_context_bundle(asset_keys=["BTC", "ETH"])

    assert bundle["scope_kind"] == "filtered"
    assert bundle["ai_ready_asset_count"] == 1
    assert bundle["article_asset_count_72h"] == 1
    assert bundle["unlock_asset_count_30d"] == 1
    assert bundle["coverage_summary"]["exchange_symbol_count"] == 2
    assert bundle["coverage_summary"]["exchange_visible_symbol_count"] == 1
    assert bundle["coverage_summary"]["news_raw_article_count_72h"] == 5
    assert bundle["coverage_summary"]["unlock_raw_event_count_30d"] == 3
    btc = next(item for item in bundle["assets"] if item["asset"] == "BTC")
    eth = next(item for item in bundle["assets"] if item["asset"] == "ETH")
    assert btc["is_ai_ready_market_asset"] is True
    assert eth["is_ai_ready_market_asset"] is False
    assert eth["exchange_visible_section_count"] == 0

    snapshot = service.save_snapshot(bundle)
    row = db.fetch_one(
        """
        SELECT breadth_status, ai_ready_asset_count, article_asset_count, unlock_asset_count
        FROM market_breadth_snapshots
        WHERE id = ?
        """,
        (snapshot["id"],),
    )
    assert row["ai_ready_asset_count"] == 1
    assert row["article_asset_count"] == 1
    assert row["unlock_asset_count"] == 1
    service.close()


def test_market_breadth_flags_raw_only_news_and_unlock_context(tmp_path):
    db = DBManager(str(tmp_path / "market_breadth_raw_only.sqlite"))
    db.init_tables()

    exchange_payload = {
        "as_of": "2026-05-19T12:00:00",
        "raw_row_count": 9,
        "ai_ready_source_names": [],
        "ai_excluded_source_names": ["ticker", "orderbook", "funding"],
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "row_count": 0,
                "raw_row_count": 9,
                "spot": [],
                "orderbook": [],
                "funding": [],
                "trade_flow": [],
                "trade_flow_spot": [],
                "trade_flow_derivatives": [],
                "open_interest": [],
                "liquidations": [],
                "positioning": [],
                "basis": [],
                "coverage_summary": {
                    "configured_section_count": 7,
                    "complete_sections": [
                        "spot",
                        "orderbook",
                        "funding",
                        "trade_flow_spot",
                        "trade_flow_derivatives",
                        "open_interest",
                        "basis",
                    ],
                    "partial_sections": [],
                },
                "data_quality_flags": ["stale_subsection_present"],
                "quality_notes": ["只有 raw 交易所快照。"],
            }
        ],
    }
    news_payload = {
        "raw_article_count": 4,
        "ai_ready_source_names": [],
        "ai_excluded_source_names": ["CoinDesk"],
        "latest_articles": [],
    }
    tokenomics_payload = {
        "raw_upcoming_unlock_event_count": 2,
        "ai_ready_source_names": [],
        "ai_excluded_source_names": ["unlock_schedule"],
        "upcoming_unlock_events": [],
        "entities": [],
    }

    service = MarketBreadthService(db=db)
    service.exchange_service = StubService(exchange_payload)
    service.news_service = StubService(news_payload)
    service.tokenomics_service = StubService(tokenomics_payload)

    bundle = service.build_latest_context_bundle(asset_keys=["BTC"])

    assert bundle["ai_ready_asset_count"] == 0
    assert bundle["article_asset_count_72h"] == 0
    assert bundle["unlock_asset_count_30d"] == 0
    assert "exchange_raw_only_no_ai_ready_assets" in bundle["data_quality_flags"]
    assert "news_raw_only_no_ai_ready_articles" in bundle["data_quality_flags"]
    assert "unlock_raw_only_no_ai_ready_events" in bundle["data_quality_flags"]
    assert any("没有任何资产保留 AI-ready 市场结构 section" in note for note in bundle["quality_notes"])
    assert any("raw 文章" in note for note in bundle["quality_notes"])
    assert any("raw 解锁事件" in note for note in bundle["quality_notes"])
    service.close()
