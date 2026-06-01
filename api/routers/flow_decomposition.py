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


@router.get("/context")
def get_flow_decomposition_context() -> dict[str, Any]:
    """资金流分解 AI 上下文 bundle。"""
    from logic_layer.flow_decomposition.service import FlowDecompositionService
    service = FlowDecompositionService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
