"""Perpetual DEX 路由 — 永续 DEX 数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/perpetual-dex", tags=["perpetual-dex"])


@router.get("/funding")
def get_funding_rates(
    symbol: str | None = Query(None, description="按交易对过滤"),
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """各永续 DEX 的 funding rate 数据。"""
    db = get_market_db()
    sql = "SELECT * FROM perp_dex_funding WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    if exchange:
        sql += " AND exchange = ?"
        params.append(exchange.lower())
    sql += " ORDER BY collected_at DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "funding_rates": rows}


@router.get("/volume")
def get_dex_volume(
    symbol: str | None = Query(None, description="按交易对过滤"),
    exchange: str | None = Query(None, description="按交易所过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """永续 DEX 交易量数据。"""
    db = get_market_db()
    sql = "SELECT * FROM perp_dex_volume WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    if exchange:
        sql += " AND exchange = ?"
        params.append(exchange.lower())
    sql += " ORDER BY collected_at DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "volumes": rows}


@router.get("/funding-comparison")
def get_funding_comparison(
    symbol: str = Query("BTC", description="交易对"),
) -> dict[str, Any]:
    """跨交易所 funding rate 对比。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT exchange, symbol, funding_rate, open_interest_usd, collected_at "
        "FROM perp_dex_funding WHERE symbol = ? "
        "AND collected_at = (SELECT MAX(collected_at) FROM perp_dex_funding WHERE symbol = ?) "
        "ORDER BY funding_rate DESC",
        (symbol.upper(), symbol.upper()),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "comparison": rows}


@router.get("/oi-distribution")
def get_oi_distribution(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """各 DEX 的 Open Interest 分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT exchange, symbol, open_interest_usd, collected_at "
        "FROM perp_dex_funding WHERE collected_at = "
        "(SELECT MAX(collected_at) FROM perp_dex_funding) "
        "ORDER BY open_interest_usd DESC LIMIT ?",
        (limit,),
    )
    total_oi = sum(_safe_float(r.get("open_interest_usd")) or 0 for r in rows)
    return {"total_oi_usd": total_oi, "count": len(rows), "distribution": rows}


@router.get("/funding-history/{symbol}")
def get_funding_history(
    symbol: str,
    exchange: str = Query("hyperliquid", description="交易所"),
    hours: int = Query(24, ge=1, le=168, description="历史小时数"),
) -> dict[str, Any]:
    """单交易对 funding rate 历史趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT funding_rate, open_interest_usd, collected_at "
        "FROM perp_dex_funding WHERE symbol = ? AND exchange = ? "
        "ORDER BY collected_at DESC LIMIT ?",
        (symbol.upper(), exchange.lower(), hours * 4),
    )
    return {"symbol": symbol.upper(), "exchange": exchange, "count": len(rows), "history": rows}


@router.get("/arb-spread")
def get_arb_spread(
    symbol: str = Query("BTC", description="交易对"),
) -> dict[str, Any]:
    """DEX vs CEX funding rate 套利价差。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT exchange, funding_rate, collected_at "
        "FROM perp_dex_funding WHERE symbol = ? "
        "AND collected_at = (SELECT MAX(collected_at) FROM perp_dex_funding WHERE symbol = ?) "
        "ORDER BY funding_rate",
        (symbol.upper(), symbol.upper()),
    )
    if len(rows) < 2:
        return {"symbol": symbol.upper(), "spread_bps": 0, "venues": rows}
    rates = [_safe_float(r.get("funding_rate")) or 0 for r in rows]
    spread = (max(rates) - min(rates)) * 10000
    return {"symbol": symbol.upper(), "spread_bps": round(spread, 2), "venues": rows}


@router.get("/context")
def get_perpetual_dex_context() -> dict[str, Any]:
    """永续 DEX AI 上下文 bundle。"""
    from data_layer.perpetual_dex_data.service import PerpDexDataService
    service = PerpDexDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
