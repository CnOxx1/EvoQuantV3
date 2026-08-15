"""API 启动时预热高频查询数据到 QueryCache，消除冷启动延迟。"""

from __future__ import annotations

import os
from pathlib import Path

from loguru import logger


# 表名与物理数据库路径显式绑定，避免在 DB_SPLIT_ENABLED=1 时错误查询 crypto_data.db。
# 仅预热 latest_* 小型快照表；历史 K 线和技术指标按请求查询，避免冷启动占满内存。
PRELOAD_TABLE_PATHS = {
    "latest_tickers": "exchange_data.db",
    "latest_funding_rates": "exchange_data.db",
    "latest_orderbook_snapshots": "exchange_data.db",
    "latest_open_interest_snapshots": "exchange_data.db",
    "latest_trade_flow_bars": "exchange_data.db",
}
DEFAULT_PRELOAD_TABLES = (
    "latest_tickers",
    "latest_funding_rates",
)

API_PRELOAD_ENABLED = os.environ.get("API_PRELOAD_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
API_PRELOAD_TABLES = tuple(
    table.strip()
    for table in os.environ.get(
        "API_PRELOAD_TABLES", ",".join(DEFAULT_PRELOAD_TABLES)
    ).split(",")
    if table.strip()
)


def _is_missing_table_error(error: Exception) -> bool:
    message = str(error).lower()
    return "no such table" in message or "does not exist" in message


def _database_path(database_filename: str) -> str:
    from config.settings import DATABASE_DIR

    return str(Path(DATABASE_DIR) / database_filename)


async def preload_hot_data() -> None:
    """预加载允许的交易所 latest_* 快照表到 QueryCache。"""
    if not API_PRELOAD_ENABLED:
        logger.info("热数据预加载已禁用 (API_PRELOAD_ENABLED=false)")
        return

    from api.query_cache import query_cache
    from database.db_manager import DBManager

    requested_tables = list(dict.fromkeys(API_PRELOAD_TABLES))
    tables = [table for table in requested_tables if table in PRELOAD_TABLE_PATHS]
    rejected_tables = [table for table in requested_tables if table not in PRELOAD_TABLE_PATHS]
    for table in rejected_tables:
        logger.warning("忽略不受支持的 API_PRELOAD_TABLES 表: {}", table)

    db_by_filename: dict[str, DBManager] = {}
    loaded = 0
    skipped = 0
    for table in tables:
        database_filename = PRELOAD_TABLE_PATHS[table]
        db = db_by_filename.setdefault(
            database_filename,
            DBManager(_database_path(database_filename)),
        )
        try:
            query_cache.get_or_fetch(
                key=f"preload:{table}",
                fetcher=lambda t=table, manager=db: manager.fetch_all(
                    f"SELECT * FROM {t}"
                ),
                ttl=300,
            )
            loaded += 1
        except Exception as error:
            if _is_missing_table_error(error):
                skipped += 1
                logger.info("预加载表 {} 尚未初始化，跳过", table)
            else:
                logger.warning(
                    "预加载表 {} 失败: {}: {}", table, type(error).__name__, error
                )

    for db in db_by_filename.values():
        db.close()

    logger.info(
        "热数据预加载完成：{}/{} 表已缓存，{} 表尚未初始化",
        loaded,
        len(tables),
        skipped,
    )
