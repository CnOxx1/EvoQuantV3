"""Contagion Risk 路由 — 传染风险端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/contagion-risk", tags=["contagion-risk"])


@router.get("/metrics")
def get_contagion_metrics(
    symbol: str | None = Query(None, description="按标的过滤"),
) -> dict[str, Any]:
    """最新传染风险指标。"""
    db = get_analytics_db()
    if symbol:
        rows = db.fetch_all(
            "SELECT * FROM contagion_metrics WHERE symbol = ? "
            "ORDER BY ts DESC LIMIT 10",
            (symbol.upper(),),
        )
    else:
        rows = db.fetch_all(
            "SELECT * FROM contagion_metrics "
            "ORDER BY ts DESC LIMIT 50",
        )
    return {"count": len(rows), "metrics": rows}


@router.get("/cascade")
def get_cascade_risk() -> dict[str, Any]:
    """当前级联风险评估。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM cascade_risk ORDER BY ts DESC LIMIT 10",
    )
    return {"count": len(rows), "cascade_risks": rows}


@router.get("/context")
def get_contagion_context() -> dict[str, Any]:
    """传染风险 AI 上下文 bundle。"""
    from logic_layer.contagion_risk.service import ContagionRiskService
    service = ContagionRiskService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
