"""DeFi 路由 — DeFi 协议数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/defi", tags=["defi"])


@router.get("/tvl")
def get_tvl_ranking(
    chain: str | None = Query(None, description="按链过滤"),
    limit: int = Query(30, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """TVL 排名（按协议）。"""
    db = get_market_db()
    sql = "SELECT * FROM defi_tvl"
    params: list[Any] = []
    if chain:
        sql += " WHERE chain = ?"
        params.append(chain.lower())
    sql += " ORDER BY tvl_usd DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    total_tvl = sum(_safe_float(r.get("tvl_usd")) or 0 for r in rows)
    return {"count": len(rows), "total_tvl_usd": round(total_tvl, 2), "protocols": rows}


@router.get("/tvl/{protocol}")
def get_protocol_tvl(protocol: str) -> dict[str, Any]:
    """单协议 TVL 详情。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_tvl WHERE protocol = ?", (protocol.lower(),)
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Protocol {protocol} not found")
    return {"protocol": protocol, "chains": rows}


@router.get("/lending-rates")
def get_lending_rates(
    asset: str | None = Query(None, description="按资产过滤（如 USDC）"),
    protocol: str | None = Query(None, description="按协议过滤"),
) -> dict[str, Any]:
    """借贷利率一览。"""
    db = get_market_db()
    sql = "SELECT * FROM defi_lending_rates WHERE 1=1"
    params: list[Any] = []
    if asset:
        sql += " AND asset = ?"
        params.append(asset.upper())
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    sql += " ORDER BY supply_apy DESC"
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "rates": rows}


@router.get("/dex-volume")
def get_dex_volume(
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
) -> dict[str, Any]:
    """DEX 成交量排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_dex_volume ORDER BY volume_24h_usd DESC LIMIT ?",
        (limit,),
    )
    total_vol = sum(_safe_float(r.get("volume_24h_usd")) or 0 for r in rows)
    return {"count": len(rows), "total_volume_24h_usd": round(total_vol, 2), "dexes": rows}


@router.get("/summary")
def get_defi_summary() -> dict[str, Any]:
    """DeFi 整体概览。"""
    db = get_market_db()
    tvl_rows = db.fetch_all("SELECT tvl_usd FROM defi_tvl")
    dex_rows = db.fetch_all("SELECT volume_24h_usd FROM defi_dex_volume")
    rate_rows = db.fetch_all("SELECT supply_apy FROM defi_lending_rates WHERE asset = 'USDC'")
    total_tvl = sum(_safe_float(r.get("tvl_usd")) or 0 for r in tvl_rows)
    total_dex_vol = sum(_safe_float(r.get("volume_24h_usd")) or 0 for r in dex_rows)
    avg_usdc_apy = (
        sum(_safe_float(r.get("supply_apy")) or 0 for r in rate_rows) / len(rate_rows)
        if rate_rows else 0
    )
    return {
        "total_tvl_usd": round(total_tvl, 2),
        "total_dex_volume_24h_usd": round(total_dex_vol, 2),
        "avg_usdc_supply_apy": round(avg_usdc_apy, 4),
        "protocol_count": len(tvl_rows),
        "dex_count": len(dex_rows),
        "data_source": "defi_protocol_data",
    }
