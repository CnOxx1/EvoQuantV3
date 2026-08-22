"""本地 Intelligence Console 工作区 SQLite 表的回归测试。"""

from __future__ import annotations

import sqlite3

from database.db_manager import DBManager
from scripts.migrate_admin_workspace import MIGRATION_ID, migrate


ADMIN_TABLES = {
    "admin_users",
    "admin_teams",
    "admin_team_members",
    "admin_team_invitations",
    "admin_evoquant_connections",
    "admin_watchlists",
    "admin_watchlist_assets",
    "admin_research_briefs",
    "admin_brief_assets",
    "admin_risk_alerts",
    "admin_ingest_events",
    "admin_alert_feedback",
    "admin_api_keys",
    "admin_usage_events",
}


def test_admin_workspace_schema_is_idempotent_and_isolated(tmp_path):
    """后台专用表应可重复创建，且通过 admin_ 前缀与行情表隔离。"""
    manager = DBManager(str(tmp_path / "analytics.db"))
    manager._create_admin_workspace_tables()
    manager._create_admin_workspace_tables()

    rows = manager.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'admin_%'"
    )
    assert {row["name"] for row in rows} == ADMIN_TABLES

    indexes = manager.fetch_all(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_admin_%'"
    )
    assert "idx_admin_risk_alerts_team_event" in {row["name"] for row in indexes}
    assert "idx_admin_usage_events_team_time" in {row["name"] for row in indexes}

    manager.close()


def test_admin_workspace_schema_enforces_team_scoped_ingest_idempotency(tmp_path):
    """同一团队同一事件只能入库一次，避免闭环重试导致重复简报。"""
    manager = DBManager(str(tmp_path / "analytics.db"))
    manager._create_admin_workspace_tables()
    conn = manager.conn
    conn.execute("INSERT INTO admin_users (open_id, role) VALUES ('owner', 'admin')")
    conn.execute(
        "INSERT INTO admin_teams (name, slug, created_by) VALUES ('研究团队', 'research', 1)"
    )
    conn.execute(
        "INSERT INTO admin_ingest_events (team_id, event_id, payload_hash, source, reported_at) "
        "VALUES (1, 'evt-1', 'hash', 'test', '2026-08-21T00:00:00Z')"
    )
    try:
        conn.execute(
            "INSERT INTO admin_ingest_events (team_id, event_id, payload_hash, source, reported_at) "
            "VALUES (1, 'evt-1', 'hash-2', 'test', '2026-08-21T00:00:01Z')"
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("admin_ingest_events 应拒绝同团队的重复 event_id")
    finally:
        manager.close()


def test_admin_workspace_migration_tracks_version_and_is_idempotent(tmp_path):
    """迁移应留下版本记录，第二次执行仅报告已应用而不重复写入。"""
    database_path = tmp_path / "analytics.db"
    first = migrate(str(database_path))
    second = migrate(str(database_path))
    assert first["status"] == "applied"
    assert second["status"] == "already_applied"

    manager = DBManager(str(database_path))
    try:
        record = manager.fetch_one(
            "SELECT migration_id, component FROM evoquant_schema_migrations WHERE migration_id = ?",
            (MIGRATION_ID,),
        )
        assert dict(record) == {
            "migration_id": MIGRATION_ID,
            "component": "intelligence_console",
        }
    finally:
        manager.close()
