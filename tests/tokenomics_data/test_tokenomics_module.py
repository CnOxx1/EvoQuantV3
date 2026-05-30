import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.tokenomics_data.service import TokenomicsDataService
from data_layer.tokenomics_data import sources as tokenomics_sources


class StaticTokenomicsClient:
    def fetch_points(self, source, entity_keys=None, interval=None, lookback_hours=None):
        payload = {
            "circulating_supply": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "ok",
                    "circulating_supply": 19_700_000.0,
                    "float_supply": 16_200_000.0,
                    "inflation_rate_annualized": 1.2,
                    "unit_map": {
                        "circulating_supply": "tokens",
                        "float_supply": "tokens",
                        "inflation_rate_annualized": "percent",
                    },
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
            ],
            "unlock_schedule": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "partial",
                    "scheduled_unlock_usd_7d": 0.0,
                    "scheduled_unlock_pct_float_7d": 0.0,
                    "scheduled_unlock_usd_30d": 0.0,
                    "unit_map": {
                        "scheduled_unlock_usd_7d": "usd",
                        "scheduled_unlock_pct_float_7d": "percent",
                        "scheduled_unlock_usd_30d": "usd",
                    },
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
            ],
            "unlock_realization": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "fallback",
                    "realized_unlock_usd_24h": 0.0,
                    "unit": "usd",
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
            ],
            "treasury_wallet_flow": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "ok",
                    "treasury_wallet_inflow": 100_000.0,
                    "treasury_wallet_outflow": 50_000.0,
                    "foundation_wallet_netflow": 50_000.0,
                    "unit_map": {
                        "treasury_wallet_inflow": "usd",
                        "treasury_wallet_outflow": "usd",
                        "foundation_wallet_netflow": "usd",
                    },
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
            ],
            "staking_ratio": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "ok",
                    "staking_ratio": 0.12,
                    "staking_ratio_change_7d": 0.01,
                    "unit_map": {
                        "staking_ratio": "ratio",
                        "staking_ratio_change_7d": "ratio",
                    },
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
                {
                    "entity_key": "ETH",
                    "observation_time": "2026-05-08T00:00:00+00:00",
                    "interval": interval or "1d",
                    "quality_flag": "ok",
                    "staking_ratio": 0.22,
                    "staking_ratio_change_7d": 0.02,
                    "unit_map": {
                        "staking_ratio": "ratio",
                        "staking_ratio_change_7d": "ratio",
                    },
                    "dimensions_json": {},
                    "raw_payload_json": "{\"source\":\"static\"}",
                },
            ],
        }
        rows = []
        requested = {item.strip().upper() for item in (entity_keys or []) if item.strip()}
        for row in payload.get(source.source_name, []):
            entity_key = str(row["entity_key"]).upper()
            if requested and entity_key not in requested:
                continue
            rows.append(dict(row))
        return rows

    def fetch_events(self, source, entity_keys=None, interval=None, lookback_hours=None):
        requested = {item.strip().upper() for item in (entity_keys or []) if item.strip()}
        events = [
            {
                "asset": "BTC",
                "event_type": "unlock",
                "scheduled_at": "2026-05-15T00:00:00+00:00",
                "unlock_amount": 1000.0,
                "unlock_value_usd": 100_000_000.0,
                "unlock_pct_float": 0.001,
                "beneficiary_group": "team",
                "status": "scheduled",
                "source_url": "https://example.test/unlock",
                "raw_payload_json": "{\"source\":\"static\"}",
            }
        ]
        if requested and "BTC" not in requested:
            return []
        return events


def _configured_tokenomics_sources(
    source_names: list[str] | None = None,
    enabled_only: bool = True,
):
    normalized_source_names = {
        value.strip().lower()
        for value in (source_names or [])
        if value.strip()
    }
    selected = []
    for source in tokenomics_sources.DEFAULT_TOKENOMICS_SOURCES:
        if normalized_source_names and source.source_name not in normalized_source_names:
            continue
        selected.append(
            source.model_copy(
                update={
                    "enabled": True,
                    "endpoint": f"https://mock.local/{source.source_name}",
                }
            )
        )
    return selected


