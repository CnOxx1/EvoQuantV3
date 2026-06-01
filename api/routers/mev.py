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


@router.get("/context")
def get_mev_context() -> dict[str, Any]:
    """MEV AI 上下文 bundle。"""
    from data_layer.mev_data.service import MevDataService
    service = MevDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
