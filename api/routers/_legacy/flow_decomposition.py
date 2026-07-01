"""Flow Decomposition 路由 — 资金流分解端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _normalize_symbol

router = APIRouter(prefix="/flow-decomposition", tags=["flow-decomposition"])


@router.get("/vpin/{symbol}")
def get_vpin(symbol: str) -> dict[str, Any]:
    """获取 VPIN 最新值和历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM vpin_history WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 24",
        (_normalize_symbol(symbol),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No VPIN data for {symbol}")
    return {"symbol": symbol, "count": len(rows), "vpin_history": rows}


@router.get("/decomposition/{symbol}")
def get_flow_decomposition(symbol: str) -> dict[str, Any]:
    """获取资金流分解结果。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM flow_decomposition WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 1",
        (_normalize_symbol(symbol),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No decomposition for {symbol}")
    return dict(row)


@router.get("/smart-money/{symbol}")
def get_smart_money(symbol: str) -> dict[str, Any]:
    """Smart money 方向。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM smart_money_flow WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 24",
        (_normalize_symbol(symbol),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No smart money data for {symbol}")
    return {"symbol": symbol, "count": len(rows), "smart_money": rows}


@router.get("/accumulation/{symbol}")
def get_accumulation_phase(symbol: str) -> dict[str, Any]:
    """积累/派发阶段。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM accumulation_distribution WHERE symbol = ? "
        "ORDER BY ts DESC LIMIT 1",
        (_normalize_symbol(symbol),),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No accumulation data for {symbol}")
    return dict(row)


@router.get("/vpin-alerts")
def get_vpin_alerts(
    threshold: float = Query(0.8, ge=0.5, le=1.0, description="VPIN 阈值"),
) -> dict[str, Any]:
    """VPIN 高风险告警。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM vpin_history WHERE vpin >= ? "
        "ORDER BY ts DESC LIMIT 50",
        (threshold,),
    )
    return {"threshold": threshold, "count": len(rows), "alerts": rows}


@router.get("/ranking")
def get_vpin_ranking() -> dict[str, Any]:
    """全资产 VPIN 排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT symbol, vpin, ts FROM vpin_history WHERE ts = ("
        "SELECT MAX(ts) FROM vpin_history AS sub WHERE sub.symbol = vpin_history.symbol) "
        "ORDER BY vpin DESC",
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/context")
def get_flow_decomposition_context() -> dict[str, Any]:
    """资金流分解 AI 上下文 bundle。"""
    # v4.4.0: 使用单例服务替代逐请求实例化
    from api.dependencies import get_flow_decomposition_service
    service = get_flow_decomposition_service()
    return service.load_latest_context_bundle()
