"""MEV Data 路由 — MEV 智能数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/mev", tags=["mev"])


@router.get("/blocks")
def get_mev_blocks(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
    builder: str | None = Query(None, description="按 builder 过滤"),
) -> dict[str, Any]:
    """最近 MEV 区块数据。"""
    db = get_market_db()
    sql = "SELECT * FROM mev_blocks WHERE 1=1"
    params: list[Any] = []
    if builder:
        sql += " AND builder = ?"
        params.append(builder)
    sql += " ORDER BY block_number DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "blocks": rows}


@router.get("/aggregation")
def get_mev_aggregation(
    interval: str = Query("1h", description="聚合间隔: 1h"),
    limit: int = Query(24, ge=1, le=168, description="返回条数"),
) -> dict[str, Any]:
    """MEV 聚合数据（按时间窗口）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mev_agg WHERE interval = ? "
        "ORDER BY ts DESC LIMIT ?",
        (interval, limit),
    )
    return {"interval": interval, "count": len(rows), "aggregations": rows}


@router.get("/builder-ranking")
def get_builder_ranking(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    hours: int = Query(24, ge=1, le=168, description="统计时间窗口(小时)"),
) -> dict[str, Any]:
    """Builder 按 MEV 提取量排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT builder, SUM(mev_value) AS total_mev, COUNT(*) AS block_count "
        "FROM mev_blocks WHERE ts >= datetime('now', '-' || ? || ' hours') "
        "GROUP BY builder ORDER BY total_mev DESC LIMIT ?",
        (hours, limit),
    )
    return {"hours": hours, "count": len(rows), "ranking": rows}


@router.get("/sandwich-analysis")
def get_sandwich_analysis(
    limit: int = Query(24, ge=1, le=168, description="返回条数"),
) -> dict[str, Any]:
    """三明治攻击频率和量。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mev_sandwich WHERE 1=1 "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "sandwich_attacks": rows}


@router.get("/liquidation-pressure")
def get_liquidation_pressure(
    limit: int = Query(24, ge=1, le=168, description="返回条数"),
) -> dict[str, Any]:
    """清算 MEV 趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mev_liquidations ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "liquidation_pressure": rows}


@router.get("/concentration")
def get_builder_concentration(
    days: int = Query(7, ge=1, le=30, description="统计天数"),
) -> dict[str, Any]:
    """Builder 集中度（HHI）趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM mev_concentration WHERE ts >= date('now', '-' || ? || ' days') "
        "ORDER BY ts DESC",
        (days,),
    )
    return {"days": days, "count": len(rows), "concentration": rows}


@router.get("/context")
def get_mev_context() -> dict[str, Any]:
    """MEV AI 上下文 bundle。"""
    from data_layer.mev_data.service import MevDataService
    service = MevDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
