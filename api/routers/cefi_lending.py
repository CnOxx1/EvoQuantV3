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


@router.get("/context")
def get_cefi_lending_context() -> dict[str, Any]:
    """CeFi 借贷利率 AI 上下文 bundle。"""
    from data_layer.cefi_lending_rate.service import CefiLendingRateService
    service = CefiLendingRateService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
