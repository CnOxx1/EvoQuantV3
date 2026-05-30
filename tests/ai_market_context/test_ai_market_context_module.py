import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from logic_layer.ai_market_context.service import AIMarketContextService


class StubService:
    def __init__(self, payload):
        self.payload = payload

    def load_latest_market_context_bundle(self, *args, **kwargs):
        return self.payload

    def load_latest_context_bundle(self, *args, **kwargs):
        return self.payload

    def load_upcoming_context_bundle(self, *args, **kwargs):
        return self.payload

    def build_latest_context_bundle(self, *args, **kwargs):
        return self.payload


class StubAuditService:
    def __init__(self, payload):
        self.payload = payload

    def load_market_world_audit(self):
        return self.payload


class StubRepository:
    def __init__(self, rows=None):
        self.rows = rows or [
            {"symbol": "BTC/USDT", "spread_bps": 4.2, "timestamp": "2026-05-19T10:00:00"}
        ]

    def fetch_latest_exchange_comparison(self, symbol: str, limit: int = 6):
        return [dict(row, symbol=symbol) for row in self.rows[:limit]]


def test_ai_market_context_bundle_respects_ai_ready_inputs(tmp_path):
    db = DBManager(str(tmp_path / 'ai_market_context.sqlite'))
    db.init_tables()

    audit_payload = {
        "summary": {
            "world_model_status": "blocked",
            "critical_gap_band_names": ["macro", "news", "onchain", "options"],
        },
        "bands": [
            {"band_name": "macro", "is_band_ready_for_ai": False},
            {"band_name": "exchange", "is_band_ready_for_ai": True},
        ],
    }
    market_breadth_payload = {
        "breadth_status": "thin",
        "breadth_score": 0.22,
        "asset_count": 4,
        "ai_ready_asset_count": 1,
        "data_quality_flag": "thin",
        "data_quality_flags": ["configured_market_breadth_thin"],
        "quality_notes": ["当前 AI-ready 市场资产覆盖很薄。"],
    }
    asset_readiness_payload = {
        "assets": [
            {
                "asset": "BTC",
                "asset_status": "blocked",
                "readiness_score": 0.15,
                "ready_band_count": 0,
                "limited_band_count": 1,
                "missing_band_count": 7,
                "missing_band_names": ["news", "macro"],
                "limited_band_names": ["exchange"],
                "bands": {
                    "exchange": {
                        "status": "limited",
                        "weight": 0.3,
                        "weighted_score": 0.15,
                        "notes": ["exchange 只有有限证据。"],
                    },
                    "news": {
                        "status": "missing",
                        "weight": 0.15,
                        "weighted_score": 0.0,
                        "notes": ["没有 AI-ready 新闻。"],
                    },
                },
                "quality_notes": ["当前 BTC 只有有限 exchange 证据。"],
            }
        ]
    }
    exchange_payload = {
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "spot": [{"last_price": 100000.0}],
                "orderbook": [{"mid_price": 100000.0}],
                "trade_flow": [{"buy_ratio": 0.61}],
                "funding": [{"funding_rate": 0.0001}],
                "open_interest": [{"open_interest": 1000000.0}],
                "liquidations": [{"total_liquidation_notional": 250000.0}],
                "positioning": [],
                "basis": [{"basis_bps": 12.0}],
            }
        ]
    }
    news_payload = {
        "latest_articles": [
            {
                "source": "CoinDesk",
                "title": "BTC article",
                "published_at": "2026-05-19T09:00:00",
                "relevance_symbols": ["BTC"],
            },
            {
                "source": "CoinDesk",
                "title": "ETH article",
                "published_at": "2026-05-19T09:10:00",
                "relevance_symbols": ["ETH"],
            },
        ],
        "data_quality_flags": [],
    }
    event_payload = {
        "upcoming_events": [
            {
                "title": "BTC unlock",
                "symbol": "BTC",
                "scheduled_at": "2026-05-25T00:00:00",
                "source_name": "unlock_schedule",
            }
        ],
        "data_quality_flags": [],
    }
    onchain_payload = {"entity_count": 0, "entities": []}
    tokenomics_payload = {
        "entity_count": 1,
        "unlock_watchlist": [
            {"entity_key": "BTC", "scheduled_unlock_usd_7d": 123456.0}
        ],
    }
    alternative_payload = {"row_count": 0, "sources": {}}
    macro_payload = {"factor_count": 12, "factors": [{"factor_id": "dxy"}]}
    market_structure_payload = {
        "assets": [
            {
                "asset": "BTC",
                "trade_flow_context": {"net_taker_notional_sum": 1234.0},
                "funding_context": {"average_funding_rate": 0.0001},
                "basis_context": {"average_basis_bps": 12.0},
                "open_interest_context": {"total_open_interest_usd": 1000000.0},
                "liquidation_context": {"total_liquidation_notional": 250000.0},
                "positioning_context": {"row_count": 0},
                "structure_completeness_score": 0.83,
                "data_quality_flag": "partial",
            }
        ]
    }

    service = AIMarketContextService(
        db=db,
        repository=StubRepository(),
        exchange_service=StubService(exchange_payload),
        news_service=StubService(news_payload),
        event_calendar_service=StubService(event_payload),
        onchain_service=StubService(onchain_payload),
        tokenomics_service=StubService(tokenomics_payload),
        alternative_service=StubService(alternative_payload),
        macro_context_service=StubService(macro_payload),
        audit_service=StubAuditService(audit_payload),
        market_breadth_service=StubService(market_breadth_payload),
        asset_readiness_service=StubService(asset_readiness_payload),
        market_structure_service=StubService(market_structure_payload),
    )

    bundle = service.build_bundle_for_entity("BTC")

    assert bundle["coverage_score"] == 0.15
    assert bundle["data_quality_flag"] == "blocked"
    assert bundle["market_structure"]["asset"] == "BTC"
    assert bundle["market_structure"]["trade_flow_context"]["net_taker_notional_sum"] == 1234.0
    assert bundle["macro_regime"] == {}
    assert bundle["raw_macro_regime"]["factor_count"] == 12
    assert len(bundle["news_and_events"]["recent_news"]) == 1
    assert bundle["news_and_events"]["recent_news"][0]["title"] == "BTC article"
    assert len(bundle["cross_exchange_execution"]) == 1
    assert len(bundle["raw_cross_exchange_execution"]) == 1
    assert bundle["cross_exchange_execution_quality_summary"]["status"] == "ready"
    assert bundle["data_readiness"]["market_world_status"] == "blocked"
    assert bundle["data_readiness"]["asset_status"] == "blocked"
    assert bundle["data_readiness"]["cross_exchange_execution_status"] == "ready"
    assert "market_world_model_blocked" in bundle["data_quality_flags"]
    assert "asset_evidence_blocked" in bundle["data_quality_flags"]
    assert "macro_context_not_ai_ready" in bundle["data_quality_flags"]
    assert "insufficient_market_evidence" in bundle["risk_flags"]
    assert any(item["type"] == "unlock_pressure" for item in bundle["evidence"])
    assert any(item["type"] == "recent_news" for item in bundle["evidence"])
    assert any(item["type"] == "upcoming_event" for item in bundle["evidence"])
    service.close()


