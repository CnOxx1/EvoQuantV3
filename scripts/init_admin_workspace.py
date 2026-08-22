"""初始化并核验 EvoQuant Intelligence Console 的 SQLite 工作区表。

默认目标为 EvoQuant 的 ``database/analytics.db``。脚本仅创建 ``admin_*``
前缀的后台工作区表，不会重建、迁移或删除行情、市场和分析数据。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import ANALYTICS_DB_PATH
from database.db_manager import DBManager
from scripts.migrate_admin_workspace import migrate


ADMIN_TABLES = (
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
)


def initialize(database_path: str) -> dict[str, object]:
    """幂等创建后台表，并返回可用于运行验收的结构化结果。"""
    path = Path(database_path).expanduser().resolve()
    migration = migrate(str(path))
    manager = DBManager(str(path))
    try:
        rows = manager.fetch_all(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name LIKE 'admin_%' ORDER BY name"
        )
        tables = [row["name"] for row in rows]
        missing = sorted(set(ADMIN_TABLES) - set(tables))
        return {
            "database": str(path),
            "migration": migration,
            "status": "ready" if not missing else "incomplete",
            "admin_table_count": len(tables),
            "tables": tables,
            "missing_tables": missing,
            "foreign_keys_enabled": bool(manager.conn.execute("PRAGMA foreign_keys").fetchone()[0]),
            "journal_mode": manager.conn.execute("PRAGMA journal_mode").fetchone()[0],
        }
    finally:
        manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 EvoQuant 管理后台 SQLite 工作区表")
    parser.add_argument(
        "--database",
        default=ANALYTICS_DB_PATH,
        help="analytics SQLite 文件路径；默认使用项目 database/analytics.db",
    )
    args = parser.parse_args()
    result = initialize(args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "ready":
        raise SystemExit("后台工作区表未完整创建。")


if __name__ == "__main__":
    main()
