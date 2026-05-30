import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.onchain_data.models import OnchainTimeSeriesPoint
from data_layer.onchain_data import sources as onchain_sources
from data_layer.onchain_data.service import OnchainDataService


class StaticOnchainClient:
    def fetch_points(self, source, entity_keys=None, interval=None, lookback_hours=None):
        payload = {
            "exchange_flow": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T10:00:00+00:00",
                    "value": -1250000.0,
                    "interval": interval or "1h",
                    "unit": "usd",
                    "dimensions_json": {"exchange_count": 4},
                }
            ],
            "whale_activity": [
                {
                    "entity_key": "BTC",
                    "observation_time": "2026-05-08T10:00:00+00:00",
                    "value": 17,
                    "interval": interval or "1h",
                    "unit": "count",
                    "dimensions_json": {"min_transfer_usd": 1000000},
                }
            ],
            "stablecoin_flow": [
                {
                    "entity_key": "USDT",
                    "observation_time": "2026-05-08T10:00:00+00:00",
                    "value": 2400000.0,
                    "interval": interval or "1h",
                    "unit": "usd",
                    "dimensions_json": {"exchange_count": 6},
                }
            ],
            "network_usage": [
                {
                    "entity_key": "BITCOIN",
                    "observation_time": "2026-05-08T10:00:00+00:00",
                    "interval": interval or "1h",
                    "active_addresses": 875000,
                    "transaction_count": 412000,
                    "fees_paid": 2350000.0,
                    "unit_map": {
                        "active_addresses": "count",
                        "transaction_count": "count",
                        "fees_paid": "usd",
                    },
                    "dimensions_json": {"window": "1h"},
                }
            ],
        }
        rows = list(payload.get(source.source_name, []))
        if entity_keys:
            requested = {entity_key.strip().upper() for entity_key in entity_keys}
            rows = [
                row
                for row in rows
                if str(row["entity_key"]).upper() in requested
            ]
        return rows


def _configured_onchain_sources(
    source_names: list[str] | None = None,
    enabled_only: bool = True,
):
    allowed_sources = {
        "exchange_flow",
        "whale_activity",
        "stablecoin_flow",
        "network_usage",
    }
    normalized_source_names = {
        value.strip().lower()
        for value in (source_names or [])
        if value.strip()
    }
    selected = []
    for source in onchain_sources.DEFAULT_ONCHAIN_SOURCES:
        if source.source_name not in allowed_sources:
            continue
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


def test_onchain_timeseries_point_normalizes_dimensions_and_timestamps():
    point = OnchainTimeSeriesPoint(
        factor_id="exchange_netflow",
        category="exchange_flow",
        factor_type="netflow",
        entity_type="asset",
        entity_key="btc",
        interval="1h",
        observation_time=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
        value=-10.5,
        unit="usd",
        dimensions_json={"exchange_count": 4},
        config_version="v1",
        source_name="exchange_flow",
        source_symbol="asset",
    )

    assert point.observation_time.tzinfo is None
    assert point.entity_key == "BTC"
    assert point.dimensions_key == "exchange_count=4"
    assert point.history_db_tuple()[11] == "{\"exchange_count\":4}"


