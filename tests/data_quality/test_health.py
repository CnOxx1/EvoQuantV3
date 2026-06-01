import sys
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.data_quality import (
    DataLayerAuditService,
    build_market_world_summary,
    is_quality_summary_ai_ready,
    resolve_evidence_band_status,
)
from data_layer.data_quality.runner import build_parser as build_data_quality_runner_parser


def test_is_quality_summary_ai_ready_accepts_clean_ok_only_snapshot():
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 4,
            "partial_count": 0,
            "fallback_count": 0,
            "stale_count": 0,
            "unknown_count": 0,
        }
    ) is True


def test_is_quality_summary_ai_ready_rejects_when_no_ok_points():
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 0,
            "partial_count": 0,
            "fallback_count": 0,
            "stale_count": 0,
            "unknown_count": 0,
        }
    ) is False


def test_is_quality_summary_ai_ready_rejects_non_ok_flags_by_default():
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 5,
            "partial_count": 1,
            "fallback_count": 0,
            "stale_count": 0,
            "unknown_count": 0,
        }
    ) is False
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 5,
            "partial_count": 0,
            "fallback_count": 1,
            "stale_count": 0,
            "unknown_count": 0,
        }
    ) is False
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 5,
            "partial_count": 0,
            "fallback_count": 0,
            "stale_count": 1,
            "unknown_count": 0,
        }
    ) is False
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 5,
            "partial_count": 0,
            "fallback_count": 0,
            "stale_count": 0,
            "unknown_count": 1,
        }
    ) is False


def test_is_quality_summary_ai_ready_can_relax_specific_flags():
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 2,
            "partial_count": 1,
            "fallback_count": 0,
            "stale_count": 0,
            "unknown_count": 0,
        },
        allow_partial=True,
    ) is True
    assert is_quality_summary_ai_ready(
        {
            "ok_count": 2,
            "partial_count": 0,
            "fallback_count": 1,
            "stale_count": 0,
            "unknown_count": 0,
        },
        allow_fallback=True,
    ) is True


def test_resolve_evidence_band_status_marks_ready_when_ai_ready_sources_and_latest_rows_exist():
    assert resolve_evidence_band_status(
        has_latest_rows=True,
        has_history_rows=True,
        ready_for_ai_source_count=1,
        minimum_ai_ready_sources=1,
    ) == "ready"


def test_resolve_evidence_band_status_marks_unconfigured_when_no_latest_rows_and_unconfigured_present():
    assert resolve_evidence_band_status(
        has_latest_rows=False,
        has_history_rows=False,
        ready_for_ai_source_count=0,
        minimum_ai_ready_sources=1,
        unconfigured_source_count=2,
    ) == "unconfigured"


def test_resolve_evidence_band_status_marks_insufficient_when_history_exists_but_ai_not_ready():
    assert resolve_evidence_band_status(
        has_latest_rows=False,
        has_history_rows=True,
        ready_for_ai_source_count=0,
        minimum_ai_ready_sources=1,
    ) == "insufficient"


