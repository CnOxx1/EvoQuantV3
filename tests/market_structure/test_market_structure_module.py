import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from logic_layer.market_structure.service import MarketStructureService


class StubExchangeService:
    def __init__(self, payload):
        self.payload = payload

    def load_latest_market_context_bundle(self, *args, **kwargs):
        return self.payload


def test_market_structure_bundle_rebuilds_real_exchange_context(tmp_path):
    db = DBManager(str(tmp_path / "market_structure.sqlite"))
    db.init_tables()

    exchange_payload = {
        "as_of": "2026-05-19T10:00:00",
        "symbol_count": 1,
        "row_count": 12,
        "raw_row_count": 15,
        "configured_universe_summary": {
            "scope_kind": "filtered",
            "tracked_symbols": ["BTC/USDT"],
        },
        "source_health_summary": {
            "source_count": 8,
            "ready_for_ai_source_count": 6,
            "not_ready_for_ai_source_count": 2,
        },
        "ai_ready_source_names": [
            "ticker",
            "funding",
            "trade_flow",
            "open_interest",
            "basis",
            "orderbook",
        ],
        "ai_excluded_source_names": ["liquidations", "long_short_ratio"],
        "symbols": [
            {
                "symbol": "BTC/USDT",
                "trade_flow_scope": "mixed",
                "spot": [
                    {"exchange": "binance", "last_price": 100000.0},
                    {"exchange": "okx", "last_price": 100050.0},
                ],
                "orderbook": [
                    {"exchange": "binance", "mid_price": 100010.0},
                    {"exchange": "okx", "mid_price": 100040.0},
                ],
                "trade_flow_spot": [
                    {
                        "exchange": "binance",
                        "buy_notional": 60000.0,
                        "sell_notional": 40000.0,
                        "aggressive_buy_notional": 55000.0,
                        "aggressive_sell_notional": 35000.0,
                        "net_taker_notional": 20000.0,
                        "cvd": 20000.0,
                    }
                ],
                "trade_flow_derivatives": [
                    {
                        "exchange": "okx",
                        "buy_notional": 50000.0,
                        "sell_notional": 70000.0,
                        "aggressive_buy_notional": 45000.0,
                        "aggressive_sell_notional": 65000.0,
                        "net_taker_notional": -20000.0,
                        "cvd": -20000.0,
                    }
                ],
                "funding": [
                    {"exchange": "binance", "funding_rate": 0.0001, "mark_price": 100100.0},
                    {"exchange": "okx", "funding_rate": -0.0002, "mark_price": 100300.0},
                ],
                "open_interest": [
                    {
                        "exchange": "binance",
                        "open_interest_usd": 1200000.0,
                        "open_interest_contracts": 1500.0,
                        "open_interest_change_5m": 10000.0,
                        "open_interest_change_1h": 40000.0,
                        "open_interest_change_24h": 100000.0,
                    },
                    {
                        "exchange": "okx",
                        "open_interest_usd": 800000.0,
                        "open_interest_contracts": 900.0,
                        "open_interest_change_5m": -5000.0,
                        "open_interest_change_1h": 20000.0,
                        "open_interest_change_24h": 70000.0,
                    },
                ],
                "liquidations": [],
                "positioning": [],
                "basis": [
                    {
                        "exchange": "binance",
                        "basis_bps": 15.0,
                        "annualized_basis_bps": 1200.0,
                        "spot_price": 100000.0,
                    },
                    {
                        "exchange": "okx",
                        "basis_bps": 45.0,
                        "annualized_basis_bps": 3600.0,
                        "spot_price": 100020.0,
                    },
                ],
                "cross_exchange_diagnostics": {
                    "spot_last_price_range_bps": 5.0,
                    "funding_mark_price_range_bps": 20.0,
                    "basis_range_bps": 30.0,
                    "max_section_timestamp_spread_seconds": 4.0,
                },
                "coverage_summary": {
                    "complete_sections": [
                        "spot",
                        "orderbook",
                        "funding",
                        "trade_flow",
                        "open_interest",
                        "basis",
                    ],
                    "partial_sections": [],
                    "missing_sections": ["liquidations", "long_short_ratio"],
                    "stale_sections": [],
                },
                "source_counts": {
                    "ticker": 2,
                    "trade_flow": 2,
                    "funding": 2,
                    "open_interest": 2,
                    "basis": 2,
                },
                "raw_source_counts": {
                    "ticker": 2,
                    "trade_flow": 2,
                    "funding": 2,
                    "open_interest": 2,
                    "basis": 2,
                },
                "data_quality_flags": [],
                "quality_notes": [],
                "ai_ready_source_names": [
                    "ticker",
                    "trade_flow",
                    "funding",
                    "open_interest",
                    "basis",
                ],
                "ai_excluded_source_names": ["liquidations", "long_short_ratio"],
            }
        ],
    }

    service = MarketStructureService(
        db=db,
        exchange_service=StubExchangeService(exchange_payload),
    )
    bundle = service.build_latest_context_bundle(asset_keys=["BTC"])

    assert bundle["asset_count"] == 1
    assert bundle["data_quality_flag"] == "partial"
    asset = bundle["assets"][0]
    assert asset["asset"] == "BTC"
    assert asset["trade_flow_context"]["row_count"] == 2
    assert asset["trade_flow_context"]["net_taker_notional_sum"] == 0.0
    assert asset["funding_context"]["positive_count"] == 1
    assert asset["funding_context"]["negative_count"] == 1
    assert asset["basis_context"]["average_basis_bps"] == 30.0
    assert asset["open_interest_context"]["total_open_interest_usd"] == 2000000.0
    assert asset["liquidation_context"]["row_count"] == 0
    assert asset["positioning_context"]["row_count"] == 0
    assert asset["structure_completeness_score"] == 1.0
    assert asset["ai_visible_coverage_summary"]["visible_core_sections"] == [
        "spot",
        "orderbook",
        "funding",
        "trade_flow",
        "open_interest",
        "basis",
    ]
    assert "market_structure_liquidations_missing" in asset["data_quality_flags"]
    assert "market_structure_positioning_missing" in asset["data_quality_flags"]

    snapshot = service.save_snapshot(bundle)
    row = db.fetch_one(
        """
        SELECT asset_count, data_quality_flag
        FROM market_structure_snapshots
        WHERE id = ?
        """,
        (snapshot["id"],),
    )

    assert row["asset_count"] == 1
    assert row["data_quality_flag"] == "partial"
    service.close()


