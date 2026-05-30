import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from logic_layer.asset_readiness.service import AssetReadinessService


class StubService:
    def __init__(self, payload):
        self.payload = payload

    def load_latest_market_context_bundle(self):
        return self.payload

    def load_latest_context_bundle(self, *args, **kwargs):
        return self.payload

    def load_upcoming_context_bundle(self, *args, **kwargs):
        return self.payload


class StubAuditService:
    def __init__(self, payload):
        self.payload = payload

    def load_market_world_audit(self):
        return self.payload


def test_asset_readiness_bundle_surfaces_partial_real_evidence(tmp_path):
    db = DBManager(str(tmp_path / "asset_readiness.sqlite"))
    db.init_tables()

    audit_payload = {
        "summary": {
            "world_model_status": "blocked",
            "required_band_count": 7,
            "required_ready_band_count": 2,
            "critical_gap_count": 5,
            "critical_gap_band_names": [
                "macro",
                "event_calendar",
                "onchain",
                "options",
                "tokenomics",
            ],
            "blocked_band_names": ["event_calendar", "onchain", "options", "tokenomics"],
            "partial_band_names": ["macro"],
        },
        "bands": [
            {"band_name": "exchange", "band_status": "ready", "is_band_ready_for_ai": True, "ready_for_ai_source_count": 2, "blocking_reasons": []},
            {"band_name": "macro", "band_status": "insufficient", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_ai_ready_sources"]},
            {"band_name": "news", "band_status": "ready", "is_band_ready_for_ai": True, "ready_for_ai_source_count": 2, "blocking_reasons": []},
            {"band_name": "event_calendar", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "onchain", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "tokenomics", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "options", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "alternative", "band_status": "ready", "is_band_ready_for_ai": True, "ready_for_ai_source_count": 1, "blocking_reasons": []},
        ],
    }

    exchange_payload = {
        "configured_universe_summary": {"tracked_symbols": ["BTC/USDT", "ETH/USDT"]},
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "row_count": 6,
                "coverage_summary": {"complete_sections": ["spot", "orderbook"], "partial_sections": []},
                "quality_notes": ["spot 与 orderbook 已完整覆盖。"],
                "spot": [{"last_price": 100000.0}],
                "orderbook": [{"mid_price": 100000.0}],
            },
            {
                "symbol": "ETH/USDT",
                "row_count": 4,
                "coverage_summary": {"complete_sections": ["spot"], "partial_sections": ["orderbook"]},
                "quality_notes": ["ETH 当前缺少部分 orderbook 视角。"],
                "spot": [{"last_price": 5000.0}],
            },
        ],
    }
    news_payload = {
        "configured_universe_summary": {"tracked_symbols": ["BTC", "ETH", "SOL"]},
        "latest_articles": [
            {"source": "CoinDesk", "relevance_symbols": ["BTC"]},
            {"source": "The Block", "relevance_symbols": ["BTC"]},
            {"source": "CoinDesk", "relevance_symbols": ["ETH"]},
        ],
    }
    event_payload = {"symbol_watchlist": []}
    onchain_payload = {
        "configured_universe_summary": {"entity_keys_by_type": {"asset": ["BTC", "ETH"]}},
        "entities": [],
    }
    tokenomics_payload = {
        "configured_universe_summary": {"tracked_entity_keys": ["BTC", "ETH"]},
        "entities": [
            {
                "entity_key": "BTC",
                "quality_flag": "ok",
                "quality_ready_ratio": 1.0,
                "observed_factor_count": 4,
                "scheduled_unlock_usd_7d": 0.0,
                "scheduled_unlock_usd_30d": 0.0,
                "staking_ratio": None,
            }
        ],
    }
    options_payload = {
        "configured_universe_summary": {"tracked_entity_keys": ["BTC", "ETH"]},
        "assets": [],
    }
    alternative_payload = {
        "sources": {
            "google_trends": {"entities": [{"entity_key": "bitcoin"}]},
            "github": {"entities": [{"entity_key": "BTC"}, {"entity_key": "ETH"}]},
            "stablecoin": {"assets": []},
        }
    }

    service = AssetReadinessService(
        db=db,
        exchange_service=StubService(exchange_payload),
        news_service=StubService(news_payload),
        event_calendar_service=StubService(event_payload),
        onchain_service=StubService(onchain_payload),
        tokenomics_service=StubService(tokenomics_payload),
        options_service=StubService(options_payload),
        alternative_service=StubService(alternative_payload),
        audit_service=StubAuditService(audit_payload),
    )

    bundle = service.build_latest_context_bundle()

    assert bundle["market_world_status"] == "blocked"
    assert bundle["asset_count"] >= 2
    assert bundle["partial_asset_count"] >= 1
    assert bundle["data_quality_flag"] == "partial"

    btc = next(item for item in bundle["assets"] if item["asset"] == "BTC")
    eth = next(item for item in bundle["assets"] if item["asset"] == "ETH")

    assert btc["asset_status"] == "partial"
    assert btc["bands"]["exchange"]["status"] == "ready"
    assert btc["bands"]["news"]["status"] == "ready"
    assert btc["bands"]["tokenomics"]["status"] == "ready"
    assert btc["bands"]["macro"]["status"] == "shared_missing"
    assert "event_calendar" in btc["missing_band_names"]

    assert eth["bands"]["news"]["status"] == "limited"
    assert eth["bands"]["options"]["status"] in {"missing", "untracked"}

    snapshot = service.save_snapshot(bundle)
    row = db.fetch_one(
        """
        SELECT market_world_status, asset_count, partial_asset_count, data_quality_flag
        FROM asset_readiness_snapshots
        WHERE id = ?
        """,
        (snapshot["id"],),
    )

    assert row["market_world_status"] == "blocked"
    assert row["partial_asset_count"] >= 1
    assert row["data_quality_flag"] == "partial"
    service.close()