def test_collect_once_records_collection_runs_and_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_coverage.sqlite")),
    )
    service.init_storage()

    summary = service.collect_once(interval="1d", lookback_hours=72)
    coverage = service.load_source_coverage(entity_keys=["BTC"])
    coverage_map = {row["source_name"]: row for row in coverage["sources"]}
    run_count = service.db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM collection_runs
        WHERE module_name = 'tokenomics_data'
        """
    )["count"]

    assert summary["total_points"] == 14
    assert summary["total_events"] == 1
    assert run_count == 5
    assert coverage["source_count"] == 5
    assert coverage["ready_source_count"] == 5
    assert coverage["ready_for_ai_source_count"] == 2
    assert coverage["not_ready_for_ai_source_count"] == 3
    assert coverage_map["circulating_supply"]["latest_ok_point_count"] == 3
    assert coverage_map["circulating_supply"]["is_ready_for_ai"] is True
    assert coverage_map["unlock_schedule"]["latest_partial_point_count"] == 3
    assert coverage_map["unlock_realization"]["latest_fallback_point_count"] == 1
    assert coverage_map["unlock_realization"]["latest_quality_ready_ratio"] == 0.0
    assert coverage_map["unlock_realization"]["is_ready_for_ai"] is False
    assert coverage_map["staking_ratio"]["latest_ok_point_count"] == 2
    assert coverage_map["staking_ratio"]["is_ready_for_ai"] is True
    assert coverage_map["treasury_wallet_flow"]["latest_ok_point_count"] == 3
    assert coverage_map["treasury_wallet_flow"]["is_ready_for_ai"] is False
    assert coverage_map["treasury_wallet_flow"]["registry_required"] is True
    assert coverage_map["treasury_wallet_flow"]["registry_ready"] is False
    assert "registry_not_ai_ready" in coverage_map["treasury_wallet_flow"]["data_quality_flags"]

    service.close()


def test_tokenomics_coverage_respects_factor_and_entity_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_filtered_coverage.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1d", lookback_hours=72)

    coverage = service.load_source_coverage(
        factor_ids=["staking_ratio"],
        entity_keys=["BTC"],
    )

    assert coverage["source_count"] == 1
    row = coverage["sources"][0]
    assert row["source_name"] == "staking_ratio"
    assert row["expected_factor_count"] == 1
    assert row["latest_factor_count"] == 1
    assert row["expected_entity_count"] == 1
    assert row["latest_entity_count"] == 1
    assert row["latest_point_count"] == 1
    assert row["latest_ok_point_count"] == 1
    assert row["latest_quality_ready_ratio"] == 1.0
    assert row["is_ready_for_ai"] is True

    service.close()


def test_load_latest_context_bundle_exposes_quality_semantics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    monkeypatch.setattr(
        TokenomicsDataService,
        "_utc_now_naive",
        staticmethod(lambda: datetime(2026, 5, 10, 0, 0, 0)),
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_bundle.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1d", lookback_hours=72)

    bundle = service.load_latest_context_bundle()
    assert bundle["row_count"] == 0
    assert bundle["raw_row_count"] == 14
    assert bundle["entity_count"] == 0
    assert bundle["raw_entity_count"] == 2
    assert bundle["source_counts"] == {}
    assert bundle["raw_source_counts"] == {
        "circulating_supply": 3,
        "treasury_wallet_flow": 3,
        "unlock_realization": 1,
        "unlock_schedule": 3,
        "staking_ratio": 4,
    }
    assert bundle["ai_ready_source_names"] == []
    assert bundle["ai_excluded_source_names"] == [
        "circulating_supply",
        "staking_ratio",
        "treasury_wallet_flow",
        "unlock_realization",
        "unlock_schedule",
    ]
    excluded_map = {
        item["source_name"]: item
        for item in bundle["ai_excluded_sources"]
    }
    assert excluded_map["circulating_supply"]["excluded_reason"] == "source_not_ready_for_ai"
    assert excluded_map["circulating_supply"]["raw_row_count"] == 3
    assert excluded_map["staking_ratio"]["excluded_reason"] == "source_not_ready_for_ai"
    assert excluded_map["staking_ratio"]["raw_row_count"] == 4
    assert excluded_map["unlock_realization"]["excluded_reason"] == "source_not_ready_for_ai"
    assert excluded_map["unlock_realization"]["raw_row_count"] == 1
    assert excluded_map["unlock_schedule"]["excluded_reason"] == "source_not_ready_for_ai"
    assert excluded_map["unlock_schedule"]["raw_row_count"] == 3
    assert excluded_map["treasury_wallet_flow"]["excluded_reason"] == "registry_not_ai_ready"
    assert excluded_map["treasury_wallet_flow"]["raw_row_count"] == 3
    assert excluded_map["treasury_wallet_flow"]["registry_required"] is True
    assert excluded_map["treasury_wallet_flow"]["registry_ready"] is False
    assert bundle["configured_universe_summary"] == {
        "scope_kind": "default",
        "tracked_entity_keys": ["ADA", "APT", "ARB", "ATOM", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "NEAR", "OP", "POL", "SOL", "SUI", "TIA", "UNI", "XRP"],
        "asset_entity_count": 18,
        "minimum_asset_entity_count_for_market_breadth": 6,
        "breadth_status": "sufficient",
        "is_market_breadth_sufficient": True,
    }
    assert bundle["coverage_summary"]["expected_entity_count"] == 18
    assert bundle["coverage_summary"]["observed_entity_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_entity_count"] == 2
    assert bundle["coverage_summary"]["expected_factor_count"] == 12
    assert bundle["coverage_summary"]["observed_factor_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_factor_count"] == 12
    assert bundle["coverage_summary"]["expected_point_count"] == 216
    assert bundle["coverage_summary"]["observed_point_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_point_count"] == 14
    assert bundle["coverage_summary"]["missing_entity_keys"] == ["ADA", "APT", "ARB", "ATOM", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "NEAR", "OP", "POL", "SOL", "SUI", "TIA", "UNI", "XRP"]
    assert bundle["coverage_summary"]["missing_factor_ids"] == [
        "circulating_supply",
        "float_supply",
        "inflation_rate_annualized",
        "scheduled_unlock_usd_7d",
        "scheduled_unlock_pct_float_7d",
        "scheduled_unlock_usd_30d",
        "realized_unlock_usd_24h",
        "treasury_wallet_inflow",
        "treasury_wallet_outflow",
        "foundation_wallet_netflow",
        "staking_ratio",
        "staking_ratio_change_7d",
    ]
    assert bundle["coverage_summary"]["ai_excluded_source_names"] == [
        "circulating_supply",
        "staking_ratio",
        "treasury_wallet_flow",
        "unlock_realization",
        "unlock_schedule",
    ]
    assert bundle["coverage_summary"]["coverage_by_source"] == [
        {
            "source_name": "circulating_supply",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "registry_required": False,
            "registry_ready": True,
            "registry_record_count": 18,
            "registry_ready_entity_count": 18,
            "registry_unready_entity_count": 0,
            "expected_entity_count": 18,
            "latest_entity_count": 1,
            "expected_factor_count": 3,
            "latest_factor_count": 3,
            "latest_point_count": 3,
            "latest_quality_ready_ratio": 1.0,
            "data_quality_flags": ["entity_coverage_incomplete"],
        },
        {
            "source_name": "staking_ratio",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "registry_required": False,
            "registry_ready": True,
            "registry_record_count": 18,
            "registry_ready_entity_count": 18,
            "registry_unready_entity_count": 0,
            "expected_entity_count": 18,
            "latest_entity_count": 2,
            "expected_factor_count": 2,
            "latest_factor_count": 2,
            "latest_point_count": 4,
            "latest_quality_ready_ratio": 1.0,
            "data_quality_flags": ["entity_coverage_incomplete"],
        },
        {
            "source_name": "treasury_wallet_flow",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "registry_required": True,
            "registry_ready": False,
            "registry_record_count": 18,
            "registry_ready_entity_count": 0,
            "registry_unready_entity_count": 18,
            "expected_entity_count": 18,
            "latest_entity_count": 1,
            "expected_factor_count": 3,
            "latest_factor_count": 3,
            "latest_point_count": 3,
            "latest_quality_ready_ratio": 1.0,
            "data_quality_flags": ["entity_coverage_incomplete", "registry_not_ai_ready"],
        },
        {
            "source_name": "unlock_realization",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "registry_required": False,
            "registry_ready": True,
            "registry_record_count": 18,
            "registry_ready_entity_count": 18,
            "registry_unready_entity_count": 0,
            "expected_entity_count": 18,
            "latest_entity_count": 1,
            "expected_factor_count": 1,
            "latest_factor_count": 1,
            "latest_point_count": 1,
            "latest_quality_ready_ratio": 0.0,
            "data_quality_flags": ["entity_coverage_incomplete", "fallback_points_present"],
        },
        {
            "source_name": "unlock_schedule",
            "health_status": "ready",
            "is_ready_for_ai": False,
            "registry_required": False,
            "registry_ready": True,
            "registry_record_count": 18,
            "registry_ready_entity_count": 18,
            "registry_unready_entity_count": 0,
            "expected_entity_count": 18,
            "latest_entity_count": 1,
            "expected_factor_count": 3,
            "latest_factor_count": 3,
            "latest_point_count": 3,
            "latest_quality_ready_ratio": 0.0,
            "data_quality_flags": ["entity_coverage_incomplete", "partial_points_present"],
        },
    ]
    assert bundle["latest_quality_flag_breakdown"] == {
        "ok": 0,
        "partial": 0,
        "fallback": 0,
        "stale": 0,
        "unknown": 0,
    }
    assert bundle["latest_quality_ready_ratio"] == 0.0
    assert bundle["raw_latest_quality_flag_breakdown"] == {
        "ok": 10,
        "partial": 3,
        "fallback": 1,
        "stale": 0,
        "unknown": 0,
    }
    assert bundle["raw_latest_quality_ready_ratio"] == 10 / 14
    assert bundle["source_health_summary"]["ready_source_count"] == 5
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
    assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 5
    assert bundle["upcoming_unlock_event_count"] == 0
    assert bundle["raw_upcoming_unlock_event_count"] == 1
    assert bundle["unlock_event_source_counts"] == {}
    assert bundle["raw_unlock_event_source_counts"] == {"unlock_schedule": 1}
    assert bundle["unlock_horizon_summary"] == {
        "next_24h": {
            "event_count": 0,
            "asset_count": 0,
            "assets": [],
            "total_unlock_value_usd": 0.0,
            "max_unlock_value_usd": 0.0,
        },
        "next_7d": {
            "event_count": 0,
            "asset_count": 0,
            "assets": [],
            "total_unlock_value_usd": 0.0,
            "max_unlock_value_usd": 0.0,
        },
        "next_30d": {
            "event_count": 0,
            "asset_count": 0,
            "assets": [],
            "total_unlock_value_usd": 0.0,
            "max_unlock_value_usd": 0.0,
        },
    }
    assert bundle["raw_unlock_horizon_summary"] == {
        "next_24h": {
            "event_count": 0,
            "asset_count": 0,
            "assets": [],
            "total_unlock_value_usd": 0.0,
            "max_unlock_value_usd": 0.0,
        },
        "next_7d": {
            "event_count": 1,
            "asset_count": 1,
            "assets": ["BTC"],
            "total_unlock_value_usd": 100000000.0,
            "max_unlock_value_usd": 100000000.0,
        },
        "next_30d": {
            "event_count": 1,
            "asset_count": 1,
            "assets": ["BTC"],
            "total_unlock_value_usd": 100000000.0,
            "max_unlock_value_usd": 100000000.0,
        },
    }
    assert "tokenomics_entity_coverage_incomplete" in bundle["data_quality_flags"]
    assert "tokenomics_partial_present" not in bundle["data_quality_flags"]
    assert "tokenomics_fallback_present" not in bundle["data_quality_flags"]
    assert "tokenomics_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert "tokenomics_configured_market_breadth_limited" not in bundle["data_quality_flags"]
    assert "tokenomics_factor_coverage_incomplete" in bundle["data_quality_flags"]
    assert "circulating_supply_structure_missing_for_18_entities" in bundle["data_quality_flags"]
    assert "unlock_pressure_missing_for_18_entities" in bundle["data_quality_flags"]
    assert "realized_unlock_missing_for_18_entities" in bundle["data_quality_flags"]
    assert "treasury_flow_missing_for_18_entities" in bundle["data_quality_flags"]
    assert "treasury_wallet_registry_not_ai_ready" in bundle["data_quality_flags"]
    assert "staking_evidence_missing_for_18_entities" in bundle["data_quality_flags"]
    assert "tokenomics_cross_asset_comparison_weak" in bundle["data_quality_flags"]
    assert any(
        "供给侧横截面仍不完整" in note
        for note in bundle["quality_notes"]
    )
    assert any("当前仍有 tokenomics source" in note for note in bundle["quality_notes"])
    assert any("treasury wallet group" in note for note in bundle["quality_notes"])
    assert not any("默认资产宇宙只覆盖" in note for note in bundle["quality_notes"])
    assert any("没有任何可直接给 AI 使用的最新快照" in note for note in bundle["quality_notes"])
    assert bundle["upcoming_unlock_events"] == []
    assert bundle["unlock_watchlist"] == []
    assert bundle["entities"] == []
    source_map = {
        item["source_name"]: item
        for item in bundle["source_health"]
    }
    assert source_map["circulating_supply"]["is_ready_for_ai"] is False
    assert "entity_coverage_incomplete" in source_map["circulating_supply"]["data_quality_flags"]
    assert source_map["unlock_realization"]["is_ready_for_ai"] is False
    assert source_map["unlock_schedule"]["is_ready_for_ai"] is False
    assert source_map["treasury_wallet_flow"]["is_ready_for_ai"] is False
    assert source_map["treasury_wallet_flow"]["registry_required"] is True
    assert source_map["treasury_wallet_flow"]["registry_ready"] is False

    service.close()


def test_tokenomics_bundle_keeps_only_ai_ready_sources_for_single_entity(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    monkeypatch.setattr(
        TokenomicsDataService,
        "_utc_now_naive",
        staticmethod(lambda: datetime(2026, 5, 10, 0, 0, 0)),
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_bundle_btc_only.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1d", lookback_hours=72)

    bundle = service.load_latest_context_bundle(entity_keys=["BTC"])

    assert bundle["row_count"] == 5
    assert bundle["raw_row_count"] == 12
    assert bundle["entity_count"] == 1
    assert bundle["raw_entity_count"] == 1
    assert bundle["source_counts"] == {
        "circulating_supply": 3,
        "staking_ratio": 2,
    }
    assert bundle["raw_source_counts"] == {
        "circulating_supply": 3,
        "treasury_wallet_flow": 3,
        "unlock_realization": 1,
        "unlock_schedule": 3,
        "staking_ratio": 2,
    }
    assert bundle["ai_ready_source_names"] == [
        "circulating_supply",
        "staking_ratio",
    ]
    assert bundle["ai_excluded_source_names"] == [
        "treasury_wallet_flow",
        "unlock_realization",
        "unlock_schedule",
    ]
    assert bundle["upcoming_unlock_event_count"] == 0
    assert bundle["raw_upcoming_unlock_event_count"] == 1
    assert bundle["unlock_event_source_counts"] == {}
    assert bundle["raw_unlock_event_source_counts"] == {"unlock_schedule": 1}
    assert "tokenomics_context_empty" not in bundle["data_quality_flags"]
    assert "unlock_pressure_missing_for_1_entities" in bundle["data_quality_flags"]
    assert "realized_unlock_missing_for_1_entities" in bundle["data_quality_flags"]
    assert "treasury_flow_missing_for_1_entities" in bundle["data_quality_flags"]

    entity = bundle["entities"][0]
    assert entity["entity_key"] == "BTC"
    assert entity["source_names"] == ["circulating_supply", "staking_ratio"]
    assert entity["scheduled_unlock_usd_7d"] is None
    assert entity["realized_unlock_usd_24h"] is None
    assert entity["treasury_wallet_inflow"] is None
    assert entity["treasury_wallet_outflow"] is None
    assert entity["foundation_wallet_netflow"] is None

    service.close()


def test_tokenomics_bundle_excludes_registry_blocked_treasury_only_context(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    monkeypatch.setattr(
        TokenomicsDataService,
        "_utc_now_naive",
        staticmethod(lambda: datetime(2026, 5, 10, 0, 0, 0)),
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_bundle_treasury_only.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1d", lookback_hours=72)

    bundle = service.load_latest_context_bundle(
        factor_ids=[
            "treasury_wallet_inflow",
            "treasury_wallet_outflow",
            "foundation_wallet_netflow",
        ],
    )

    assert bundle["row_count"] == 0
    assert bundle["raw_row_count"] == 3
    assert bundle["entity_count"] == 0
    assert bundle["raw_entity_count"] == 1
    assert bundle["source_counts"] == {}
    assert bundle["raw_source_counts"] == {"treasury_wallet_flow": 3}
    assert bundle["ai_excluded_source_names"] == ["treasury_wallet_flow"]
    assert bundle["coverage_summary"]["expected_entity_count"] == 18
    assert bundle["coverage_summary"]["observed_entity_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_entity_count"] == 1
    assert bundle["coverage_summary"]["observed_factor_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_factor_count"] == 3
    assert bundle["coverage_summary"]["observed_point_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_point_count"] == 3
    assert bundle["coverage_summary"]["missing_factor_ids"] == [
        "treasury_wallet_inflow",
        "treasury_wallet_outflow",
        "foundation_wallet_netflow",
    ]
    assert "tokenomics_context_empty" in bundle["data_quality_flags"]
    assert "tokenomics_entity_coverage_incomplete" in bundle["data_quality_flags"]
    assert "tokenomics_factor_coverage_incomplete" in bundle["data_quality_flags"]
    assert "treasury_wallet_registry_not_ai_ready" in bundle["data_quality_flags"]

    service.close()


def test_build_scheduler_registers_all_enabled_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    service = TokenomicsDataService(
        db=DBManager(str(tmp_path / "tokenomics_scheduler.sqlite"))
    )

    scheduler = service.build_scheduler(interval="1d", lookback_hours=72)

    assert isinstance(scheduler, BlockingScheduler)
    assert len(scheduler.get_jobs()) == 5
    service.close()


def test_tokenomics_bundle_treats_factor_filtered_scope_as_filtered(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.tokenomics_data.service.load_tokenomics_sources",
        _configured_tokenomics_sources,
    )
    service = TokenomicsDataService(
        client=StaticTokenomicsClient(),
        db=DBManager(str(tmp_path / "tokenomics_bundle_factor_filtered.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1d", lookback_hours=72)

    bundle = service.load_latest_context_bundle(
        factor_ids=["staking_ratio"],
    )

    assert bundle["configured_universe_summary"]["scope_kind"] == "filtered"
    assert bundle["configured_universe_summary"]["breadth_status"] == "filtered"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is None
    assert "tokenomics_configured_market_breadth_limited" not in bundle["data_quality_flags"]

    service.close()