def test_build_market_world_summary_marks_blocked_when_required_band_is_missing():
    summary = build_market_world_summary(
        [
            {
                "band_name": "exchange",
                "required": True,
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
            {
                "band_name": "onchain",
                "required": True,
                "band_status": "missing",
                "is_band_ready_for_ai": False,
            },
            {
                "band_name": "alternative",
                "required": False,
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
        ]
    )

    assert summary["world_model_status"] == "blocked"
    assert summary["is_market_data_ready_for_ai"] is False
    assert summary["critical_gap_band_names"] == ["onchain"]
    assert summary["blocked_band_names"] == ["onchain"]


def test_build_market_world_summary_marks_ready_when_all_required_bands_are_ai_ready():
    summary = build_market_world_summary(
        [
            {
                "band_name": "exchange",
                "required": True,
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
            {
                "band_name": "macro",
                "required": True,
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
            {
                "band_name": "news",
                "required": True,
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
        ]
    )

    assert summary["world_model_status"] == "ready"
    assert summary["is_market_data_ready_for_ai"] is True
    assert summary["critical_gap_count"] == 0


def test_data_quality_audit_snapshot_table_is_created(tmp_path):
    db = DBManager(str(tmp_path / "audit_schema.sqlite"))
    db.init_tables()

    row = db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'data_quality_audit_snapshots'
        """
    )

    assert row["count"] == 1
    db.close()


def test_ensure_columns_tolerates_duplicate_column_created_by_other_process(tmp_path, monkeypatch):
    db_path = str(tmp_path / "schema_race.sqlite")
    db = DBManager(db_path)
    db.execute("CREATE TABLE schema_race (id INTEGER PRIMARY KEY)")
    db.commit()

    competing_conn = sqlite3.connect(db_path)
    competing_conn.execute("ALTER TABLE schema_race ADD COLUMN race_col REAL")
    competing_conn.commit()
    competing_conn.close()

    original_existing_columns = db._existing_columns
    calls = {"count": 0}

    def stale_then_actual(table_name: str) -> set[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return {"id"}
        return original_existing_columns(table_name)

    monkeypatch.setattr(db, "_existing_columns", stale_then_actual)

    db._ensure_columns("schema_race", {"race_col": "REAL"})

    columns = {row["name"] for row in db.fetch_all("PRAGMA table_info(schema_race)")}
    assert "race_col" in columns
    db.close()


def test_data_layer_audit_service_can_save_market_world_snapshot(tmp_path):
    db = DBManager(str(tmp_path / "audit_save.sqlite"))
    db.init_tables()
    service = DataLayerAuditService(db=db, service_factories={})

    payload = {
        "as_of": "2026-05-18T15:30:00",
        "summary": {
            "world_model_status": "blocked",
            "is_market_data_ready_for_ai": False,
            "required_band_count": 7,
            "required_ready_band_count": 1,
            "optional_band_count": 1,
            "optional_ready_band_count": 0,
            "critical_gap_count": 3,
            "critical_gap_band_names": ["onchain", "tokenomics", "options"],
            "blocked_band_names": ["onchain", "tokenomics"],
            "partial_band_names": ["options"],
        },
        "bands": [
            {
                "band_name": "exchange",
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
            {
                "band_name": "onchain",
                "band_status": "unconfigured",
                "is_band_ready_for_ai": False,
            },
        ],
    }

    snapshot = service.save_market_world_audit_snapshot(payload)
    row = db.fetch_one(
        """
        SELECT audit_scope, world_model_status, is_market_data_ready_for_ai,
               critical_gap_count, critical_gap_band_names_json, bands_json
        FROM data_quality_audit_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert snapshot["audit_scope"] == "market_world_model"
    assert row["audit_scope"] == "market_world_model"
    assert row["world_model_status"] == "blocked"
    assert row["is_market_data_ready_for_ai"] == 0
    assert row["critical_gap_count"] == 3
    assert "onchain" in row["critical_gap_band_names_json"]
    assert "exchange" in row["bands_json"]

    service.close()


def test_data_layer_audit_service_includes_asset_readiness_summary(tmp_path, monkeypatch):
    db = DBManager(str(tmp_path / "audit_asset_readiness.sqlite"))
    db.init_tables()

    class StubCoverageService:
        def __init__(self, payload):
            self.payload = payload

        def load_source_coverage(self):
            return self.payload

        def close(self):
            return None

    class StubAssetReadinessService:
        def __init__(self, payload):
            self.payload = payload
            self.last_audit_payload = None

        def build_latest_context_bundle(self, audit_payload=None):
            self.last_audit_payload = audit_payload
            return self.payload

        def close(self):
            return None

    healthy_coverage = {
        "source_count": 1,
        "ready_source_count": 1,
        "problem_source_count": 0,
        "ready_for_ai_source_count": 1,
        "not_ready_for_ai_source_count": 0,
        "stale_source_count": 0,
        "unconfigured_source_count": 0,
        "data_quality_flags": [],
        "quality_notes": [],
    }

    asset_readiness_stub = StubAssetReadinessService(
        {
            "asset_count": 4,
            "ready_asset_count": 1,
            "partial_asset_count": 2,
            "thin_asset_count": 1,
            "blocked_asset_count": 0,
            "average_readiness_score": 0.61,
            "data_quality_flag": "partial",
            "data_quality_flags": ["no_asset_fully_ready"],
            "quality_notes": ["当前只有 1 个资产达到 ready。"],
            "top_analysis_candidate_assets": [
                {"asset": "BTC", "asset_status": "ready", "readiness_score": 0.88}
            ],
        }
    )

    service = DataLayerAuditService(
        db=db,
        service_factories={
            "exchange_data": lambda local_db: StubCoverageService(healthy_coverage),
            "macro_data": lambda local_db: StubCoverageService(healthy_coverage),
            "news_data": lambda local_db: StubCoverageService(healthy_coverage),
            "event_calendar_data": lambda local_db: StubCoverageService(healthy_coverage),
            "onchain_data": lambda local_db: StubCoverageService(healthy_coverage),
            "tokenomics_data": lambda local_db: StubCoverageService(healthy_coverage),
            "options_data": lambda local_db: StubCoverageService(healthy_coverage),
            "alternative_data": lambda local_db: StubCoverageService(healthy_coverage),
            "perpetual_dex_data": lambda local_db: StubCoverageService(healthy_coverage),
            "onchain_address_data": lambda local_db: StubCoverageService(healthy_coverage),
            "dex_liquidity_data": lambda local_db: StubCoverageService(healthy_coverage),
            "gas_network_data": lambda local_db: StubCoverageService(healthy_coverage),
            "governance_data": lambda local_db: StubCoverageService(healthy_coverage),
            "asset_readiness": lambda local_db: asset_readiness_stub,
        },
    )

    monkeypatch.setattr(service, "_safe_table_count", lambda table_name: 1)

    payload = service.load_market_world_audit()

    assert payload["summary"]["world_model_status"] == "ready"
    assert payload["asset_readiness_summary"]["asset_count"] == 4
    assert payload["asset_readiness_summary"]["ready_asset_count"] == 1
    assert payload["asset_readiness_summary"]["top_analysis_candidate_assets"][0]["asset"] == "BTC"
    assert asset_readiness_stub.last_audit_payload["summary"]["world_model_status"] == "ready"

    snapshot = service.save_market_world_audit_snapshot(payload)
    assert snapshot["world_model_status"] == "ready"
    service.close()


def test_data_layer_audit_service_run_market_world_audit_persists_run_log(tmp_path):
    db = DBManager(str(tmp_path / "audit_run.sqlite"))
    db.init_tables()
    service = DataLayerAuditService(db=db, service_factories={})

    payload = {
        "as_of": "2026-05-18T16:00:00",
        "summary": {
            "world_model_status": "partial",
            "is_market_data_ready_for_ai": False,
            "required_band_count": 7,
            "required_ready_band_count": 6,
            "optional_band_count": 1,
            "optional_ready_band_count": 0,
            "critical_gap_count": 1,
            "critical_gap_band_names": ["macro"],
            "blocked_band_names": [],
            "partial_band_names": ["macro"],
        },
        "bands": [
            {
                "band_name": "exchange",
                "band_status": "ready",
                "is_band_ready_for_ai": True,
            },
            {
                "band_name": "macro",
                "band_status": "insufficient",
                "is_band_ready_for_ai": False,
            },
        ],
    }

    service.load_market_world_audit = lambda: payload
    result = service.run_market_world_audit()
    snapshot_row = db.fetch_one(
        """
        SELECT audit_scope, world_model_status, critical_gap_count
        FROM data_quality_audit_snapshots
        ORDER BY id DESC
        LIMIT 1
        """
    )
    run_row = db.fetch_one(
        """
        SELECT module_name, source_name, job_name, status, item_count, message, metadata_json
        FROM collection_runs
        ORDER BY id DESC
        LIMIT 1
        """
    )

    assert result["snapshot"]["audit_scope"] == "market_world_model"
    assert snapshot_row["world_model_status"] == "partial"
    assert snapshot_row["critical_gap_count"] == 1
    assert run_row["module_name"] == "data_quality"
    assert run_row["source_name"] == "market_world_model"
    assert run_row["job_name"] == "market_world_audit"
    assert run_row["status"] == "success"
    assert run_row["item_count"] == 2
    assert "world_model_status=partial" in (run_row["message"] or "")
    assert '"critical_gap_count":1' in (run_row["metadata_json"] or "")

    service.close()


def test_data_layer_audit_service_build_scheduler_registers_periodic_job(tmp_path):
    db = DBManager(str(tmp_path / "audit_scheduler.sqlite"))
    db.init_tables()
    service = DataLayerAuditService(db=db, service_factories={})

    scheduler = service.build_scheduler(interval_seconds=123, audit_scope="market_world_model")
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "market_world_audit"
    assert int(jobs[0].trigger.interval.total_seconds()) == 123

    service.close()


def test_data_quality_runner_parser_defaults_to_once_mode():
    args = build_data_quality_runner_parser().parse_args([])

    assert args.mode == "once"
