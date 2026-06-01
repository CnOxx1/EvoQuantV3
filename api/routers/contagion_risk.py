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


@router.get("/systemic-score")
def get_systemic_score() -> dict[str, Any]:
    """系统性风险总评分。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM systemic_risk_score ORDER BY ts DESC LIMIT 1",
    )
    if not row:
        raise HTTPException(status_code=404, detail="No systemic score available")
    return dict(row)


@router.get("/covar/{symbol}")
def get_covar(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """单资产 CoVaR 分析。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM contagion_metrics WHERE symbol = ? AND metric_type = 'covar' "
        "ORDER BY ts DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No CoVaR data for {symbol}")
    return {"symbol": symbol.upper(), "count": len(rows), "covar": rows}


@router.get("/tail-beta/{symbol}")
def get_tail_beta(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """尾部 Beta 放大倍数。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM contagion_metrics WHERE symbol = ? AND metric_type = 'tail_beta' "
        "ORDER BY ts DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No tail beta data for {symbol}")
    return {"symbol": symbol.upper(), "count": len(rows), "tail_beta": rows}


@router.get("/stablecoin-health")
def get_stablecoin_health() -> dict[str, Any]:
    """稳定币脱锚概率。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM stablecoin_health ORDER BY ts DESC LIMIT 10",
    )
    return {"count": len(rows), "stablecoin_health": rows}


@router.get("/context")
def get_contagion_context() -> dict[str, Any]:
    """传染风险 AI 上下文 bundle。"""
    from logic_layer.contagion_risk.service import ContagionRiskService
    service = ContagionRiskService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
