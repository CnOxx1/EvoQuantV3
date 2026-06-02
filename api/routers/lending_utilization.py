"""Lending Utilization 路由 — 借贷协议利用率端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/lending-utilization", tags=["lending-utilization"])


@router.get("/pools")
def get_current_pools(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """当前借贷池状态（按利用率降序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM lending_pools ORDER BY utilization_rate DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "pools": rows}


@router.get("/high-utilization")
def get_high_utilization_pools(
    threshold: float = Query(0.8, ge=0.0, le=1.0, description="利用率阈值"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """高利用率池（接近 kink 点）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM lending_pools WHERE utilization_rate > ? "
        "ORDER BY utilization_rate DESC LIMIT ?",
        (threshold, limit),
    )
    return {"threshold": threshold, "count": len(rows), "pools": rows}


@router.get("/by-protocol")
def get_pools_by_protocol(
    protocol: str = Query("aave", description="协议名称"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """按协议筛选借贷池。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM lending_pools WHERE protocol = ? "
        "ORDER BY utilization_rate DESC LIMIT ?",
        (protocol.lower(), limit),
    )
    return {"protocol": protocol.lower(), "count": len(rows), "pools": rows}


@router.get("/history")
def get_utilization_history(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """利用率历史快照。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM utilization_snapshots "
        "WHERE ts >= datetime('now', '-' || ? || ' days') "
        "ORDER BY ts DESC LIMIT ?",
        (days, limit),
    )
    return {"days": days, "count": len(rows), "snapshots": rows}


@router.get("/context")
def get_lending_utilization_context() -> dict[str, Any]:
    """借贷利用率 AI 上下文 bundle。"""
    from data_layer.lending_utilization.service import LendingUtilizationService
    service = LendingUtilizationService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