def test_init_storage_creates_onchain_tables_and_catalog(tmp_path):
    service = OnchainDataService(db=DBManager(str(tmp_path / "onchain.sqlite")))
    service.init_storage()

    tables = {
        row["name"]
        for row in service.db.fetch_all(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'onchain_%'
            """
        )
    }
    factor_row = service.db.fetch_one(
        """
        SELECT factor_id, source_name
        FROM onchain_factor_catalog
        WHERE factor_id = 'exchange_netflow'
        """
    )

    assert {
        "onchain_factor_catalog",
        "onchain_timeseries",
    }.issubset(tables)
    assert factor_row["source_name"] == "exchange_flow"
    service.close()


def test_collect_once_writes_history_and_latest_tables(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_collect.sqlite")),
    )
    service.init_storage()

    summary = service.collect_once(interval="1h", lookback_hours=24)

    history_count = service.db.fetch_one(
        "SELECT COUNT(*) AS count FROM onchain_timeseries"
    )["count"]
    latest_count = service.db.fetch_one(
        "SELECT COUNT(*) AS count FROM latest_onchain_timeseries"
    )["count"]
    btc_row = service.db.fetch_one(
        """
        SELECT factor_id, value
        FROM latest_onchain_timeseries
        WHERE entity_key = 'BTC' AND factor_id = 'exchange_netflow'
        """
    )

    assert summary["total_points"] == 6
    assert history_count == 6
    assert latest_count == 6
    assert btc_row["value"] == -1250000.0
    bitcoin_network_row = service.db.fetch_one(
        """
        SELECT factor_id, value
        FROM latest_onchain_timeseries
        WHERE entity_key = 'BITCOIN' AND factor_id = 'active_addresses'
        """
    )
    assert bitcoin_network_row["value"] == 875000
    service.close()


def test_load_latest_context_bundle_groups_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_context.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1h", lookback_hours=24)

    bundle = service.load_latest_context_bundle()
    assert bundle["row_count"] == 0
    assert bundle["raw_row_count"] == 6
    assert bundle["entity_count"] == 0
    assert bundle["raw_entity_count"] == 3
    assert bundle["source_counts"] == {}
    assert bundle["raw_source_counts"] == {
        "network_usage": 3,
        "exchange_flow": 1,
        "stablecoin_flow": 1,
        "whale_activity": 1,
    }
    assert bundle["ai_ready_source_names"] == []
    assert bundle["ai_excluded_source_names"] == [
        "exchange_flow",
        "network_usage",
        "stablecoin_flow",
        "whale_activity",
    ]
    assert bundle["configured_universe_summary"] == {
        "scope_kind": "default",
        "entity_type_counts": {
            "asset": 18,
            "chain": 6,
            "stablecoin_asset": 3,
        },
        "entity_keys_by_type": {
            "asset": ["ADA", "APT", "ARB", "ATOM", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "NEAR", "OP", "POL", "SOL", "SUI", "TIA", "UNI", "XRP"],
            "chain": ["ARBITRUM", "BASE", "BITCOIN", "ETHEREUM", "SOLANA", "SUI"],
            "stablecoin_asset": ["FDUSD", "USDC", "USDT"],
        },
        "minimum_entity_type_counts_for_market_breadth": {
            "asset": 6,
            "chain": 8,
            "stablecoin_asset": 4,
            "protocol": 6,
        },
        "breadth_status": "limited",
        "is_market_breadth_sufficient": False,
    }
    assert bundle["coverage_summary"]["expected_entity_count"] == 27
    assert bundle["coverage_summary"]["observed_entity_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_entity_count"] == 3
    assert bundle["coverage_summary"]["expected_factor_count"] == 6
    assert bundle["coverage_summary"]["observed_factor_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_factor_count"] == 6
    assert bundle["coverage_summary"]["expected_point_count"] == 57
    assert bundle["coverage_summary"]["observed_point_count"] == 0
    assert bundle["coverage_summary"]["raw_observed_point_count"] == 6
    assert bundle["coverage_summary"]["missing_entity_count"] == 27
    assert bundle["coverage_summary"]["missing_entities"] == [
        {"entity_type": "asset", "entity_key": "ADA"},
        {"entity_type": "asset", "entity_key": "APT"},
        {"entity_type": "asset", "entity_key": "ARB"},
        {"entity_type": "asset", "entity_key": "ATOM"},
        {"entity_type": "asset", "entity_key": "AVAX"},
        {"entity_type": "asset", "entity_key": "BTC"},
        {"entity_type": "asset", "entity_key": "DOGE"},
        {"entity_type": "asset", "entity_key": "DOT"},
        {"entity_type": "asset", "entity_key": "ETH"},
        {"entity_type": "asset", "entity_key": "LINK"},
        {"entity_type": "asset", "entity_key": "NEAR"},
        {"entity_type": "asset", "entity_key": "OP"},
        {"entity_type": "asset", "entity_key": "POL"},
        {"entity_type": "asset", "entity_key": "SOL"},
        {"entity_type": "asset", "entity_key": "SUI"},
        {"entity_type": "asset", "entity_key": "TIA"},
        {"entity_type": "asset", "entity_key": "UNI"},
        {"entity_type": "asset", "entity_key": "XRP"},
        {"entity_type": "chain", "entity_key": "ARBITRUM"},
        {"entity_type": "chain", "entity_key": "BASE"},
        {"entity_type": "chain", "entity_key": "BITCOIN"},
        {"entity_type": "chain", "entity_key": "ETHEREUM"},
        {"entity_type": "chain", "entity_key": "SOLANA"},
        {"entity_type": "chain", "entity_key": "SUI"},
        {"entity_type": "stablecoin_asset", "entity_key": "FDUSD"},
        {"entity_type": "stablecoin_asset", "entity_key": "USDC"},
        {"entity_type": "stablecoin_asset", "entity_key": "USDT"},
    ]
    assert bundle["coverage_summary"]["missing_entity_keys"] == [
        "ADA",
        "APT",
        "ARB",
        "ARBITRUM",
        "ATOM",
        "AVAX",
        "BASE",
        "BITCOIN",
        "BTC",
        "DOGE",
        "DOT",
        "ETH",
        "ETHEREUM",
        "FDUSD",
        "LINK",
        "NEAR",
        "OP",
        "POL",
        "SOL",
        "SOLANA",
        "SUI",
        "TIA",
        "UNI",
        "USDC",
        "USDT",
        "XRP",
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
        "ok": 6,
        "partial": 0,
        "fallback": 0,
        "stale": 0,
        "unknown": 0,
    }
    assert bundle["raw_latest_quality_ready_ratio"] == 1.0
    assert bundle["source_health_summary"]["ready_source_count"] == 4
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
    assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 4
    assert bundle["coverage_summary"]["ready_for_ai_source_count"] == 0
    assert any(
        item["source_name"] == "exchange_flow" and item["is_ready_for_ai"] is False
        for item in bundle["coverage_summary"]["coverage_by_source"]
    )
    assert "onchain_entity_coverage_incomplete" in bundle["data_quality_flags"]
    assert "onchain_factor_coverage_incomplete" in bundle["data_quality_flags"]
    assert "onchain_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert "onchain_configured_market_breadth_limited" in bundle["data_quality_flags"]
    assert "onchain_context_empty" in bundle["data_quality_flags"]
    assert any(
        "没有任何可直接给 AI 使用的链上证据" in note
        for note in bundle["quality_notes"]
    )
    assert any(
        "默认实体宇宙仍偏向核心执行资产" in note
        for note in bundle["quality_notes"]
    )
    assert bundle["leaders"]["largest_exchange_outflow"] is None
    assert bundle["leaders"]["largest_whale_activity"] is None
    assert bundle["leaders"]["largest_stablecoin_exchange_inflow"] is None
    assert bundle["entities"] == []
    service.close()


def test_build_scheduler_registers_all_enabled_jobs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(db=DBManager(str(tmp_path / "onchain_scheduler.sqlite")))
    scheduler = service.build_scheduler(interval="1h", lookback_hours=24)

    assert isinstance(scheduler, BlockingScheduler)
    assert len(scheduler.get_jobs()) == 4
    service.close()


def test_collect_once_records_collection_runs_and_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_coverage.sqlite")),
    )
    service.init_storage()

    service.collect_once(interval="1h", lookback_hours=24)

    run_count = service.db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM collection_runs
        WHERE module_name = 'onchain_data'
        """
    )["count"]
    coverage = service.load_source_coverage()

    assert run_count == 4
    assert coverage["source_count"] == 4
    assert coverage["stale_source_count"] == 0
    assert coverage["ready_source_count"] == 4
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 4
    assert all(item["health_status"] == "ready" for item in coverage["sources"])
    assert all(item["is_ready_for_ai"] is False for item in coverage["sources"])
    assert all(item["last_run_status"] == "success" for item in coverage["sources"])
    assert all(item["latest_ok_point_count"] == item["latest_point_count"] for item in coverage["sources"])
    service.close()


def test_onchain_coverage_respects_factor_and_entity_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_filtered_coverage.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1h", lookback_hours=24)

    coverage = service.load_source_coverage(
        factor_ids=["exchange_netflow"],
        entity_keys=["BTC"],
    )

    assert coverage["source_count"] == 1
    row = coverage["sources"][0]
    assert row["source_name"] == "exchange_flow"
    assert row["expected_factor_count"] == 1
    assert row["latest_factor_count"] == 1
    assert row["expected_entity_count"] == 1
    assert row["latest_entity_count"] == 1
    assert row["expected_point_count"] == 1
    assert row["latest_point_count"] == 1
    assert row["latest_ok_point_count"] == 1
    assert row["latest_quality_ready_ratio"] == 1.0
    assert row["is_ready_for_ai"] is True
    assert coverage["ready_for_ai_source_count"] == 1
    assert coverage["not_ready_for_ai_source_count"] == 0

    service.close()


def test_onchain_source_ready_but_not_ai_ready_when_quality_is_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        db=DBManager(str(tmp_path / "onchain_fallback_quality.sqlite")),
    )
    service.init_storage()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    service.save_to_db(
        [
            OnchainTimeSeriesPoint(
                factor_id="exchange_netflow",
                category="exchange_flow",
                factor_type="netflow",
                entity_type="asset",
                entity_key="BTC",
                interval="1h",
                observation_time=now,
                value=-1250000.0,
                unit="usd",
                quality_flag="fallback",
                source_name="exchange_flow",
                source_symbol="asset",
            )
        ]
    )
    service.db.record_collection_run(
        module_name="onchain_data",
        source_name="exchange_flow",
        job_name="exchange_flow_once",
        status="success",
        item_count=1,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
        duration_seconds=0.0,
    )

    coverage = service.load_source_coverage(
        source_names=["exchange_flow"],
        factor_ids=["exchange_netflow"],
        entity_keys=["BTC"],
    )
    row = coverage["sources"][0]

    assert row["health_status"] == "ready"
    assert row["latest_ok_point_count"] == 0
    assert row["latest_fallback_point_count"] == 1
    assert row["is_ready_for_ai"] is False
    assert "fallback_points_present" in row["data_quality_flags"]
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 1
    service.close()


