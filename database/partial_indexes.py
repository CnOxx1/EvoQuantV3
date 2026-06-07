"""部分索引和覆盖索引 — 为热数据查询添加针对性索引。

部分索引：只索引满足条件的行，减少索引体积，提升写入速度
覆盖索引：包含查询需要的所有列，避免回表（索引扫描即可返回数据）

使用方式：
    from database.partial_indexes import ensure_partial_indexes, ensure_covering_indexes

    ensure_partial_indexes(conn)
    ensure_covering_indexes(conn)
"""

from __future__ import annotations

import os
import sqlite3
import time

from loguru import logger

# 环境变量控制
PARTIAL_INDEX_ENABLED = os.environ.get("DB_PARTIAL_INDEXES", "1") == "1"

# 部分索引定义：(index_name, table_name, columns, where_clause)
PARTIAL_INDEXES: list[tuple[str, str, str, str]] = [
    # 只索引最近 7 天的 klines（热数据查询加速）
    (
        "idx_klines_hot_7d",
        "klines",
        "symbol, exchange, timeframe, open_time DESC",
        "open_time >= datetime('now', '-7 days')",
    ),
    # 只索引 status='running' 的采集任务（活跃任务查询）
    (
        "idx_collection_runs_active",
        "collection_runs",
        "module_name, started_at DESC",
        "status = 'running'",
    ),
    # 只索引最近 24h 的 tickers（实时行情查询）
    (
        "idx_tickers_hot_24h",
        "tickers",
        "symbol, exchange, timestamp DESC",
        "timestamp >= datetime('now', '-1 day')",
    ),
]

# 覆盖索引：包含查询需要的所有列，避免回表
# (index_name, table_name, columns)
COVERING_INDEXES: list[tuple[str, str, str]] = [
    # latest_tickers 查询通常需要 last_price, volume, spread
    (
        "idx_latest_tickers_covering",
        "latest_tickers",
        "symbol, exchange, last_price, quote_volume_24h, spread_bps, timestamp",
    ),
]


def ensure_partial_indexes(conn: sqlite3.Connection) -> int:
    """创建部分索引，返回新建索引数。"""
    if not PARTIAL_INDEX_ENABLED:
        return 0

    created = 0
    for index_name, table_name, columns, where in PARTIAL_INDEXES:
        sql = (
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} ({columns}) WHERE {where}"
        )
        try:
            conn.execute(sql)
            created += 1
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                logger.debug("跳过部分索引 {} — 表 {} 不存在", index_name, table_name)
            else:
                logger.warning("创建部分索引 {} 失败: {}", index_name, exc)
    if created:
        conn.commit()
        logger.info("部分索引创建完成: {} 个", created)
    return created


def ensure_covering_indexes(conn: sqlite3.Connection) -> int:
    """创建覆盖索引，返回新建索引数。"""
    created = 0
    for index_name, table_name, columns in COVERING_INDEXES:
        sql = (
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table_name} ({columns})"
        )
        try:
            conn.execute(sql)
            created += 1
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                logger.debug("跳过覆盖索引 {} — 表 {} 不存在", index_name, table_name)
            else:
                logger.warning("创建覆盖索引 {} 失败: {}", index_name, exc)
    if created:
        conn.commit()
        logger.info("覆盖索引创建完成: {} 个", created)
    return created


def ensure_all_advanced_indexes(conn: sqlite3.Connection) -> dict[str, int]:
    """创建所有高级索引（部分 + 覆盖），返回统计。"""
    start = time.monotonic()
    results = {
        "partial": ensure_partial_indexes(conn),
        "covering": ensure_covering_indexes(conn),
    }
    elapsed = time.monotonic() - start
    total = sum(results.values())
    if total:
        logger.info("高级索引优化完成: {} 个 ({:.1f}s) — {}", total, elapsed, results)
    return results
