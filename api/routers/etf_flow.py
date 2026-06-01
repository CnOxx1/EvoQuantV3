"""ETF Flow 路由 — ETF 资金流端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/etf-flow", tags=["etf-flow"])


@router.get("/daily")
def get_daily_flows(
    asset: str = Query("BTC", description="资产类型: BTC/ETH"),
    days: int = Query(7, ge=1, le=90, description="返回天数"),
) -> dict[str, Any]:
    """ETF 每日资金流列表。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM etf_daily_flows WHERE asset = ? "
        "ORDER BY date DESC LIMIT ?",
        (asset.upper(), days),
    )
    return {"asset": asset.upper(), "count": len(rows), "flows": rows}


@router.get("/summary")
def get_flow_summary(
    asset: str = Query("BTC", description="资产类型: BTC/ETH"),
    days: int = Query(7, ge=1, le=30, description="返回天数"),
) -> dict[str, Any]:
    """ETF 资金流汇总（含累计净流入）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM etf_flow_summary WHERE asset = ? "
        "ORDER BY date DESC LIMIT ?",
        (asset.upper(), days),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No ETF flow summary for {asset}")
    return {"asset": asset.upper(), "count": len(rows), "summary": rows}


@router.get("/context")
def get_etf_flow_context() -> dict[str, Any]:
    """ETF 资金流 AI 上下文 bundle。"""
    from data_layer.etf_flow_data.service import EtfFlowDataService
    service = EtfFlowDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