def test_ai_market_context_snapshots_persist_partial_quality(tmp_path):
    db = DBManager(str(tmp_path / 'ai_market_context_persist.sqlite'))
    db.init_tables()

    audit_payload = {
        "summary": {
            "world_model_status": "partial",
            "critical_gap_band_names": ["options"],
        },
        "bands": [
            {"band_name": "macro", "is_band_ready_for_ai": True},
            {"band_name": "exchange", "is_band_ready_for_ai": True},
        ],
    }
    market_breadth_payload = {
        "breadth_status": "narrow",
        "breadth_score": 0.55,
        "asset_count": 6,
        "ai_ready_asset_count": 4,
        "data_quality_flag": "partial",
        "data_quality_flags": ["configured_market_breadth_narrow"],
        "quality_notes": ["当前是窄市场视角。"],
    }
    asset_readiness_payload = {
        "assets": [
            {
                "asset": "BTC",
                "asset_status": "partial",
                "readiness_score": 0.58,
                "ready_band_count": 3,
                "limited_band_count": 1,
                "missing_band_count": 3,
                "missing_band_names": ["options"],
                "limited_band_names": ["news"],
                "bands": {},
                "quality_notes": ["BTC 当前可做有限分析。"],
            }
        ]
    }
    exchange_payload = {
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "spot": [{"last_price": 100000.0}],
                "orderbook": [{"mid_price": 100000.0}],
                "trade_flow": [{"buy_ratio": 0.61}],
                "funding": [{"funding_rate": 0.0001}],
                "open_interest": [{"open_interest": 1000000.0}],
                "liquidations": [],
                "positioning": [],
                "basis": [{"basis_bps": 12.0}],
            }
        ]
    }
    news_payload = {
        "latest_articles": [
            {
                "source": "CoinDesk",
                "title": "BTC article",
                "published_at": "2026-05-19T09:00:00",
                "relevance_symbols": ["BTC"],
            }
        ],
        "data_quality_flags": [],
    }
    event_payload = {"upcoming_events": [], "data_quality_flags": []}
    onchain_payload = {"entity_count": 1, "entities": [{"entity_key": "BTC"}]}
    tokenomics_payload = {"entity_count": 1, "unlock_watchlist": []}
    alternative_payload = {"row_count": 1, "sources": {"github": {"entities": [{"entity_key": "BTC"}]}}}
    macro_payload = {"factor_count": 8, "factors": [{"factor_id": "dxy"}]}
    market_structure_payload = {
        "assets": [
            {
                "asset": "BTC",
                "trade_flow_context": {"net_taker_notional_sum": 5000.0},
                "funding_context": {"average_funding_rate": 0.0002},
                "basis_context": {"average_basis_bps": 30.0},
                "open_interest_context": {"total_open_interest_usd": 2500000.0},
                "liquidation_context": {"total_liquidation_notional": 0.0},
                "positioning_context": {"row_count": 1},
                "structure_completeness_score": 0.92,
                "data_quality_flag": "ok",
            }
        ]
    }

    service = AIMarketContextService(
        db=db,
        exchange_service=StubService(exchange_payload),
        news_service=StubService(news_payload),
        event_calendar_service=StubService(event_payload),
        onchain_service=StubService(onchain_payload),
        tokenomics_service=StubService(tokenomics_payload),
        alternative_service=StubService(alternative_payload),
        macro_context_service=StubService(macro_payload),
        audit_service=StubAuditService(audit_payload),
        market_breadth_service=StubService(market_breadth_payload),
        asset_readiness_service=StubService(asset_readiness_payload),
        market_structure_service=StubService(market_structure_payload),
    )

    snapshots = service.build_latest_snapshots(["BTC"], persist=True)
    assert len(snapshots) == 1
    assert snapshots[0].data_quality_flag == "partial"

    bundle = service.load_latest_context_bundle(["BTC"])
    assert bundle["entity_count"] == 1
    assert bundle["entities"][0]["entity_key"] == "BTC"
    assert bundle["entities"][0]["data_quality_flag"] == "partial"
    assert bundle["entities"][0]["data_readiness"]["asset_status"] == "partial"
    assert bundle["entities"][0]["market_structure"]["data_quality_flag"] == "ok"
    service.close()


