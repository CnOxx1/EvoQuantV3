"""Regulatory 路由 — 监管动态端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/regulatory", tags=["regulatory"])


@router.get("/events")
def get_events(
    jurisdiction: str | None = Query(None, description="按司法管辖区过滤: US/EU/CN/UK/JP/KR/global"),
    severity: str | None = Query(None, description="按严重度过滤: high/medium/low"),
    limit: int = Query(30, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """最近监管事件列表。"""
    db = get_market_db()
    sql = "SELECT * FROM regulatory_events WHERE 1=1"
    params: list[Any] = []
    if jurisdiction:
        sql += " AND jurisdiction = ?"
        params.append(jurisdiction.upper())
    if severity:
        sql += " AND impact_severity = ?"
        params.append(severity.lower())
    sql += " ORDER BY event_date DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "events": rows}


@router.get("/etf-tracker")
def get_etf_tracker() -> dict[str, Any]:
    """ETF 申请状态追踪。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM etf_tracker ORDER BY decision_deadline ASC",
    )
    return {"count": len(rows), "etfs": rows}


@router.get("/risk-signal")
def get_risk_signal() -> dict[str, Any]:
    """当前监管风险信号。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT impact_severity, COUNT(*) as cnt FROM regulatory_events "
        "WHERE event_date >= datetime('now', '-7 days') GROUP BY impact_severity",
    )
    severity_map = {r.get("impact_severity"): r.get("cnt", 0) for r in rows}
    high_count = severity_map.get("high", 0)
    medium_count = severity_map.get("medium", 0)
    total_7d = sum(severity_map.values())
    if high_count >= 3:
        risk_level = "elevated"
    elif high_count >= 1 or medium_count >= 5:
        risk_level = "moderate"
    else:
        risk_level = "low"
    return {
        "risk_level": risk_level,
        "events_7d": total_7d,
        "high_severity_7d": high_count,
        "medium_severity_7d": medium_count,
        "data_source": "regulatory_data",
    }


@router.get("/summary")
def get_regulatory_summary() -> dict[str, Any]:
    """监管环境概览。"""
    db = get_market_db()
    recent = db.fetch_all(
        "SELECT jurisdiction, event_type, COUNT(*) as cnt "
        "FROM regulatory_events WHERE event_date >= datetime('now', '-30 days') "
        "GROUP BY jurisdiction, event_type ORDER BY cnt DESC",
    )
    etfs = db.fetch_all("SELECT status, COUNT(*) as cnt FROM etf_tracker GROUP BY status")
    etf_status = {r.get("status"): r.get("cnt", 0) for r in etfs}
    return {
        "events_30d_by_jurisdiction": recent,
        "etf_status_summary": etf_status,
        "data_source": "regulatory_data",
    }
