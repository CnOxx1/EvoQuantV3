"""DeFi Liquidation 路由 — DeFi 清算事件与健康因子分析端点。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.pagination import CursorParams, build_keyset_query, paginated_response

router = APIRouter(prefix="/defi-liquidation", tags=["defi-liquidation"])


@router.get("/recent")
def get_recent(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近清算事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_liquidations ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "liquidations": rows}


@router.get("/by-protocol")
def get_by_protocol(
    protocol: str = Query("aave", description="协议名称"),
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """指定协议的清算记录。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_liquidations WHERE protocol = ? ORDER BY timestamp DESC LIMIT ?",
        (protocol, limit),
    )
    return {"protocol": protocol, "count": len(rows), "liquidations": rows}


@router.get("/health-factors")
def get_health_factors() -> dict[str, Any]:
    """健康因子分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM health_factor_distribution ORDER BY timestamp DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"health_factors": rows[0]}


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    """清算汇总统计（总量与计数）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT "
        "COUNT(*) AS total_count, "
        "SUM(liquidation_amount_usd) AS total_volume_usd, "
        "AVG(liquidation_amount_usd) AS avg_amount_usd, "
        "MAX(liquidation_amount_usd) AS max_amount_usd "
        "FROM defi_liquidations "
        "WHERE timestamp >= datetime('now', '-1 day')",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"summary": rows[0]}


@router.get("/context")
def get_defi_liquidation_context() -> dict[str, Any]:
    """DeFi 清算 AI 上下文 bundle。"""
    from data_layer.defi_liquidation_data.service import DefiLiquidationDataService
    service = DefiLiquidationDataService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle


@router.get("/events/paginated")
def get_events_paginated(
    protocol: Optional[str] = Query(None, description="按协议过滤"),
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(50, ge=1, le=1000, description="每页条数"),
) -> dict[str, Any]:
    """DeFi 清算事件（游标分页）。"""
    db = get_market_db()
    params = CursorParams(cursor=cursor, limit=limit)
    if protocol:
        base_sql = "SELECT rowid, * FROM defi_liquidations WHERE protocol = ?"
        base_params = (protocol,)
    else:
        base_sql = "SELECT rowid, * FROM defi_liquidations WHERE 1=1"
        base_params = ()
    sql, sql_params = build_keyset_query(
        base_sql=base_sql,
        base_params=base_params,
        cursor_params=params,
        timestamp_col="timestamp",
        id_col="rowid",
    )
    rows = db.fetch_all(sql, sql_params)
    return paginated_response(rows, params, timestamp_col="timestamp", id_col="rowid")
