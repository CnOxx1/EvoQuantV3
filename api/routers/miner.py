"""Miner 路由 — 矿工数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/miner", tags=["miner"])


@router.get("/metrics")
def get_miner_metrics(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """矿工指标历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM miner_metrics ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "metrics": rows}


@router.get("/metrics/latest")
def get_latest_miner_metrics() -> dict[str, Any]:
    """最新矿工指标。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM miner_metrics ORDER BY collected_at DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"latest": rows[0]}


@router.get("/hashrate")
def get_hashrate_history(
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """算力历史数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM hashrate_history ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "hashrate": rows}


@router.get("/puell")
def get_puell_multiple(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """Puell Multiple 历史。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT puell_multiple, miner_revenue_24h, collected_at "
        "FROM miner_metrics WHERE puell_multiple > 0 "
        "ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "puell_history": rows}


@router.get("/context")
def get_miner_context() -> dict[str, Any]:
    """矿工数据 AI 上下文 bundle。"""
    from data_layer.miner_data.service import MinerDataService
    service = MinerDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
