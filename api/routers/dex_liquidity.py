"""DEX 流动性路由 — DEX 池子与流动性数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/dex-liquidity", tags=["dex-liquidity"])


@router.get("/pools")
def get_pools(
    protocol: str | None = Query(None, description="按协议过滤: uniswap_v3/curve"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """DEX 流动性池列表（按 TVL 排序）。"""
    db = get_market_db()
    sql = "SELECT * FROM dex_pools WHERE 1=1"
    params: list[Any] = []
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    sql += " ORDER BY tvl_usd DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "pools": rows}


@router.get("/tvl-distribution")
def get_tvl_distribution() -> dict[str, Any]:
    """各协议 TVL 分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT protocol, SUM(tvl_usd) as total_tvl, COUNT(*) as pool_count "
        "FROM dex_pools WHERE collected_at = "
        "(SELECT MAX(collected_at) FROM dex_pools) "
        "GROUP BY protocol ORDER BY total_tvl DESC",
        (),
    )
    return {"count": len(rows), "distribution": rows}


@router.get("/ticks/{pool_address}")
def get_tick_liquidity(
    pool_address: str,
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """指定池子的 tick 级流动性分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_tick_liquidity WHERE pool_address = ? "
        "ORDER BY tick_lower LIMIT ?",
        (pool_address.lower(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No tick data for {pool_address}")
    return {"pool_address": pool_address, "count": len(rows), "ticks": rows}


@router.get("/events")
def get_liquidity_events(
    protocol: str | None = Query(None, description="按协议过滤"),
    event_type: str | None = Query(None, description="mint/burn"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近流动性添加/移除事件。"""
    db = get_market_db()
    sql = "SELECT * FROM dex_liquidity_events WHERE 1=1"
    params: list[Any] = []
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    if event_type:
        sql += " AND event_type = ?"
        params.append(event_type.lower())
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "events": rows}


@router.get("/concentration")
def get_liquidity_concentration() -> dict[str, Any]:
    """流动性集中度分析（前 10 池占比）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT protocol, pool_address, token0, token1, tvl_usd "
        "FROM dex_pools WHERE collected_at = "
        "(SELECT MAX(collected_at) FROM dex_pools) "
        "ORDER BY tvl_usd DESC LIMIT 50",
        (),
    )
    total_tvl = sum(_safe_float(r.get("tvl_usd")) or 0 for r in rows)
    top10_tvl = sum(_safe_float(r.get("tvl_usd")) or 0 for r in rows[:10])
    concentration = top10_tvl / total_tvl if total_tvl > 0 else 0
    return {
        "total_tvl_usd": total_tvl,
        "top10_tvl_usd": top10_tvl,
        "top10_concentration": round(concentration, 4),
        "top_pools": rows[:10],
    }


@router.get("/large-events")
def get_large_events(
    min_usd: float = Query(100000, ge=0, description="最小金额 USD"),
    hours: int = Query(24, ge=1, le=168, description="时间窗口"),
) -> dict[str, Any]:
    """大额流动性事件（鲸鱼 LP 操作）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM dex_liquidity_events WHERE amount_usd >= ? "
        "AND timestamp >= datetime('now', '-' || ? || ' hours') "
        "ORDER BY amount_usd DESC",
        (min_usd, hours),
    )
    return {"min_usd": min_usd, "hours": hours, "count": len(rows), "events": rows}


@router.get("/context")
def get_dex_liquidity_context() -> dict[str, Any]:
    """DEX 流动性 AI 上下文 bundle。"""
    from data_layer.dex_liquidity_data.service import DexLiquidityService
    service = DexLiquidityService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
