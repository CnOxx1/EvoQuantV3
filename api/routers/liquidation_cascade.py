"""清算级联预测路由 — 清算风险分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/liquidation-cascade", tags=["liquidation-cascade"])


@router.get("/clusters")
def get_liquidation_clusters(
    symbol: str | None = Query(None, description="按交易对过滤"),
    direction: str | None = Query(None, description="long/short"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """清算价格聚集区域。"""
    db = get_analytics_db()
    sql = "SELECT * FROM liquidation_clusters WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    if direction:
        sql += " AND direction = ?"
        params.append(direction.lower())
    sql += " ORDER BY total_size_usd DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "clusters": rows}


@router.get("/cascade-risk")
def get_cascade_risk(
    symbol: str | None = Query(None, description="按交易对过滤"),
    min_probability: float = Query(0.0, ge=0, le=1, description="最小概率阈值"),
) -> dict[str, Any]:
    """级联清算风险评估。"""
    db = get_analytics_db()
    sql = "SELECT * FROM cascade_risk WHERE cascade_probability >= ?"
    params: list[Any] = [min_probability]
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " ORDER BY cascade_probability DESC"
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "risks": rows}


@router.get("/heatmap/{symbol}")
def get_liquidation_heatmap(
    symbol: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """清算热力图（价格区间清算密度）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM liquidation_heatmap WHERE symbol = ? "
        "ORDER BY price_from",
        (symbol.upper(),),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No heatmap for {symbol}")
    return {"symbol": symbol.upper(), "count": len(rows), "heatmap": rows}


@router.get("/critical-levels")
def get_critical_levels(
    severity: str = Query("critical", description="severity 过滤: critical/high/medium"),
) -> dict[str, Any]:
    """高危清算触发价位。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM cascade_risk WHERE severity = ? "
        "ORDER BY estimated_liquidation_usd DESC",
        (severity.lower(),),
    )
    return {"severity": severity, "count": len(rows), "critical_levels": rows}


@router.get("/leverage-distribution")
def get_leverage_distribution(
    symbol: str | None = Query(None, description="按交易对过滤"),
) -> dict[str, Any]:
    """杠杆分布统计。"""
    db = get_analytics_db()
    sql = "SELECT symbol, AVG(leverage_avg) as avg_leverage, "
    sql += "MAX(leverage_avg) as max_leverage, COUNT(*) as cluster_count "
    sql += "FROM liquidation_clusters WHERE 1=1"
    params: list[Any] = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol.upper())
    sql += " GROUP BY symbol ORDER BY avg_leverage DESC"
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "leverage_distribution": rows}


@router.get("/proximity-alert")
def get_proximity_alerts(
    max_distance_pct: float = Query(5.0, ge=0, le=20, description="最大距离百分比"),
) -> dict[str, Any]:
    """距当前价格最近的清算集群（预警）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM liquidation_clusters WHERE distance_pct <= ? "
        "ORDER BY distance_pct ASC",
        (max_distance_pct,),
    )
    return {"max_distance_pct": max_distance_pct, "count": len(rows), "alerts": rows}


@router.get("/estimated-cascade")
def get_estimated_cascade(
    symbol: str = Query("BTC", description="交易对"),
) -> dict[str, Any]:
    """预估级联清算总量。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM cascade_risk WHERE symbol = ? "
        "ORDER BY cascade_probability DESC",
        (symbol.upper(),),
    )
    total_estimated = sum(_safe_float(r.get("estimated_liquidation_usd")) or 0 for r in rows)
    return {
        "symbol": symbol.upper(),
        "total_estimated_usd": total_estimated,
        "count": len(rows),
        "cascades": rows,
    }


@router.get("/context")
def get_liquidation_cascade_context() -> dict[str, Any]:
    """清算级联预测 AI 上下文 bundle。"""
    from logic_layer.liquidation_cascade.service import LiquidationCascadeService
    service = LiquidationCascadeService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
