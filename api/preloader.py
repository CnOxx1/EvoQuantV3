"""API 启动时预热高频查询数据到 QueryCache，消除冷启动延迟。"""

from __future__ import annotations

import os
from loguru import logger


API_PRELOAD_ENABLED = os.environ.get("API_PRELOAD_ENABLED", "true").lower() in ("1", "true", "yes")
API_PRELOAD_TABLES = os.environ.get(
    "API_PRELOAD_TABLES",
    "latest_klines,latest_merged_klines,latest_technical_indicators,latest_funding_rates",
).split(",")


async def preload_hot_data() -> None:
    """预加载 latest_* 快照表到 QueryCache（异步友好但内部同步查询）。"""
    if not API_PRELOAD_ENABLED:
        logger.info("热数据预加载已禁用 (API_PRELOAD_ENABLED=false)")
        return

    from api.query_cache import query_cache
    from database.db_manager import DBManager

    db = DBManager()
    tables = [t.strip() for t in API_PRELOAD_TABLES if t.strip()]
    loaded = 0

    for table in tables:
        try:
            query_cache.get_or_fetch(
                key=f"preload:{table}",
                fetcher=lambda t=table: db.fetch_all(f"SELECT * FROM {t}"),
                ttl=300,
            )
            loaded += 1
        except Exception as e:
            logger.warning("预加载表 {} 失败: {}: {}", table, type(e).__name__, e)

    logger.info("热数据预加载完成：{}/{} 表已缓存", loaded, len(tables))
