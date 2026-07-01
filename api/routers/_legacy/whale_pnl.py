"""Whale PnL 路由 — 巨鲸钱包盈亏与智能资金分析端点。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.pagination import CursorParams, build_keyset_query, paginated_response

router = APIRouter(prefix="/whale-pnl", tags=["whale-pnl"])


@router.get("/portfolios")
def get_portfolios(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最新巨鲸投资组合（按总价值排序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM whale_portfolios ORDER BY total_value_usd DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "portfolios": rows}


@router.get("/top-performers")
def get_top_performers(
    limit: int = Query(20, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """24小时盈亏排行榜。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM whale_portfolios ORDER BY pnl_24h DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "top_performers": rows}


@router.get("/history")
def get_history(
    address: str = Query(..., description="钱包地址"),
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """指定地址的盈亏历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM whale_pnl_history WHERE address = ? ORDER BY timestamp DESC LIMIT ?",
        (address, limit),
    )
    return {"address": address, "count": len(rows), "history": rows}


@router.get("/aggregate")
def get_aggregate() -> dict[str, Any]:
    """智能资金汇总统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT "
        "COUNT(*) AS total_whales, "
        "SUM(total_value_usd) AS total_aum, "
        "AVG(pnl_24h) AS avg_pnl_24h, "
        "SUM(CASE WHEN pnl_24h > 0 THEN 1 ELSE 0 END) AS profitable_count "
        "FROM whale_portfolios",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"aggregate": rows[0]}


@router.get("/context")
def get_whale_pnl_context() -> dict[str, Any]:
    """巨鲸盈亏 AI 上下文 bundle。"""
    from data_layer.whale_wallet_pnl.service import WhaleWalletPnlService
    service = WhaleWalletPnlService()
    service.init_storage()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle


@router.get("/history/paginated")
def get_history_paginated(
    address: str = Query(..., description="钱包地址"),
    cursor: Optional[str] = Query(None, description="分页游标"),
    limit: int = Query(50, ge=1, le=1000, description="每页条数"),
) -> dict[str, Any]:
    """指定地址的盈亏历史（游标分页）。"""
    db = get_market_db()
    params = CursorParams(cursor=cursor, limit=limit)
    sql, sql_params = build_keyset_query(
        base_sql="SELECT rowid, * FROM whale_pnl_history WHERE address = ?",
        base_params=(address,),
        cursor_params=params,
        timestamp_col="timestamp",
        id_col="rowid",
    )
    rows = db.fetch_all(sql, sql_params)
    return paginated_response(rows, params, timestamp_col="timestamp", id_col="rowid")