def test_ai_market_context_hides_raw_only_cross_exchange_rows_from_ai_view(tmp_path):
    db = DBManager(str(tmp_path / 'ai_market_context_cross_exchange.sqlite'))
    db.init_tables()

    audit_payload = {
        "summary": {
            "world_model_status": "partial",
            "critical_gap_band_names": ["options"],
        },
        "bands": [
            {"band_name": "macro", "is_band_ready_for_ai": True},
            {"band_name": "exchange", "is_band_ready_for_ai": True},
        ],
    }
    market_breadth_payload = {
        "breadth_status": "narrow",
        "breadth_score": 0.48,
        "asset_count": 4,
        "ai_ready_asset_count": 2,
        "data_quality_flag": "partial",
        "data_quality_flags": [],
        "quality_notes": ["当前市场广度仍然偏窄。"],
    }
    asset_readiness_payload = {
        "assets": [
            {
                "asset": "BTC",
                "asset_status": "partial",
                "readiness_score": 0.52,
                "ready_band_count": 2,
                "limited_band_count": 2,
                "missing_band_count": 2,
                "missing_band_names": ["options"],
                "limited_band_names": ["news"],
                "bands": {},
                "quality_notes": ["BTC 当前证据链仍不完整。"],
            }
        ]
    }
    exchange_payload = {
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "spot": [{"last_price": 100000.0}],
                "orderbook": [{"mid_price": 100000.0}],
                "trade_flow": [{"buy_ratio": 0.52}],
                "funding": [{"funding_rate": 0.0001}],
                "open_interest": [{"open_interest": 500000.0}],
                "liquidations": [],
                "positioning": [],
                "basis": [{"basis_bps": 10.0}],
            }
        ]
    }
    news_payload = {
        "latest_articles": [
            {
                "source": "CoinDesk",
                "title": "BTC article",
                "published_at": "2026-05-19T09:00:00",
                "relevance_symbols": ["BTC"],
            }
        ],
        "data_quality_flags": [],
    }
    event_payload = {"upcoming_events": [], "data_quality_flags": []}
    onchain_payload = {"entity_count": 1, "entities": [{"entity_key": "BTC"}]}
    tokenomics_payload = {"entity_count": 1, "unlock_watchlist": []}
    alternative_payload = {"row_count": 0, "sources": {}}
    macro_payload = {"factor_count": 6, "factors": [{"factor_id": "dxy"}]}
    market_structure_payload = {
        "assets": [
            {
                "asset": "BTC",
                "trade_flow_context": {"net_taker_notional_sum": 1000.0},
                "funding_context": {"average_funding_rate": 0.0001},
                "basis_context": {"average_basis_bps": 10.0},
                "open_interest_context": {"total_open_interest_usd": 500000.0},
                "liquidation_context": {"total_liquidation_notional": 0.0},
                "positioning_context": {"row_count": 0},
                "structure_completeness_score": 0.67,
                "data_quality_flag": "partial",
            }
        ]
    }
    repository = StubRepository(
        rows=[
            {
                "exchange_a": "binance",
                "exchange_b": "okx",
                "signal_label": "data_quality_warning",
                "is_actionable": False,
                "data_quality_flag": "stale_orderbook_a|cross_exchange_orderbook_gap",
                "timestamp": "2026-05-19T10:00:00",
            }
        ]
    )

    service = AIMarketContextService(
        db=db,
        repository=repository,
        exchange_service=StubService(exchange_payload),
        news_service=StubService(news_payload),
        event_calendar_service=StubService(event_payload),
        onchain_service=StubService(onchain_payload),
        tokenomics_service=StubService(tokenomics_payload),
        alternative_service=StubService(alternative_payload),
        macro_context_service=StubService(macro_payload),
        audit_service=StubAuditService(audit_payload),
        market_breadth_service=StubService(market_breadth_payload),
        asset_readiness_service=StubService(asset_readiness_payload),
        market_structure_service=StubService(market_structure_payload),
    )

    bundle = service.build_bundle_for_entity("BTC")

    assert bundle["cross_exchange_execution"] == []
    assert len(bundle["raw_cross_exchange_execution"]) == 1
    assert bundle["cross_exchange_execution_quality_summary"]["status"] == "raw_only"
    assert bundle["cross_exchange_execution_quality_summary"]["raw_only_due_to_quality_issues"] is True
    assert bundle["data_readiness"]["cross_exchange_execution_status"] == "raw_only"
    assert "cross_exchange_execution_not_ai_ready" in bundle["data_quality_flags"]
    assert any(
        "跨交易所执行上下文存在真实原始快照" in note
        for note in bundle["quality_notes"]
    )
    service.close()
