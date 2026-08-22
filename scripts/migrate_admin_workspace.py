"""执行 EvoQuant Intelligence Console 的 SQLite 工作区迁移。

迁移状态记录在 analytics.db 的 ``evoquant_schema_migrations`` 表中；业务表
仍由 DBManager 的幂等建表方法统一定义，避免 SQL 定义在多个位置漂移。
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


MIGRATIONS = (
    ("20260821_admin_workspace_v1", "创建团队工作区、简报、风险、审计与幂等投递表"),
    ("20260822_admin_password_auth_v2", "为本地账号密码登录增加用户名与密码哈希字段"),
)
MIGRATION_ID = MIGRATIONS[-1][0]


def migrate(database_path: str) -> dict[str, object]:
    """将指定 analytics.db 升级到管理后台工作区 v1。"""
    path = Path(database_path).expanduser().resolve()
    manager = DBManager(str(path))
    try:
        manager.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evoquant_schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                component TEXT NOT NULL,
                description TEXT NOT NULL
            )
            """
        )
        applied = []
        for migration_id, description in MIGRATIONS:
            existing = manager.conn.execute(
                "SELECT 1 FROM evoquant_schema_migrations WHERE migration_id = ?", (migration_id,)
            ).fetchone()
            if existing:
                continue
            manager._create_admin_workspace_tables()
            manager.conn.execute(
                "INSERT INTO evoquant_schema_migrations (migration_id, component, description) VALUES (?, 'intelligence_console', ?)",
                (migration_id, description),
            )
            applied.append(migration_id)
        manager.conn.commit()
        return {
            "database": str(path),
            "migration_ids": [item[0] for item in MIGRATIONS],
            "status": "applied" if applied else "already_applied",
            "applied": applied,
        }
    finally:
        manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 EvoQuant 管理后台 SQLite 工作区")
    parser.add_argument("--database", default=ANALYTICS_DB_PATH)
    args = parser.parse_args()
    print(json.dumps(migrate(args.database), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
