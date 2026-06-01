"""链上地址行为路由 — 鲸鱼追踪与地址画像端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/onchain-address", tags=["onchain-address"])


@router.get("/whale-moves")
def get_whale_moves(
    token: str | None = Query(None, description="按 token 过滤"),
    direction: str | None = Query(None, description="in/out"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近鲸鱼大额转账事件。"""
    db = get_market_db()
    sql = "SELECT * FROM whale_moves WHERE 1=1"
    params: list[Any] = []
    if token:
        sql += " AND token = ?"
        params.append(token.upper())
    if direction:
        sql += " AND direction = ?"
        params.append(direction.lower())
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "whale_moves": rows}


@router.get("/flows/{address}")
def get_address_flows(
    address: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """指定地址的资金流向。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM address_flows WHERE address = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (address.lower(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No flows for {address}")
    return {"address": address, "count": len(rows), "flows": rows}


@router.get("/labels")
def get_address_labels(
    category: str | None = Query(None, description="按分类过滤: fund/exchange/whale"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """已标记地址标签列表。"""
    db = get_market_db()
    sql = "SELECT * FROM address_labels WHERE 1=1"
    params: list[Any] = []
    if category:
        sql += " AND category = ?"
        params.append(category.lower())
    sql += " ORDER BY last_active DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "labels": rows}


@router.get("/net-flow")
def get_net_flow(
    token: str = Query("ETH", description="Token"),
    hours: int = Query(24, ge=1, le=168, description="统计时间窗口"),
) -> dict[str, Any]:
    """指定 token 的净流入/流出汇总。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT direction, SUM(amount_usd) as total_usd, COUNT(*) as tx_count "
        "FROM address_flows WHERE token = ? "
        "AND timestamp >= datetime('now', '-' || ? || ' hours') "
        "GROUP BY direction",
        (token.upper(), hours),
    )
    inflow = 0.0
    outflow = 0.0
    for r in rows:
        if r["direction"] == "in":
            inflow = _safe_float(r["total_usd"]) or 0
        else:
            outflow = _safe_float(r["total_usd"]) or 0
    return {
        "token": token.upper(),
        "hours": hours,
        "inflow_usd": inflow,
        "outflow_usd": outflow,
        "net_flow_usd": inflow - outflow,
        "direction": "net_inflow" if inflow > outflow else "net_outflow",
    }


@router.get("/top-movers")
def get_top_movers(
    hours: int = Query(24, ge=1, le=168, description="统计时间窗口"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """按转账金额排名的顶级地址。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT address, entity, SUM(amount_usd) as total_usd, COUNT(*) as tx_count "
        "FROM whale_moves WHERE timestamp >= datetime('now', '-' || ? || ' hours') "
        "GROUP BY address ORDER BY total_usd DESC LIMIT ?",
        (hours, limit),
    )
    return {"hours": hours, "count": len(rows), "top_movers": rows}


@router.get("/exchange-flow")
def get_exchange_flow(
    hours: int = Query(24, ge=1, le=168, description="统计时间窗口"),
) -> dict[str, Any]:
    """交易所资金净流入/流出。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT COALESCE(to_exchange, from_exchange) as exchange, "
        "direction, SUM(amount_usd) as total_usd, COUNT(*) as tx_count "
        "FROM whale_moves WHERE timestamp >= datetime('now', '-' || ? || ' hours') "
        "AND (from_exchange != '' OR to_exchange != '') "
        "GROUP BY exchange, direction ORDER BY total_usd DESC",
        (hours,),
    )
    return {"hours": hours, "count": len(rows), "exchange_flows": rows}


@router.get("/context")
def get_onchain_address_context() -> dict[str, Any]:
    """链上地址行为 AI 上下文 bundle。"""
    from data_layer.onchain_address_data.service import OnchainAddressService
    service = OnchainAddressService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
