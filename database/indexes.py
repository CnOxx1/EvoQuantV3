"""数据库索引优化 — 为高频查询表添加复合索引。

在数据库初始化后调用 ensure_indexes() 即可。
使用 CREATE INDEX IF NOT EXISTS 保证幂等。
"""

from __future__ import annotations

import sqlite3
import time

from loguru import logger


# (index_name, table_name, columns)
# 按数据库域分组

EXCHANGE_DATA_INDEXES = [
    # klines 已有 idx_klines_lookup，补充 DESC 排序索引
    ("idx_klines_symbol_time_desc", "klines", "symbol, exchange, timeframe, open_time DESC"),
    # tickers 补充覆盖索引
    ("idx_tickers_symbol_exchange_ts_desc", "tickers", "symbol, exchange, timestamp DESC"),
    # funding_rates 补充时间降序
    ("idx_funding_rates_symbol_ts_desc", "funding_rates", "symbol, exchange, timestamp DESC"),
    # orderbook 补充时间降序
    ("idx_orderbook_symbol_ts_desc", "orderbook_snapshots", "symbol, exchange, timestamp DESC"),
    # trade_flow_bars 补充时间降序
    ("idx_trade_flow_bars_time_desc", "trade_flow_bars", "symbol, exchange, market_type, open_time DESC"),
    # open_interest 补充时间降序
    ("idx_oi_snapshots_time_desc", "open_interest_snapshots", "symbol, exchange, market_type, timestamp DESC"),
    # liquidation_bars 补充时间降序
    ("idx_liquidation_bars_time_desc", "liquidation_bars", "symbol, exchange, market_type, open_time DESC"),
    # positioning 补充时间降序
    ("idx_positioning_time_desc", "positioning_snapshots", "symbol, exchange, timestamp DESC"),
    # basis 补充时间降序
    ("idx_basis_snapshots_time_desc", "basis_snapshots", "symbol, exchange, timestamp DESC"),
    # collection_runs 补充 status 索引
    ("idx_collection_runs_status", "collection_runs", "status, finished_at DESC"),
]

MARKET_DATA_INDEXES = [
    # macro_timeseries 补充 factor+time 复合索引
    ("idx_macro_ts_factor_time_desc", "macro_timeseries", "factor_id, observation_time DESC"),
    # onchain_timeseries
    ("idx_onchain_ts_factor_entity_time", "onchain_timeseries", "factor_id, entity_key, observation_time DESC"),
    # tokenomics_timeseries
    ("idx_tokenomics_ts_factor_entity_time", "tokenomics_timeseries", "factor_id, entity_key, observation_time DESC"),
    # options_timeseries
    ("idx_options_ts_factor_entity_time", "options_timeseries", "factor_id, entity_key, observation_time DESC"),
]

ANALYTICS_INDEXES = [
    # technical_indicators 补充 symbol+timeframe+time DESC
    ("idx_tech_ind_symbol_tf_time_desc", "technical_indicators", "symbol, timeframe, open_time DESC"),
    # merged_klines
    ("idx_merged_klines_symbol_tf_time_desc", "merged_klines", "symbol, timeframe, open_time DESC"),
]


def _apply_indexes(conn: sqlite3.Connection, indexes: list[tuple[str, str, str]]) -> int:
    """对给定连接执行索引创建，返回新建索引数。"""
    created = 0
    for index_name, table_name, columns in indexes:
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"
        try:
            conn.execute(sql)
            created += 1
        except sqlite3.OperationalError as exc:
            # 表不存在时跳过（模块尚未初始化）
            if "no such table" in str(exc).lower():
                logger.debug("跳过索引 {} — 表 {} 不存在", index_name, table_name)
            else:
                logger.warning("创建索引 {} 失败: {}", index_name, exc)
    return created


def ensure_indexes(
    exchange_conn: sqlite3.Connection | None = None,
    market_conn: sqlite3.Connection | None = None,
    analytics_conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """为所有已初始化的数据库补充优化索引。

    可单独传入某个域的连接，也可全部传入。
    返回 {domain: created_count}。
    """
    start = time.monotonic()
    results = {}

    if exchange_conn:
        results["exchange_data"] = _apply_indexes(exchange_conn, EXCHANGE_DATA_INDEXES)
        exchange_conn.commit()

    if market_conn:
        results["market_data"] = _apply_indexes(market_conn, MARKET_DATA_INDEXES)
        market_conn.commit()

    if analytics_conn:
        results["analytics"] = _apply_indexes(analytics_conn, ANALYTICS_INDEXES)
        analytics_conn.commit()

    elapsed = time.monotonic() - start
    total = sum(results.values())
    if total:
        logger.info("数据库索引优化完成: {} 个索引 ({:.1f}s) — {}", total, elapsed, results)
    return results


def ensure_all_indexes() -> dict[str, int]:
    """自动从 database.router 获取所有域连接并执行索引优化（含部分索引和覆盖索引）。"""
    try:
        from database.router import get_exchange_db, get_market_db, get_analytics_db
        results = ensure_indexes(
            exchange_conn=get_exchange_db().conn,
            market_conn=get_market_db().conn,
            analytics_conn=get_analytics_db().conn,
        )
        # 高级索引：部分索引 + 覆盖索引
        try:
            from database.partial_indexes import ensure_all_advanced_indexes
            for db_getter in (get_exchange_db, get_market_db, get_analytics_db):
                adv = ensure_all_advanced_indexes(db_getter().conn)
                results["partial"] = results.get("partial", 0) + adv.get("partial", 0)
                results["covering"] = results.get("covering", 0) + adv.get("covering", 0)
        except Exception as exc:
            logger.debug("高级索引创建跳过: {}", exc)
        return results
    except Exception as exc:
        logger.warning("自动索引优化失败: {}", exc)
        return {}
