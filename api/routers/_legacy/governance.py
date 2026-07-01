"""治理投票路由 — DAO 治理数据端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_market_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/proposals")
def get_proposals(
    protocol: str | None = Query(None, description="按协议过滤"),
    state: str | None = Query(None, description="active/closed/pending"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """治理提案列表。"""
    db = get_market_db()
    sql = "SELECT * FROM governance_proposals WHERE 1=1"
    params: list[Any] = []
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    if state:
        sql += " AND state = ?"
        params.append(state.lower())
    sql += " ORDER BY start_ts DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "proposals": rows}


@router.get("/votes/{proposal_id}")
def get_proposal_votes(
    proposal_id: str,
    limit: int = Query(100, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """指定提案的投票详情。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM governance_votes WHERE proposal_id = ? "
        "ORDER BY voting_power DESC LIMIT ?",
        (proposal_id, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No votes for {proposal_id}")
    return {"proposal_id": proposal_id, "count": len(rows), "votes": rows}


@router.get("/activity")
def get_governance_activity(
    protocol: str | None = Query(None, description="按协议过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """各协议治理活跃度指标。"""
    db = get_market_db()
    sql = "SELECT * FROM governance_activity WHERE 1=1"
    params: list[Any] = []
    if protocol:
        sql += " AND protocol = ?"
        params.append(protocol.lower())
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = db.fetch_all(sql, tuple(params))
    return {"count": len(rows), "activity": rows}


@router.get("/whale-votes")
def get_whale_votes(
    min_power: float = Query(100000, ge=0, description="最小投票权重 USD"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """大户投票记录（按投票权重排序）。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM governance_votes WHERE voting_power >= ? "
        "ORDER BY voting_power DESC LIMIT ?",
        (min_power, limit),
    )
    return {"min_power": min_power, "count": len(rows), "whale_votes": rows}


@router.get("/participation")
def get_participation_trend(
    protocol: str = Query("aave.eth", description="协议"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """投票参与率趋势。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT participation_rate, whale_vote_pct, proposals_active, timestamp "
        "FROM governance_activity WHERE protocol = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (protocol.lower(), limit),
    )
    return {"protocol": protocol, "count": len(rows), "trend": rows}


@router.get("/quorum-risk")
def get_quorum_risk() -> dict[str, Any]:
    """未达法定人数风险的提案。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM governance_proposals WHERE state = 'active' "
        "AND quorum_pct < 50 ORDER BY quorum_pct ASC",
        (),
    )
    return {"count": len(rows), "at_risk_proposals": rows}


@router.get("/protocol-ranking")
def get_protocol_ranking() -> dict[str, Any]:
    """按活跃度排名各协议。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT protocol, proposals_active, participation_rate, whale_vote_pct "
        "FROM governance_activity WHERE timestamp = "
        "(SELECT MAX(timestamp) FROM governance_activity) "
        "ORDER BY proposals_active DESC",
        (),
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/context")
def get_governance_context() -> dict[str, Any]:
    """治理投票 AI 上下文 bundle。"""
    from data_layer.governance_data.service import GovernanceDataService
    service = GovernanceDataService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
