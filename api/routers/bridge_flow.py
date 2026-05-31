"""Bridge Flow 路由 — 跨链桥资金流端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/bridge-flow", tags=["bridge-flow"])


@router.get("/chains")
def get_chain_flows(
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
) -> dict[str, Any]:
    """各链净流入/流出排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM chain_net_flows ORDER BY ABS(net_flow_usd) DESC LIMIT ?",
        (limit,),
    )
    inflow_chains = [r for r in rows if (_safe_float(r.get("net_flow_usd")) or 0) > 0]
    outflow_chains = [r for r in rows if (_safe_float(r.get("net_flow_usd")) or 0) < 0]
    return {
        "count": len(rows),
        "net_inflow_chains": len(inflow_chains),
        "net_outflow_chains": len(outflow_chains),
        "chains": rows,
    }


@router.get("/bridges")
def get_bridge_volumes(
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
) -> dict[str, Any]:
    """各桥成交量排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT bridge_name, SUM(volume_usd) as total_volume, "
        "SUM(tx_count) as total_txs FROM bridge_flows "
        "GROUP BY bridge_name ORDER BY total_volume DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "bridges": rows}


@router.get("/migration")
def get_migration_signals() -> dict[str, Any]:
    """资本迁移方向分析。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT chain, inflow_usd, outflow_usd, net_flow_usd, "
        "top_source_chain, top_dest_chain, dominant_token "
        "FROM chain_net_flows ORDER BY net_flow_usd DESC",
    )
    if not rows:
        return {"status": "no_data", "signals": []}
    l2_inflow = sum(
        _safe_float(r.get("net_flow_usd")) or 0
        for r in rows
        if r.get("chain", "").lower() in ("arbitrum", "optimism", "base", "zksync", "polygon")
    )
    l1_inflow = sum(
        _safe_float(r.get("net_flow_usd")) or 0
        for r in rows
        if r.get("chain", "").lower() in ("ethereum", "bitcoin")
    )
    direction = "l2_expansion" if l2_inflow > l1_inflow else "l1_consolidation"
    return {
        "migration_direction": direction,
        "l2_net_inflow_usd": round(l2_inflow, 2),
        "l1_net_inflow_usd": round(l1_inflow, 2),
        "chain_count": len(rows),
        "chains": rows,
        "data_source": "bridge_flow_data",
    }
