"""v3 DeFi — DeFi 协议统一入口。

端点：
  /defi/liquidations         — 最近清算事件
  /defi/liquidations/by-protocol — 按协议
  /defi/health-factors       — 健康因子分布
  /defi/stress               — DeFi 压力指数
  /defi/governance/proposals — 治理提案
  /defi/governance/votes     — 投票记录
  /defi/smart-money          — Smart Money 信念
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db

router = APIRouter(prefix="/defi", tags=["defi"])


@router.get("/liquidations")
def get_liquidations(
    limit: int = Query(20, ge=1, le=200, description="条数"),
) -> dict[str, Any]:
    """最近清算事件。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_liquidations ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "liquidations": [dict(r) for r in rows]}


@router.get("/liquidations/by-protocol")
def get_liquidations_by_protocol(
    protocol: str = Query("aave", description="协议名称"),
    limit: int = Query(50, ge=1, le=500, description="条数"),
) -> dict[str, Any]:
    """指定协议的清算记录。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM defi_liquidations WHERE protocol = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (protocol, limit),
    )
    return {"protocol": protocol, "count": len(rows), "liquidations": [dict(r) for r in rows]}


@router.get("/health-factors")
def get_health_factors() -> dict[str, Any]:
    """健康因子分布。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM health_factor_distribution ORDER BY timestamp DESC LIMIT 1", ()
    )
    if not rows:
        return {"status": "no_data"}
    return {"health_factors": dict(rows[0])}


@router.get("/stress")
def get_stress() -> dict[str, Any]:
    """DeFi 压力指数。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM defi_stress_states ORDER BY ts DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No DeFi stress data.")
    return dict(row)


@router.get("/governance/proposals")
def get_proposals(
    status: str | None = Query(None, description="过滤: active/closed/pending"),
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """治理提案。"""
    db = get_market_db()
    if status:
        rows = db.fetch_all(
            "SELECT proposal_id, title, protocol, status, start_time, end_time, votes_for, votes_against "
            "FROM governance_proposals WHERE status = ? "
            "ORDER BY start_time DESC LIMIT ?",
            (status, limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT proposal_id, title, protocol, status, start_time, end_time, votes_for, votes_against "
            "FROM governance_proposals ORDER BY start_time DESC LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No proposals found.")
    return {"count": len(rows), "proposals": [dict(r) for r in rows]}


@router.get("/governance/votes")
def get_votes(
    proposal_id: str | None = Query(None, description="提案 ID"),
    limit: int = Query(20, ge=1, le=100, description="条数"),
) -> dict[str, Any]:
    """投票记录。"""
    db = get_market_db()
    if proposal_id:
        rows = db.fetch_all(
            "SELECT voter, choice, voting_power, timestamp "
            "FROM governance_votes WHERE proposal_id = ? "
            "ORDER BY voting_power DESC LIMIT ?",
            (proposal_id, limit),
        )
    else:
        rows = db.fetch_all(
            "SELECT proposal_id, voter, choice, voting_power, timestamp "
            "FROM governance_votes ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No votes found.")
    return {"count": len(rows), "votes": [dict(r) for r in rows]}


@router.get("/smart-money")
def get_smart_money() -> dict[str, Any]:
    """Smart Money 信念指数。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM smart_money_conviction_states ORDER BY ts DESC LIMIT 1", ()
    )
    if not row:
        raise HTTPException(status_code=404, detail="No smart money data.")
    return dict(row)
