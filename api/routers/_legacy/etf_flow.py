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


@router.get("/issuer-ranking")
def get_issuer_ranking(
    asset: str = Query("BTC", description="资产类型: BTC/ETH"),
    days: int = Query(7, ge=1, le=30, description="统计天数"),
) -> dict[str, Any]:
    """按净流入排名各发行商。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT issuer, SUM(net_flow) AS total_net_flow, COUNT(*) AS days_active "
        "FROM etf_daily_flows WHERE asset = ? AND date >= date('now', '-' || ? || ' days') "
        "GROUP BY issuer ORDER BY total_net_flow DESC",
        (asset.upper(), days),
    )
    return {"asset": asset.upper(), "days": days, "count": len(rows), "ranking": rows}


@router.get("/premium-discount/{asset}")
def get_premium_discount(
    asset: str,
    limit: int = Query(30, ge=1, le=90, description="返回条数"),
) -> dict[str, Any]:
    """ETF 溢价/折价追踪。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM etf_premium_discount WHERE asset = ? "
        "ORDER BY date DESC LIMIT ?",
        (asset.upper(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No premium/discount data for {asset}")
    return {"asset": asset.upper(), "count": len(rows), "premium_discount": rows}


@router.get("/flow-streak/{asset}")
def get_flow_streak(asset: str) -> dict[str, Any]:
    """连续流入/流出天数统计。"""
    db = get_market_db()
    row = db.fetch_one(
        "SELECT * FROM etf_flow_streaks WHERE asset = ? "
        "ORDER BY ts DESC LIMIT 1",
        (asset.upper(),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No streak data for {asset}")
    return dict(row)


@router.get("/anomalies")
def get_flow_anomalies(
    asset: str = Query("BTC", description="资产类型: BTC/ETH"),
    threshold: float = Query(2.0, ge=1.0, le=5.0, description="z-score 阈值"),
) -> dict[str, Any]:
    """异常流入检测（z-score 超阈值）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM etf_daily_flows WHERE asset = ? "
        "AND abs(z_score) >= ? ORDER BY date DESC LIMIT 30",
        (asset.upper(), threshold),
    )
    return {"asset": asset.upper(), "threshold": threshold, "count": len(rows), "anomalies": rows}


@router.get("/context")
def get_etf_flow_context() -> dict[str, Any]:
    """ETF 资金流 AI 上下文 bundle。"""
    from data_layer.etf_flow_data.service import EtfFlowDataService
    service = EtfFlowDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
