"""从 crypto_data.db 迁移数据到域拆分数据库。

用法：
    python -m database.migrate_split [--dry-run] [--source PATH]

迁移完成后原文件不会被删除，需手动确认后重命名为 .backup。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    ANALYTICS_DB_PATH,
    DATABASE_DIR,
    DATABASE_PATH,
    EXCHANGE_DATA_DB_PATH,
    MARKET_DATA_DB_PATH,
)
from database.db_manager import DBManager
from database.schemas import (
    EXCHANGE_DATA_TABLE_NAMES,
    MARKET_DATA_TABLE_NAMES,
)

# analytics 域的物理表名
ANALYTICS_TABLE_NAMES: list[str] = [
    "collection_runs",
    "merged_klines",
    "technical_indicators",
    "exchange_comparison_snapshots",
    "macro_context_snapshots",
    "ai_market_context_snapshots",
    "market_breadth_snapshots",
    "market_structure_snapshots",
    "asset_readiness_snapshots",
    "data_quality_audit_snapshots",
]

DOMAIN_MAP: dict[str, tuple[str, list[str]]] = {
    "exchange_data": (EXCHANGE_DATA_DB_PATH, EXCHANGE_DATA_TABLE_NAMES),
    "market_data": (MARKET_DATA_DB_PATH, MARKET_DATA_TABLE_NAMES),
    "analytics": (ANALYTICS_DB_PATH, ANALYTICS_TABLE_NAMES),
}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return bool(row and row[0] > 0)


def _row_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()
    return row[0] if row else 0


def migrate(source_path: str, dry_run: bool = False):
    """将 source_path 中的表数据按域拷贝到对应域数据库。"""
    if not os.path.exists(source_path):
        print(f"源数据库不存在: {source_path}")
        return

    # 先确保目标域数据库的表结构已创建
    if not dry_run:
        ex_db = DBManager(db_path=EXCHANGE_DATA_DB_PATH)
        ex_db.init_exchange_data_tables()
        mk_db = DBManager(db_path=MARKET_DATA_DB_PATH)
        mk_db.init_market_data_tables()
        an_db = DBManager(db_path=ANALYTICS_DB_PATH)
        an_db.init_analytics_tables()
        ex_db.close()
        mk_db.close()
        an_db.close()

    source_conn = sqlite3.connect(source_path, timeout=60)
    source_conn.execute("PRAGMA journal_mode=WAL")

    total_migrated = 0

    for domain_name, (target_path, table_names) in DOMAIN_MAP.items():
        print(f"\n{'[DRY-RUN] ' if dry_run else ''}域: {domain_name}")
        print(f"  目标: {target_path}")

        if not dry_run:
            source_conn.execute(
                f"ATTACH DATABASE '{target_path}' AS target_db"
            )

        for table_name in table_names:
            if not _table_exists(source_conn, table_name):
                print(f"  跳过 {table_name} (源表不存在)")
                continue

            count = _row_count(source_conn, table_name)
            if count == 0:
                print(f"  跳过 {table_name} (0 行)")
                continue

            if dry_run:
                print(f"  将迁移 {table_name}: {count} 行")
            else:
                source_conn.execute(
                    f"INSERT OR IGNORE INTO target_db.[{table_name}] "
                    f"SELECT * FROM main.[{table_name}]"
                )
                migrated = _row_count(source_conn, f"target_db.{table_name}")
                print(f"  已迁移 {table_name}: {count} → {migrated} 行")

            total_migrated += count

        if not dry_run:
            source_conn.commit()
            source_conn.execute("DETACH DATABASE target_db")

    source_conn.close()
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}迁移完成，共处理 {total_migrated} 行")
    if not dry_run:
        print(f"原文件保留: {source_path}")
        print("确认无误后可手动重命名为 .backup")


def main():
    parser = argparse.ArgumentParser(description="数据库域拆分迁移工具")
    parser.add_argument(
        "--source",
        default=DATABASE_PATH,
        help=f"源数据库路径 (默认: {DATABASE_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印迁移计划，不实际执行",
    )
    args = parser.parse_args()
    migrate(source_path=args.source, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
