"""Exchange Reserve 路由 — 交易所储备数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/exchange-reserve", tags=["exchange-reserve"])


@router.get("/balances")
def get_reserve_balances(
    asset: str | None = Query(None, description="按资产过滤 (BTC/ETH/USDT)"),
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """交易所储备余额。"""
    db = get_market_db()
    sql = "SELECT * FROM exchange_reserves WHERE 1=1"
    params: list[Any] = []
    if asset:
        sql += " AND asset = ?"
        params.append(asset.upper())
    if exchange:
        sql += " AND exchange = ?"
        params.append(exchange.lower())
    sql += " ORDER BY collected_at DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "reserves": rows}


@router.get("/netflow")
def get_netflow(
    asset: str = Query("BTC", description="资产"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """净流入/流出趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM reserve_changes WHERE asset = ? "
        "ORDER BY collected_at DESC LIMIT ?",
        (asset.upper(), limit),
    )
    return {"asset": asset.upper(), "count": len(rows), "flows": rows}


@router.get("/summary")
def get_reserve_summary() -> dict[str, Any]:
    """各资产储备汇总（最新）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT asset, SUM(reserve_balance) as total_reserve "
        "FROM exchange_reserves WHERE collected_at = "
        "(SELECT MAX(collected_at) FROM exchange_reserves) "
        "GROUP BY asset ORDER BY total_reserve DESC",
        (),
    )
    return {"count": len(rows), "summary": rows}


@router.get("/changes")
def get_reserve_changes(
    asset: str = Query("BTC", description="资产"),
) -> dict[str, Any]:
    """储备变化（24h/7d）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM reserve_changes WHERE asset = ? "
        "AND collected_at = (SELECT MAX(collected_at) FROM reserve_changes WHERE asset = ?) "
        "ORDER BY ABS(netflow_24h) DESC",
        (asset.upper(), asset.upper()),
    )
    return {"asset": asset.upper(), "count": len(rows), "changes": rows}


@router.get("/context")
def get_exchange_reserve_context() -> dict[str, Any]:
    """交易所储备 AI 上下文 bundle。"""
    from data_layer.exchange_reserve_data.service import ExchangeReserveDataService
    service = ExchangeReserveDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
