"""CeFi Lending Rate 路由 — CeFi 借贷利率端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/cefi-lending", tags=["cefi-lending"])


@router.get("/rates")
def get_lending_rates(
    asset: str = Query("BTC", description="资产"),
    platform: str | None = Query(None, description="平台过滤: binance/okx/bybit"),
) -> dict[str, Any]:
    """最新 CeFi 借贷利率。"""
    db = get_market_db()
    sql = "SELECT * FROM cefi_lending_rates WHERE asset = ?"
    params: list[Any] = [asset.upper()]
    if platform:
        sql += " AND platform = ?"
        params.append(platform.lower())
    sql += " ORDER BY ts DESC LIMIT 20"
    rows = db.fetch_all(sql, tuple(params))
    return {"asset": asset.upper(), "count": len(rows), "rates": rows}


@router.get("/spread")
def get_lending_spread(
    asset: str = Query("BTC", description="资产"),
) -> dict[str, Any]:
    """CeFi vs DeFi 利率价差。"""
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM lending_rate_spread WHERE asset = ? "
        "ORDER BY ts DESC LIMIT 1",
        (asset.upper(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No spread data for {asset}")
    return dict(row)


@router.get("/platform-ranking/{asset}")
def get_platform_ranking(
    asset: str,
    term: str = Query("flexible", description="期限: flexible/7d/30d"),
) -> dict[str, Any]:
    """各平台利率排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM cefi_lending_rates WHERE asset = ? AND term = ? "
        "AND ts = (SELECT MAX(ts) FROM cefi_lending_rates WHERE asset = ? AND term = ?) "
        "ORDER BY rate DESC",
        (asset.upper(), term, asset.upper(), term),
    )
    return {"asset": asset.upper(), "term": term, "count": len(rows), "ranking": rows}


@router.get("/inversion-signals")
def get_inversion_signals(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """利率倒挂检测（DeFi > CeFi）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM lending_rate_spread WHERE defi_rate > cefi_rate "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "inversions": rows}


@router.get("/rate-history/{asset}")
def get_rate_history(
    asset: str,
    platform: str | None = Query(None, description="平台过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """利率历史趋势。"""
    db = get_market_db()
    sql = "SELECT * FROM cefi_lending_rates WHERE asset = ?"
    params: list[Any] = [asset.upper()]
    if platform:
        sql += " AND platform = ?"
        params.append(platform.lower())
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"asset": asset.upper(), "count": len(rows), "rate_history": rows}


@router.get("/utilization/{asset}")
def get_utilization(
    asset: str,
    limit: int = Query(30, ge=1, le=90, description="返回条数"),
) -> dict[str, Any]:
    """资金利用率追踪。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM cefi_utilization WHERE asset = ? "
        "ORDER BY ts DESC LIMIT ?",
        (asset.upper(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No utilization data for {asset}")
    return {"asset": asset.upper(), "count": len(rows), "utilization": rows}


@router.get("/context")
def get_cefi_lending_context() -> dict[str, Any]:
    """CeFi 借贷利率 AI 上下文 bundle。"""
    from data_layer.cefi_lending_rate.service import CefiLendingRateService
    service = CefiLendingRateService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
