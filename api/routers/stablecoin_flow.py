"""Stablecoin Flow 路由 — 稳定币铸造/销毁与链上资金流动分析端点。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.pagination import CursorParams, build_keyset_query, paginated_response

router = APIRouter(prefix="/stablecoin-flow", tags=["stablecoin-flow"])


@router.get("/latest")
def get_latest_mint_burns(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最新稳定币铸造/销毁事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM stablecoin_mint_burns ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "events": rows}


@router.get("/history")
def get_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史铸造/销毁记录。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM stablecoin_mint_burns ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/chain-flows")
def get_chain_flows(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """最新链上资金流动分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM stablecoin_chain_flows ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "chain_flows": rows}


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    """24小时稳定币铸造/销毁汇总统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT "
        "SUM(CASE WHEN action = 'mint' THEN amount ELSE 0 END) AS total_minted_24h, "
        "SUM(CASE WHEN action = 'burn' THEN amount ELSE 0 END) AS total_burned_24h, "
        "COUNT(*) AS event_count "
        "FROM stablecoin_mint_burns "
        "WHERE timestamp >= datetime('now', '-1 day')",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"summary": rows[0]}


@router.get("/context")
def get_stablecoin_flow_context() -> dict[str, Any]:
    """稳定币资金流 AI 上下文 bundle。"""
    from data_layer.stablecoin_flow_data.service import StablecoinFlowDataService
    service = StablecoinFlowDataService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle


@router.get("/events/paginated")
def get_events_paginated(
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(50, ge=1, le=1000, description="每页条数"),
) -> dict[str, Any]:
    """稳定币铸造/销毁事件（游标分页）。"""
    db = get_market_db()
    params = CursorParams(cursor=cursor, limit=limit)
    sql, sql_params = build_keyset_query(
        base_sql="SELECT rowid, * FROM stablecoin_mint_burns WHERE 1=1",
        base_params=(),
        cursor_params=params,
        timestamp_col="timestamp",
        id_col="rowid",
    )
    rows = db.fetch_all(sql, sql_params)
    return paginated_response(rows, params, timestamp_col="timestamp", id_col="rowid")
