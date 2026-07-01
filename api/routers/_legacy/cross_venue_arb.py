"""跨场所套利路由 — 跨交易所价差与套利检测端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/cross-venue-arb", tags=["cross-venue-arb"])


@router.get("/opportunities")
def get_arb_opportunities(
    symbol: str | None = Query(None, description="按交易对过滤"),
    min_spread_bps: float = Query(0, ge=0, description="最小价差 bps"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """当前套利机会。"""
    db = get_analytics_db()
    sql = "SELECT * FROM arb_opportunities WHERE spread_bps >= ?"
    params: list[Any] = [min_spread_bps]
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY spread_bps DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "opportunities": rows}


@router.get("/spreads")
def get_venue_spreads(
    symbol: str | None = Query(None, description="按交易对过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """各场所间价差快照。"""
    db = get_analytics_db()
    sql = "SELECT * FROM venue_spreads WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY mid_spread_bps DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "spreads": rows}


@router.get("/persistence")
def get_arb_persistence(
    symbol: str | None = Query(None, description="按交易对过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """套利机会持续性分析。"""
    db = get_analytics_db()
    sql = "SELECT * FROM arb_persistence WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY avg_spread_bps DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "persistence": rows}


@router.get("/efficiency-score")
def get_market_efficiency() -> dict[str, Any]:
    """市场效率评分（跨场所价格一致性）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT symbol, AVG(mid_spread_bps) as avg_spread, "
        "MAX(mid_spread_bps) as max_spread, COUNT(*) as venue_pairs "
        "FROM venue_spreads WHERE ts = (SELECT MAX(ts) FROM venue_spreads) "
        "GROUP BY symbol ORDER BY avg_spread DESC",
        (),
    )
    all_spreads = [_safe_float(r.get("avg_spread")) or 0 for r in rows]
    avg_all = sum(all_spreads) / max(len(all_spreads), 1)
    efficiency = max(0, 100 - avg_all * 10)
    return {
        "efficiency_score": round(efficiency, 2),
        "avg_spread_bps": round(avg_all, 2),
        "by_symbol": rows,
    }


@router.get("/venue-ranking")
def get_venue_ranking() -> dict[str, Any]:
    """各场所价格竞争力排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT venue_buy as venue, COUNT(*) as win_count, "
        "AVG(spread_bps) as avg_profit_bps "
        "FROM arb_opportunities WHERE ts = (SELECT MAX(ts) FROM arb_opportunities) "
        "GROUP BY venue_buy ORDER BY win_count DESC",
        (),
    )
    return {"count": len(rows), "venue_ranking": rows}


@router.get("/cross-type")
def get_cross_type_analysis() -> dict[str, Any]:
    """CEX-DEX vs CEX-CEX 套利类型分析。"""
    db = get_analytics_db()
    dex_venues = ("dydx", "hyperliquid", "gmx")
    rows = db.fetch_all(
        "SELECT * FROM arb_opportunities WHERE ts = "
        "(SELECT MAX(ts) FROM arb_opportunities) "
        "ORDER BY spread_bps DESC",
        (),
    )
    cex_dex = [r for r in rows if r.get("venue_buy") in dex_venues or r.get("venue_sell") in dex_venues]
    cex_cex = [r for r in rows if r.get("venue_buy") not in dex_venues and r.get("venue_sell") not in dex_venues]
    return {
        "cex_dex_count": len(cex_dex),
        "cex_cex_count": len(cex_cex),
        "cex_dex_opportunities": cex_dex[:10],
        "cex_cex_opportunities": cex_cex[:10],
    }


@router.get("/historical")
def get_arb_historical(
    symbol: str = Query("BTC", description="交易对"),
    hours: int = Query(24, ge=1, le=168, description="时间窗口"),
) -> dict[str, Any]:
    """历史套利机会频率。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM arb_opportunities WHERE symbol = ? "
        "AND ts >= datetime('now', '-' || ? || ' hours') "
        "ORDER BY ts DESC",
        (symbol.upper(), hours),
    )
    return {"symbol": symbol.upper(), "hours": hours, "count": len(rows), "history": rows}


@router.get("/context")
def get_cross_venue_arb_context() -> dict[str, Any]:
    """跨场所套利 AI 上下文 bundle。"""
    from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService
    service = CrossVenueArbService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