def test_market_structure_completeness_only_counts_ai_visible_sections(tmp_path):
    db = DBManager(str(tmp_path / "market_structure_visible.sqlite"))
    db.init_tables()

    exchange_payload = {
        "as_of": "2026-05-19T10:00:00",
        "symbols": [
            {
                "symbol": "BTC/USDT",
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
                "cross_exchange_diagnostics": {},
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
                    "missing_sections": [],
                    "stale_sections": [
                        "spot",
                        "orderbook",
                        "funding",
                        "trade_flow_spot",
                        "trade_flow_derivatives",
                        "open_interest",
                        "basis",
                    ],
                },
                "source_counts": {},
                "raw_source_counts": {
                    "ticker": 2,
                    "orderbook": 2,
                    "funding": 2,
                    "trade_flow": 2,
                    "open_interest": 2,
                    "basis": 2,
                },
                "data_quality_flags": ["stale_subsection_present"],
                "quality_notes": ["这些结构仍有真实 raw 快照，但它们都已经 stale。"],
                "ai_ready_source_names": [],
                "ai_excluded_source_names": [
                    "ticker",
                    "orderbook",
                    "funding",
                    "trade_flow",
                    "open_interest",
                    "basis",
                ],
            }
        ],
    }

    service = MarketStructureService(
        db=db,
        exchange_service=StubExchangeService(exchange_payload),
    )
    bundle = service.build_latest_context_bundle(asset_keys=["BTC"])

    asset = bundle["assets"][0]
    assert asset["structure_completeness_score"] == 0.0
    assert asset["data_quality_flag"] == "thin"
    assert asset["ai_visible_coverage_summary"]["visible_core_sections"] == []
    assert asset["ai_visible_coverage_summary"]["raw_present_missing_core_sections"] == [
        "spot",
        "orderbook",
        "funding",
        "trade_flow",
        "open_interest",
        "basis",
    ]
    assert "market_structure_core_section_missing" in asset["data_quality_flags"]
    assert any("没有进入 AI 主视图" in note for note in asset["quality_notes"])
    service.close()