def test_onchain_bundle_preserves_entity_type_identity_in_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_identity.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1h", lookback_hours=24)

    bundle = service.load_latest_context_bundle()
    missing_entities = {
        (item["entity_type"], item["entity_key"])
        for item in bundle["coverage_summary"]["missing_entities"]
    }

    assert ("chain", "SUI") in missing_entities
    assert ("asset", "SUI") in missing_entities
    assert bundle["coverage_summary"]["missing_entity_count"] == 27

    service.close()


def test_onchain_bundle_treats_factor_filtered_scope_as_filtered(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "data_layer.onchain_data.service.load_onchain_sources",
        _configured_onchain_sources,
    )
    service = OnchainDataService(
        client=StaticOnchainClient(),
        db=DBManager(str(tmp_path / "onchain_bundle_factor_filtered.sqlite")),
    )
    service.init_storage()
    service.collect_once(interval="1h", lookback_hours=24)

    bundle = service.load_latest_context_bundle(
        factor_ids=["exchange_netflow"],
    )

    assert bundle["configured_universe_summary"]["scope_kind"] == "filtered"
    assert bundle["configured_universe_summary"]["breadth_status"] == "filtered"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is None
    assert "onchain_configured_market_breadth_limited" not in bundle["data_quality_flags"]

    service.close()
