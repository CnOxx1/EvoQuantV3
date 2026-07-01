"""Liquid Staking 路由 — 流动性质押数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/liquid-staking", tags=["liquid-staking"])


@router.get("/positions")
def get_staking_positions(
    protocol: str | None = Query(None, description="按协议过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """质押仓位数据。"""
    db = get_market_db()
    sql = "SELECT * FROM staking_positions WHERE 1=1"
    params: list[Any] = []
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    sql += " ORDER BY collected_at DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "positions": rows}


@router.get("/validator-queue")
def get_validator_queue(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """验证者队列状态。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM validator_queue ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "queue": rows}


@router.get("/restaking")
def get_restaking_tvl(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """再质押 TVL 数据。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM restaking_tvl ORDER BY collected_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "restaking": rows}


@router.get("/apr-comparison")
def get_apr_comparison() -> dict[str, Any]:
    """各协议 APR 对比。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT protocol, staking_apr, total_staked, collected_at "
        "FROM staking_positions WHERE collected_at = "
        "(SELECT MAX(collected_at) FROM staking_positions) "
        "ORDER BY staking_apr DESC",
        (),
    )
    return {"count": len(rows), "comparison": rows}


@router.get("/context")
def get_liquid_staking_context() -> dict[str, Any]:
    """流动性质押 AI 上下文 bundle。"""
    from data_layer.liquid_staking_data.service import LiquidStakingDataService
    service = LiquidStakingDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
