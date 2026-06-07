"""分块查询支持 — 为大表查询提供生成器接口，避免一次加载全表。

使用方式：
    from database.chunked_query import chunked_fetch, chunked_fetch_df

    # 生成器模式：每次返回 chunk_size 行
    for rows in chunked_fetch(conn, "SELECT * FROM klines WHERE symbol = ?", ("BTC/USDT",)):
        process(rows)

    # DataFrame 生成器模式
    for df_chunk in chunked_fetch_df(conn, "SELECT * FROM klines", chunk_size=10000):
        result = compute(df_chunk)
"""

from __future__ import annotations

import os
import sqlite3
from typing import Generator

from loguru import logger

# 默认分块大小（通过环境变量可配置）
DEFAULT_CHUNK_SIZE = int(os.environ.get("DB_CHUNK_SIZE", "5000"))


def chunked_fetch(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Generator[list[sqlite3.Row], None, None]:
    """分块读取查询结果 — 生成器模式。

    用于大表查询时控制内存占用。每次 yield 一个 chunk。
    """
    cursor = conn.execute(sql, params)
    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break
        yield rows


def chunked_fetch_df(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    chunk_size: int = DEFAULT_CHUNK_SIZE,
):
    """分块读取为 DataFrame 生成器。

    每次 yield 一个包含 chunk_size 行的 DataFrame。
    需要 pandas 已安装（延迟导入）。

    Yields
    ------
    pd.DataFrame
        每个 chunk 对应的 DataFrame
    """
    import pandas as pd

    cursor = conn.execute(sql, params)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []

    while True:
        rows = cursor.fetchmany(chunk_size)
        if not rows:
            break
        yield pd.DataFrame([dict(r) for r in rows], columns=columns)


def fetch_with_limit(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    max_rows: int | None = None,
) -> list[sqlite3.Row]:
    """带最大行数限制的查询 — 防止无界查询导致 OOM。

    如果原 SQL 已包含 LIMIT 子句，不做额外处理。
    """
    if max_rows is None:
        max_rows = int(os.environ.get("DB_QUERY_MAX_ROWS", "100000"))

    # 简单检测：如果 SQL 已有 LIMIT，不注入额外限制
    sql_upper = sql.upper().rstrip().rstrip(";")
    if "LIMIT" not in sql_upper.split("ORDER BY")[-1] if "ORDER BY" in sql_upper else sql_upper:
        sql = f"{sql.rstrip().rstrip(';')} LIMIT {max_rows}"
        logger.debug("注入 LIMIT {} 防止无界查询", max_rows)

    cursor = conn.execute(sql, params)
    return cursor.fetchall()