def test_asset_readiness_exchange_band_does_not_credit_raw_only_sections(tmp_path):
    db = DBManager(str(tmp_path / "asset_readiness_raw_exchange.sqlite"))
    db.init_tables()

    audit_payload = {
        "summary": {
            "world_model_status": "blocked",
            "required_band_count": 7,
            "required_ready_band_count": 1,
            "critical_gap_count": 6,
            "critical_gap_band_names": [
                "macro",
                "news",
                "event_calendar",
                "onchain",
                "tokenomics",
                "options",
            ],
            "blocked_band_names": [
                "event_calendar",
                "onchain",
                "tokenomics",
                "options",
            ],
            "partial_band_names": [],
        },
        "bands": [
            {"band_name": "exchange", "band_status": "ready", "is_band_ready_for_ai": True, "ready_for_ai_source_count": 2, "blocking_reasons": []},
            {"band_name": "macro", "band_status": "stale", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_ai_ready_sources"]},
            {"band_name": "news", "band_status": "stale", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_ai_ready_sources"]},
            {"band_name": "event_calendar", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "onchain", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "tokenomics", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "options", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
            {"band_name": "alternative", "band_status": "missing", "is_band_ready_for_ai": False, "ready_for_ai_source_count": 0, "blocking_reasons": ["no_latest_rows"]},
        ],
    }

    exchange_payload = {
        "configured_universe_summary": {"tracked_symbols": ["BTC/USDT"]},
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "row_count": 0,
                "raw_row_count": 12,
                "coverage_summary": {
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
                "quality_notes": ["这些交易所结构虽然存在 raw 快照，但已经被上游从 AI 主视图剥离。"],
                "spot": [],
                "orderbook": [],
                "funding": [],
                "trade_flow": [],
                "open_interest": [],
                "basis": [],
            }
        ],
    }

    service = AssetReadinessService(
        db=db,
        exchange_service=StubService(exchange_payload),
        news_service=StubService({"configured_universe_summary": {"tracked_symbols": ["BTC"]}, "latest_articles": []}),
        event_calendar_service=StubService({"symbol_watchlist": []}),
        onchain_service=StubService({"configured_universe_summary": {"entity_keys_by_type": {"asset": ["BTC"]}}, "entities": []}),
        tokenomics_service=StubService({"configured_universe_summary": {"tracked_entity_keys": ["BTC"]}, "entities": []}),
        options_service=StubService({"configured_universe_summary": {"tracked_entity_keys": ["BTC"]}, "assets": []}),
        alternative_service=StubService({"sources": {}}),
        audit_service=StubAuditService(audit_payload),
    )

    bundle = service.build_latest_context_bundle(asset_keys=["BTC"])
    btc = bundle["assets"][0]

    assert btc["readiness_score"] == 0.0
    assert btc["asset_status"] == "blocked"
    assert btc["bands"]["exchange"]["status"] == "missing"
    assert btc["bands"]["exchange"]["details"]["visible_sections"] == []
    assert any("没有任何 AI-ready section 进入主视图" in note for note in btc["bands"]["exchange"]["notes"])
    service.close()
