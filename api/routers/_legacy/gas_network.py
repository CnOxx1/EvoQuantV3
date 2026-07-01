"""Gas 与网络拥堵路由 — 以太坊 Gas 和网络状态端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/gas-network", tags=["gas-network"])


@router.get("/current")
def get_current_gas() -> dict[str, Any]:
    """当前 Gas 价格。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM gas_prices ORDER BY block_number DESC LIMIT 1",
        (),
    )
    if not rows:
        return {"status": "no_data"}
    return {"gas": rows[0]}


@router.get("/history")
def get_gas_history(
    hours: int = Query(24, ge=1, le=168, description="历史小时数"),
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """Gas 价格历史趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM gas_prices WHERE timestamp >= datetime('now', '-' || ? || ' hours') "
        "ORDER BY block_number DESC LIMIT ?",
        (hours, limit),
    )
    return {"hours": hours, "count": len(rows), "history": rows}


@router.get("/congestion")
def get_congestion(
    limit: int = Query(24, ge=1, le=168, description="返回条数"),
) -> dict[str, Any]:
    """网络拥堵状态。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM network_congestion ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "congestion": rows}


@router.get("/spikes")
def get_gas_spikes(
    hours: int = Query(24, ge=1, le=168, description="时间窗口"),
) -> dict[str, Any]:
    """Gas 异常飙升事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM gas_spikes WHERE timestamp >= datetime('now', '-' || ? || ' hours') "
        "ORDER BY spike_ratio DESC",
        (hours,),
    )
    return {"hours": hours, "count": len(rows), "spikes": rows}


@router.get("/avg-fee")
def get_avg_fee(
    hours: int = Query(6, ge=1, le=72, description="统计时间窗口"),
) -> dict[str, Any]:
    """平均 Gas 费用统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT AVG(base_fee_gwei) as avg_base, AVG(priority_fee_gwei) as avg_priority, "
        "MAX(base_fee_gwei) as max_base, MIN(base_fee_gwei) as min_base "
        "FROM gas_prices WHERE timestamp >= datetime('now', '-' || ? || ' hours')",
        (hours,),
    )
    if not rows or rows[0].get("avg_base") is None:
        return {"hours": hours, "status": "no_data"}
    return {"hours": hours, "stats": rows[0]}


@router.get("/utilization")
def get_block_utilization(
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """区块 Gas 利用率趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT block_number, gas_used_ratio, base_fee_gwei, timestamp "
        "FROM gas_prices ORDER BY block_number DESC LIMIT ?",
        (limit,),
    )
    avg_util = sum(_safe_float(r.get("gas_used_ratio")) or 0 for r in rows) / max(len(rows), 1)
    return {"avg_utilization": round(avg_util, 4), "count": len(rows), "blocks": rows}


@router.get("/context")
def get_gas_network_context() -> dict[str, Any]:
    """Gas 与网络拥堵 AI 上下文 bundle。"""
    from data_layer.gas_network_data.service import GasNetworkService
    service = GasNetworkService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
