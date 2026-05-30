import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.event_calendar_data.models import EventCalendarEvent
from data_layer.event_calendar_data.models import EventCalendarSource
from data_layer.event_calendar_data.service import EventCalendarDataService


class SequenceEventClient:
    def __init__(self, payloads_by_source: dict[str, list[list[dict]]]):
        self.payloads_by_source = {
            key: list(value)
            for key, value in payloads_by_source.items()
        }

    def fetch_events(self, source, lookahead_days=None):
        payloads = self.payloads_by_source.get(source.name, [])
        if not payloads:
            return []
        return list(payloads.pop(0))


def test_event_calendar_init_storage_creates_table(tmp_path):
    service = EventCalendarDataService(db=DBManager(str(tmp_path / "calendar.sqlite")))
    service.init_storage()

    tables = {
        row["name"]
        for row in service.db.fetch_all(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'event_calendar_events'
            """
        )
    }

    assert tables == {"event_calendar_events"}
    service.close()


def test_event_calendar_collect_once_upserts_status_and_title(tmp_path, monkeypatch):
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=3)
    configured_source = EventCalendarSource(
        name="Macro Calendar API",
        event_type="macro",
        endpoint="https://calendar.example/api/macro",
        tags=["macro", "calendar"],
    )

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        lambda *args, **kwargs: [configured_source],
    )

    client = SequenceEventClient(
        {
            "Macro Calendar API": [
                [
                    {
                        "external_id": "fomc-2026-06",
                        "title": "FOMC Rate Decision",
                        "scheduled_at": scheduled_at.isoformat(),
                        "symbol": "MARKET",
                        "status": "scheduled",
                        "importance_score": 0.9,
                    }
                ],
                [
                    {
                        "external_id": "fomc-2026-06",
                        "title": "FOMC Rate Decision Updated",
                        "scheduled_at": scheduled_at.isoformat(),
                        "symbol": "MARKET",
                        "status": "updated",
                        "importance_score": 0.95,
                    }
                ],
            ]
        }
    )
    service = EventCalendarDataService(
        client=client,
        db=DBManager(str(tmp_path / "calendar_upsert.sqlite")),
    )
    service.init_storage()

    first = service.collect_once(source_names=["Macro Calendar API"])
    second = service.collect_once(source_names=["Macro Calendar API"])

    row = service.db.fetch_one(
        """
        SELECT COUNT(*) AS count, title, status, importance_score
        FROM event_calendar_events
        WHERE external_id = ?
        """,
        ("fomc-2026-06",),
    )

    assert first == {"event_count": 1}
    assert second == {"event_count": 1}
    assert row["count"] == 1
    assert row["title"] == "FOMC Rate Decision Updated"
    assert row["status"] == "updated"
    assert row["importance_score"] == 0.95
    service.close()


def test_load_upcoming_events_filters_out_past_items(tmp_path):
    db = DBManager(str(tmp_path / "calendar_query.sqlite"))
    service = EventCalendarDataService(db=db)
    service.init_storage()

    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="Past CPI",
                symbol="MARKET",
                scheduled_at=datetime.now(timezone.utc) - timedelta(days=2),
                source_name="Macro Calendar API",
            ),
            EventCalendarEvent(
                event_type="etf",
                title="Future ETF Deadline",
                symbol="BTC",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=5),
                source_name="ETF Calendar API",
            ),
        ]
    )

    rows = service.load_upcoming_events(horizon_days=30, statuses=["scheduled"])

    assert [row["title"] for row in rows] == ["Future ETF Deadline"]
    service.close()


def test_event_calendar_scheduler_job_uses_fresh_db_connection_per_thread(tmp_path, monkeypatch):
    db_path = str(tmp_path / "calendar_scheduler.sqlite")
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)
    configured_source = EventCalendarSource(
        name="Macro Calendar API",
        event_type="macro",
        endpoint="https://calendar.example/api/macro",
        tags=["macro", "calendar"],
    )

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        lambda *args, **kwargs: [configured_source],
    )

    service = EventCalendarDataService(
        client=SequenceEventClient(
            {
                "Macro Calendar API": [[
                    {
                        "external_id": "cpi-1",
                        "title": "US CPI",
                        "scheduled_at": scheduled_at.isoformat(),
                        "symbol": "MARKET",
                    }
                ]]
            }
        ),
        db=DBManager(db_path),
    )
    service.init_storage()

    errors: list[str] = []

    def worker():
        try:
            service._run_scheduled_collect(source_names=["Macro Calendar API"])
        except Exception as exc:  # pragma: no cover - explicit failure capture
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []

    verify_db = DBManager(db_path)
    row = verify_db.fetch_one(
        "SELECT COUNT(*) AS count FROM event_calendar_events WHERE external_id = ?",
        ("cpi-1",),
    )
    run_row = verify_db.fetch_one(
        """
        SELECT status, item_count
        FROM collection_runs
        WHERE module_name = 'event_calendar_data' AND source_name = 'Macro Calendar API'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    assert row["count"] == 1
    assert run_row["status"] == "success"
    assert run_row["item_count"] == 1
    verify_db.close()
    service.close()


def test_event_calendar_collect_records_run_and_coverage(tmp_path, monkeypatch):
    configured_source = EventCalendarSource(
        name="Macro Calendar API",
        event_type="macro",
        endpoint="https://calendar.example/api/macro",
        tags=["macro", "calendar"],
    )

    def fake_loader(*args, **kwargs):
        return [configured_source]

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        "data_layer.event_calendar_data.collector.load_event_calendar_sources",
        fake_loader,
    )

    scheduled_at = datetime.now(timezone.utc) + timedelta(days=2)
    service = EventCalendarDataService(
        client=SequenceEventClient(
            {
                "Macro Calendar API": [[
                    {
                        "external_id": "nfp-1",
                        "title": "US NFP",
                        "scheduled_at": scheduled_at.isoformat(),
                        "symbol": "MARKET",
                    }
                ]]
            }
        ),
        db=DBManager(str(tmp_path / "calendar_coverage.sqlite")),
    )
    service.init_storage()

    service.collect_once(source_names=["Macro Calendar API"])

    run_row = service.db.fetch_one(
        """
        SELECT status, item_count
        FROM collection_runs
        WHERE module_name = 'event_calendar_data' AND source_name = 'Macro Calendar API'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    coverage = service.load_source_coverage(source_names=["Macro Calendar API"])

    assert run_row["status"] == "success"
    assert run_row["item_count"] == 1
    assert coverage["source_count"] == 1
    assert coverage["ready_source_count"] == 1
    assert coverage["problem_source_count"] == 0
    assert coverage["upcoming_event_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 1
    assert coverage["sources"][0]["source_name"] == "Macro Calendar API"
    assert coverage["sources"][0]["name"] == "Macro Calendar API"
    assert coverage["sources"][0]["configuration_ready"] is True
    assert coverage["sources"][0]["health_status"] == "ready"
    assert coverage["sources"][0]["is_ready_for_ai"] is False
    assert coverage["sources"][0]["last_run_status"] == "success"
    assert "thin_upcoming_horizon" in coverage["sources"][0]["data_quality_flags"]
    service.close()


def test_event_calendar_collect_marks_unconfigured_sources_in_collection_runs(tmp_path, monkeypatch):
    unconfigured_source = EventCalendarSource(
        name="Macro Calendar API",
        event_type="macro",
        endpoint=None,
        tags=["macro", "calendar"],
    )

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        lambda *args, **kwargs: [unconfigured_source],
    )

    service = EventCalendarDataService(
        client=SequenceEventClient({}),
        db=DBManager(str(tmp_path / "calendar_unconfigured.sqlite")),
    )
    service.init_storage()

    result = service.collect_once(source_names=["Macro Calendar API"])

    run_row = service.db.fetch_one(
        """
        SELECT status, item_count, message
        FROM collection_runs
        WHERE module_name = 'event_calendar_data' AND source_name = 'Macro Calendar API'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    coverage = service.load_source_coverage(source_names=["Macro Calendar API"])

    assert result == {"event_count": 0}
    assert run_row["status"] == "unconfigured"
    assert run_row["item_count"] == 0
    assert "未配置 endpoint" in (run_row["message"] or "")
    assert coverage["sources"][0]["configuration_ready"] is False
    assert coverage["sources"][0]["health_status"] == "unconfigured"
    assert coverage["sources"][0]["last_run_status"] == "unconfigured"
    service.close()


def test_event_calendar_source_with_single_low_signal_event_is_not_ai_ready(tmp_path, monkeypatch):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_source = EventCalendarSource(
        name="Upgrade Calendar API",
        event_type="upgrade",
        endpoint="https://calendar.example/api/upgrade",
        tags=["upgrade", "calendar"],
    )

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        lambda *args, **kwargs: [configured_source],
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_single_low_signal.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="upgrade",
                title="Minor Governance Execution",
                symbol="SUI",
                scheduled_at=fixed_now + timedelta(days=20),
                importance_score=0.4,
                source_name="Upgrade Calendar API",
                tags=["upgrade"],
            ),
        ]
    )
    service.db.record_collection_run(
        module_name="event_calendar_data",
        source_name="Upgrade Calendar API",
        job_name="event_calendar_events",
        status="success",
        item_count=1,
        started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
        finished_at=fixed_now.isoformat(),
        duration_seconds=300,
    )

    coverage = service.load_source_coverage(source_names=["Upgrade Calendar API"])
    source = coverage["sources"][0]

    assert coverage["ready_source_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 0
    assert source["health_status"] == "ready"
    assert source["upcoming_events"] == 1
    assert source["upcoming_high_importance_events"] == 0
    assert source["is_ready_for_ai"] is False
    assert "single_low_signal_upcoming_event" in source["data_quality_flags"]
    service.close()


def test_load_upcoming_context_bundle_groups_forward_catalysts(monkeypatch, tmp_path):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_sources = [
        EventCalendarSource(
            name="Macro Calendar API",
            event_type="macro",
            endpoint="https://calendar.example/api/macro",
            tags=["macro", "calendar"],
        ),
        EventCalendarSource(
            name="ETF Calendar API",
            event_type="etf",
            endpoint="https://calendar.example/api/etf",
            tags=["etf", "calendar"],
        ),
        EventCalendarSource(
            name="Token Unlock Calendar API",
            event_type="unlock",
            endpoint="https://calendar.example/api/unlock",
            tags=["unlock", "calendar"],
        ),
    ]

    def fake_loader(source_names=None, event_types=None, enabled_only=True):
        rows = list(configured_sources)
        if source_names:
            normalized_names = {value.strip().lower() for value in source_names if value.strip()}
            rows = [row for row in rows if row.name.lower() in normalized_names]
        if event_types:
            normalized_types = {value.strip().lower() for value in event_types if value.strip()}
            rows = [row for row in rows if row.event_type.lower() in normalized_types]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_bundle.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="FOMC Rate Decision",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(hours=12),
                importance_score=0.95,
                source_name="Macro Calendar API",
                tags=["fomc", "rates"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="BTC ETF Review Deadline",
                symbol="BTC",
                scheduled_at=fixed_now + timedelta(days=5),
                importance_score=0.85,
                source_name="ETF Calendar API",
                tags=["etf", "regulation"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Large Token Unlock",
                symbol="SOL",
                scheduled_at=fixed_now + timedelta(days=6),
                importance_score=0.9,
                source_name="Token Unlock Calendar API",
                tags=["unlock", "supply"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="ETH ETF Follow-up Review Window",
                symbol="ETH",
                scheduled_at=fixed_now + timedelta(days=18),
                importance_score=0.55,
                source_name="ETF Calendar API",
                tags=["etf", "review"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Secondary Token Unlock Window",
                symbol="SUI",
                scheduled_at=fixed_now + timedelta(days=16),
                importance_score=0.5,
                source_name="Token Unlock Calendar API",
                tags=["unlock", "supply"],
            ),
            EventCalendarEvent(
                event_type="macro",
                title="US CPI Release",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(days=20),
                importance_score=0.6,
                source_name="Macro Calendar API",
                tags=["cpi", "inflation"],
            ),
        ]
    )

    for source_name in (
        "Macro Calendar API",
        "ETF Calendar API",
        "Token Unlock Calendar API",
    ):
        service.db.record_collection_run(
            module_name="event_calendar_data",
            source_name=source_name,
            job_name="event_calendar_events",
            status="success",
            item_count=1,
            started_at=(fixed_now - timedelta(minutes=10)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=600,
        )

    bundle = service.load_upcoming_context_bundle(horizon_days=30)

    assert bundle["as_of"] == fixed_now.isoformat()
    assert bundle["event_count"] == 6
    assert bundle["source_counts"] == {
        "Macro Calendar API": 2,
        "ETF Calendar API": 2,
        "Token Unlock Calendar API": 2,
    }
    assert bundle["configured_universe_summary"]["scope_kind"] == "default"
    assert bundle["configured_universe_summary"]["breadth_status"] == "limited"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is False
    assert bundle["configured_universe_summary"]["missing_semantic_groups"] == [
        "protocol_upgrade"
    ]
    assert bundle["coverage_summary"]["selected_source_count"] == 3
    assert bundle["coverage_summary"]["ready_source_count"] == 3
    assert bundle["coverage_summary"]["ready_for_ai_source_count"] == 3
    assert bundle["coverage_summary"]["missing_event_types"] == []
    assert bundle["coverage_summary"]["event_count_next_24h"] == 1
    assert bundle["coverage_summary"]["event_count_next_7d"] == 3
    assert bundle["coverage_summary"]["event_count_next_30d"] == 6
    assert bundle["source_health_summary"]["ready_source_count"] == 3
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 3
    assert {
        item["source_name"]
        for item in bundle["coverage_summary"]["coverage_by_source"]
    } == {
        "Macro Calendar API",
        "ETF Calendar API",
        "Token Unlock Calendar API",
    }
    assert bundle["next_24h"]["events"][0]["title"] == "FOMC Rate Decision"
    assert bundle["high_importance_events"][0]["title"] == "FOMC Rate Decision"
    by_event_type = {
        item["event_type"]: item
        for item in bundle["by_event_type"]
    }
    assert by_event_type["macro"]["event_count"] == 2
    assert by_event_type["etf"]["event_count"] == 2
    assert by_event_type["unlock"]["event_count"] == 2
    symbol_map = {
        item["symbol"]: item
        for item in bundle["symbol_watchlist"]
    }
    assert bundle["symbol_watchlist"][0]["symbol"] == "MARKET"
    assert symbol_map["BTC"]["event_count"] == 1
    assert symbol_map["SOL"]["high_importance_event_count"] == 1
    assert bundle["data_quality_flags"] == [
        "event_calendar_configured_market_breadth_limited"
    ]
    assert any("默认配置宇宙只覆盖 3 类事件/3 路来源" in note for note in bundle["quality_notes"])

    service.close()


def test_event_calendar_coverage_marks_unconfigured_source():
    service = EventCalendarDataService()

    coverage = service.load_source_coverage(source_names=["ETF Calendar API"])
    source = coverage["sources"][0]

    assert coverage["source_count"] == 1
    assert coverage["ready_source_count"] == 0
    assert coverage["unconfigured_source_count"] == 1
    assert coverage["problem_source_count"] == 1
    assert source["source_name"] == "ETF Calendar API"
    assert source["configuration_ready"] is False
    assert source["health_status"] == "unconfigured"
    assert source["is_ready_for_ai"] is False
    assert "unconfigured_source" in source["data_quality_flags"]
    assert "no_historical_events" in source["data_quality_flags"]
    assert any("没有配置真实 endpoint" in note for note in source["quality_notes"])
    service.close()


def test_event_calendar_bundle_marks_event_type_missing_when_source_not_ai_ready(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_sources = [
        EventCalendarSource(
            name="Macro Calendar API",
            event_type="macro",
            endpoint="https://calendar.example/api/macro",
            tags=["macro", "calendar"],
        ),
        EventCalendarSource(
            name="ETF Calendar API",
            event_type="etf",
            endpoint="https://calendar.example/api/etf",
            tags=["etf", "calendar"],
        ),
    ]

    def fake_loader(source_names=None, event_types=None, enabled_only=True):
        rows = list(configured_sources)
        if source_names:
            normalized_names = {value.strip().lower() for value in source_names if value.strip()}
            rows = [row for row in rows if row.name.lower() in normalized_names]
        if event_types:
            normalized_types = {value.strip().lower() for value in event_types if value.strip()}
            rows = [row for row in rows if row.event_type.lower() in normalized_types]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_bundle_missing_ai_ready.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="US CPI",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(days=2),
                importance_score=0.9,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="BTC ETF Decision Window",
                symbol="BTC",
                scheduled_at=fixed_now + timedelta(days=20),
                importance_score=0.85,
                source_name="ETF Calendar API",
                tags=["etf"],
            ),
        ]
    )

    for source_name in ("Macro Calendar API", "ETF Calendar API"):
        service.db.record_collection_run(
            module_name="event_calendar_data",
            source_name=source_name,
            job_name="event_calendar_events",
            status="success",
            item_count=1,
            started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=300,
        )

    bundle = service.load_upcoming_context_bundle(horizon_days=30)

    assert bundle["coverage_summary"]["ready_source_count"] == 2
    assert bundle["coverage_summary"]["ready_for_ai_source_count"] == 1
    assert bundle["event_count"] == 1
    assert bundle["raw_event_count"] == 2
    assert bundle["source_counts"] == {"ETF Calendar API": 1}
    assert bundle["raw_source_counts"] == {
        "ETF Calendar API": 1,
        "Macro Calendar API": 1,
    }
    assert bundle["ai_ready_source_names"] == ["ETF Calendar API"]
    assert bundle["ai_excluded_source_names"] == ["Macro Calendar API"]
    assert bundle["ai_excluded_sources"] == [
        {
            "source_name": "Macro Calendar API",
            "event_type": "macro",
            "excluded_reason": "source_not_ai_ready",
            "raw_event_count": 1,
            "raw_high_importance_event_count": 1,
            "raw_next_event_at": (fixed_now + timedelta(days=2)).isoformat(),
            "raw_farthest_event_horizon_days": 2.0,
            "health_status": "ready",
            "is_ready_for_ai": False,
            "configuration_ready": True,
            "is_stale": False,
            "upcoming_events": 1,
            "upcoming_high_importance_events": 1,
            "minimum_horizon_days": 14,
            "farthest_event_horizon_days": 2.0,
            "data_quality_flags": ["thin_upcoming_horizon"],
            "quality_notes": [
                "当前未来事件只延伸到 2.0 天，低于该类事件建议的 14 天前瞻视野。",
                "宏观事件时间点是 AI 判断风险窗口和跨市场联动的重要前置证据。",
                "最近一次事件采集虽然成功，但未来事件视野仍未达到可直接供 AI 做交易前瞻判断的质量门槛。",
            ],
        }
    ]
    assert bundle["coverage_summary"]["missing_event_types"] == ["macro"]
    assert bundle["coverage_summary"]["raw_observed_event_types"] == ["etf", "macro"]
    assert bundle["coverage_summary"]["event_count_next_7d"] == 0
    assert bundle["coverage_summary"]["raw_event_count_next_7d"] == 1
    assert bundle["coverage_summary"]["ai_excluded_source_names"] == [
        "Macro Calendar API"
    ]
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 1
    assert [item["title"] for item in bundle["upcoming_events"]] == [
        "BTC ETF Decision Window"
    ]
    assert any(
        item["source_name"] == "Macro Calendar API" and item["is_ready_for_ai"] is False
        for item in bundle["coverage_summary"]["coverage_by_source"]
    )
    service.close()


def test_event_calendar_bundle_configured_universe_sufficient_when_all_core_event_types_present(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_sources = [
        EventCalendarSource(
            name="Macro Calendar API",
            event_type="macro",
            endpoint="https://calendar.example/api/macro",
            tags=["macro", "calendar"],
        ),
        EventCalendarSource(
            name="ETF Calendar API",
            event_type="etf",
            endpoint="https://calendar.example/api/etf",
            tags=["etf", "calendar"],
        ),
        EventCalendarSource(
            name="Token Unlock Calendar API",
            event_type="unlock",
            endpoint="https://calendar.example/api/unlock",
            tags=["unlock", "calendar"],
        ),
        EventCalendarSource(
            name="Project Upgrade Calendar API",
            event_type="upgrade",
            endpoint="https://calendar.example/api/upgrade",
            tags=["upgrade", "calendar"],
        ),
    ]

    def fake_loader(source_names=None, event_types=None, enabled_only=True):
        rows = list(configured_sources)
        if source_names:
            normalized_names = {value.strip().lower() for value in source_names if value.strip()}
            rows = [row for row in rows if row.name.lower() in normalized_names]
        if event_types:
            normalized_types = {value.strip().lower() for value in event_types if value.strip()}
            rows = [row for row in rows if row.event_type.lower() in normalized_types]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_bundle_full_universe.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="FOMC Rate Decision",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(hours=12),
                importance_score=0.95,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
            EventCalendarEvent(
                event_type="macro",
                title="US CPI Release",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(days=20),
                importance_score=0.6,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="BTC ETF Review Deadline",
                symbol="BTC",
                scheduled_at=fixed_now + timedelta(days=5),
                importance_score=0.85,
                source_name="ETF Calendar API",
                tags=["etf"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="ETH ETF Review Deadline",
                symbol="ETH",
                scheduled_at=fixed_now + timedelta(days=18),
                importance_score=0.55,
                source_name="ETF Calendar API",
                tags=["etf"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Large Token Unlock",
                symbol="SOL",
                scheduled_at=fixed_now + timedelta(days=6),
                importance_score=0.9,
                source_name="Token Unlock Calendar API",
                tags=["unlock"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Secondary Unlock Window",
                symbol="SUI",
                scheduled_at=fixed_now + timedelta(days=16),
                importance_score=0.5,
                source_name="Token Unlock Calendar API",
                tags=["unlock"],
            ),
            EventCalendarEvent(
                event_type="upgrade",
                title="Mainnet Upgrade Window",
                symbol="SUI",
                scheduled_at=fixed_now + timedelta(days=3),
                importance_score=0.88,
                source_name="Project Upgrade Calendar API",
                tags=["upgrade"],
            ),
            EventCalendarEvent(
                event_type="upgrade",
                title="Governance Execution Window",
                symbol="ARB",
                scheduled_at=fixed_now + timedelta(days=15),
                importance_score=0.7,
                source_name="Project Upgrade Calendar API",
                tags=["upgrade"],
            ),
        ]
    )

    for source_name in (
        "Macro Calendar API",
        "ETF Calendar API",
        "Token Unlock Calendar API",
        "Project Upgrade Calendar API",
    ):
        service.db.record_collection_run(
            module_name="event_calendar_data",
            source_name=source_name,
            job_name="event_calendar_events",
            status="success",
            item_count=2,
            started_at=(fixed_now - timedelta(minutes=10)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=600,
        )

    bundle = service.load_upcoming_context_bundle(horizon_days=30)

    assert bundle["configured_universe_summary"]["scope_kind"] == "default"
    assert bundle["configured_universe_summary"]["breadth_status"] == "sufficient"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is True
    assert bundle["configured_universe_summary"]["event_type_count"] == 4
    assert bundle["configured_universe_summary"]["source_count"] == 4
    assert bundle["configured_universe_summary"]["missing_semantic_groups"] == []
    assert "event_calendar_configured_market_breadth_limited" not in bundle["data_quality_flags"]

    service.close()


def test_event_calendar_symbol_filtered_bundle_does_not_mislabel_missing_event_types(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_sources = [
        EventCalendarSource(
            name="Macro Calendar API",
            event_type="macro",
            endpoint="https://calendar.example/api/macro",
            tags=["macro", "calendar"],
        ),
        EventCalendarSource(
            name="ETF Calendar API",
            event_type="etf",
            endpoint="https://calendar.example/api/etf",
            tags=["etf", "calendar"],
        ),
        EventCalendarSource(
            name="Token Unlock Calendar API",
            event_type="unlock",
            endpoint="https://calendar.example/api/unlock",
            tags=["unlock", "calendar"],
        ),
    ]

    def fake_loader(source_names=None, event_types=None, enabled_only=True):
        rows = list(configured_sources)
        if source_names:
            normalized_names = {value.strip().lower() for value in source_names if value.strip()}
            rows = [row for row in rows if row.name.lower() in normalized_names]
        if event_types:
            normalized_types = {value.strip().lower() for value in event_types if value.strip()}
            rows = [row for row in rows if row.event_type.lower() in normalized_types]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return rows

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_bundle_symbol_filter.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="FOMC Rate Decision",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(hours=12),
                importance_score=0.95,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
            EventCalendarEvent(
                event_type="macro",
                title="US CPI Release",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(days=20),
                importance_score=0.6,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="BTC ETF Review Deadline",
                symbol="BTC",
                scheduled_at=fixed_now + timedelta(days=5),
                importance_score=0.85,
                source_name="ETF Calendar API",
                tags=["etf"],
            ),
            EventCalendarEvent(
                event_type="etf",
                title="ETH ETF Review Deadline",
                symbol="ETH",
                scheduled_at=fixed_now + timedelta(days=18),
                importance_score=0.55,
                source_name="ETF Calendar API",
                tags=["etf"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Large Token Unlock",
                symbol="SOL",
                scheduled_at=fixed_now + timedelta(days=6),
                importance_score=0.9,
                source_name="Token Unlock Calendar API",
                tags=["unlock"],
            ),
            EventCalendarEvent(
                event_type="unlock",
                title="Secondary Unlock Window",
                symbol="SUI",
                scheduled_at=fixed_now + timedelta(days=16),
                importance_score=0.5,
                source_name="Token Unlock Calendar API",
                tags=["unlock"],
            ),
        ]
    )

    for source_name in (
        "Macro Calendar API",
        "ETF Calendar API",
        "Token Unlock Calendar API",
    ):
        service.db.record_collection_run(
            module_name="event_calendar_data",
            source_name=source_name,
            job_name="event_calendar_events",
            status="success",
            item_count=2,
            started_at=(fixed_now - timedelta(minutes=10)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=600,
        )

    bundle = service.load_upcoming_context_bundle(
        horizon_days=30,
        symbols=["BTC"],
    )

    assert bundle["configured_universe_summary"]["scope_kind"] == "filtered"
    assert bundle["configured_universe_summary"]["breadth_status"] == "filtered"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is None
    assert bundle["coverage_summary"]["missing_event_types"] == []
    assert "event_calendar_event_types_incomplete" not in bundle["data_quality_flags"]
    assert "event_calendar_single_event_type_only" not in bundle["data_quality_flags"]

    service.close()


def test_event_calendar_bundle_empty_when_only_non_ai_ready_sources_remain(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    configured_sources = [
        EventCalendarSource(
            name="Macro Calendar API",
            event_type="macro",
            endpoint="https://calendar.example/api/macro",
            tags=["macro", "calendar"],
        ),
    ]

    def fake_loader(source_names=None, event_types=None, enabled_only=True):
        return list(configured_sources)

    monkeypatch.setattr(
        "data_layer.event_calendar_data.service.load_event_calendar_sources",
        fake_loader,
    )
    monkeypatch.setattr(
        EventCalendarDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = EventCalendarDataService(
        db=DBManager(str(tmp_path / "calendar_bundle_only_non_ai_ready.sqlite"))
    )
    service.init_storage()
    service.collector.save_to_db(
        [
            EventCalendarEvent(
                event_type="macro",
                title="US CPI",
                symbol="MARKET",
                scheduled_at=fixed_now + timedelta(days=2),
                importance_score=0.9,
                source_name="Macro Calendar API",
                tags=["macro"],
            ),
        ]
    )
    service.db.record_collection_run(
        module_name="event_calendar_data",
        source_name="Macro Calendar API",
        job_name="event_calendar_events",
        status="success",
        item_count=1,
        started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
        finished_at=fixed_now.isoformat(),
        duration_seconds=300,
    )

    bundle = service.load_upcoming_context_bundle(horizon_days=30)

    assert bundle["event_count"] == 0
    assert bundle["raw_event_count"] == 1
    assert bundle["source_counts"] == {}
    assert bundle["raw_source_counts"] == {"Macro Calendar API": 1}
    assert bundle["ai_excluded_source_names"] == ["Macro Calendar API"]
    assert bundle["coverage_summary"]["event_count_next_24h"] == 0
    assert bundle["coverage_summary"]["raw_event_count_next_24h"] == 0
    assert bundle["coverage_summary"]["event_count_next_7d"] == 0
    assert bundle["coverage_summary"]["raw_event_count_next_7d"] == 1
    assert bundle["coverage_summary"]["raw_observed_event_types"] == ["macro"]
    assert "event_calendar_context_empty" in bundle["data_quality_flags"]
    assert any(
        "虽然还有真实已落库事件，但它们全部来自尚未达到 AI-ready 门槛的事件源"
        in note
        for note in bundle["quality_notes"]
    )

    service.close()
