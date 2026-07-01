"""Anomaly 路由 — 异常检测端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _normalize_symbol
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/recent")
def get_recent_anomalies(
    symbol: str | None = Query(None, description="按资产过滤"),
    severity: str | None = Query(None, description="按严重度过滤: critical/warning/info"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近检测到的异常事件列表。"""
    db = get_analytics_db()
    sql = "SELECT * FROM anomalies WHERE 1=1"
    params: list[Any] = []
    if symbol:
        normalized = _normalize_symbol(symbol)
        sql += " AND symbol = ?"
        params.append(normalized)
    if severity:
        sql += " AND severity = ?"
        params.append(severity.lower())
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "anomalies": rows}


@router.get("/active/{symbol}")
def get_active_anomalies(symbol: str) -> dict[str, Any]:
    """单资产当前活跃异常。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not in universe")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM anomalies WHERE symbol = ? "
        "AND ts >= datetime('now', '-1 hour') ORDER BY ts DESC",
        (normalized,),
    )
    return {"symbol": normalized, "active_count": len(rows), "anomalies": rows}


@router.get("/market-risk")
def get_market_risk() -> dict[str, Any]:
    """市场整体异常风险评估。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT severity, COUNT(*) as cnt FROM anomalies "
        "WHERE ts >= datetime('now', '-1 hour') GROUP BY severity",
    )
    severity_map = {r.get("severity"): r.get("cnt", 0) for r in rows}
    critical = severity_map.get("critical", 0)
    warning = severity_map.get("warning", 0)
    total = sum(severity_map.values())
    if critical >= 3:
        risk_level = "high"
    elif critical >= 1 or warning >= 5:
        risk_level = "elevated"
    else:
        risk_level = "normal"
    recent_symbols = db.fetch_all(
        "SELECT DISTINCT symbol FROM anomalies "
        "WHERE ts >= datetime('now', '-1 hour') AND severity IN ('critical', 'warning')",
    )
    return {
        "risk_level": risk_level,
        "anomalies_1h": total,
        "critical_count": critical,
        "warning_count": warning,
        "affected_symbols": [r.get("symbol") for r in recent_symbols],
        "data_source": "anomaly_detection",
    }
