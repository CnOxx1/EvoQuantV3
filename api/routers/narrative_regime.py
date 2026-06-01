"""Narrative Regime 路由 — 叙事状态机端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/narrative-regime", tags=["narrative-regime"])


@router.get("/active")
def get_active_narratives(
    phase: str | None = Query(None, description="阶段过滤: emerging/growing/peak/decaying"),
) -> dict[str, Any]:
    """当前活跃的市场叙事列表。"""
    db = get_analytics_db()
    if phase:
        rows = db.fetch_all(
            "SELECT * FROM market_narratives WHERE lifecycle_phase = ? "
            "ORDER BY attention_score DESC LIMIT 20",
            (phase,),
        )
    else:
        rows = db.fetch_all(
            "SELECT * FROM market_narratives "
            "ORDER BY ts DESC, attention_score DESC LIMIT 30",
        )
    return {"count": len(rows), "narratives": rows}


@router.get("/transitions")
def get_narrative_transitions(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """叙事阶段转换记录。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM narrative_transitions ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "transitions": rows}


@router.get("/by-phase/{phase}")
def get_by_phase(phase: str) -> dict[str, Any]:
    """按生命周期阶段过滤。"""
    valid_phases = ("emerging", "growing", "peak", "decaying")
    if phase not in valid_phases:
        raise HTTPException(status_code=400, detail=f"Invalid phase. Must be one of: {valid_phases}")
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM market_narratives WHERE lifecycle_phase = ? "
        "ORDER BY attention_score DESC",
        (phase,),
    )
    return {"phase": phase, "count": len(rows), "narratives": rows}


@router.get("/attention-ranking")
def get_attention_ranking(
    limit: int = Query(20, ge=1, le=50, description="返回条数"),
) -> dict[str, Any]:
    """按注意力评分排名。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM market_narratives "
        "ORDER BY attention_score DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/tokens/{narrative_id}")
def get_narrative_tokens(narrative_id: str) -> dict[str, Any]:
    """叙事关联 token。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM narrative_tokens WHERE narrative_id = ? "
        "ORDER BY relevance_score DESC",
        (narrative_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No tokens for narrative {narrative_id}")
    return {"narrative_id": narrative_id, "count": len(rows), "tokens": rows}


@router.get("/emerging")
def get_emerging_narratives() -> dict[str, Any]:
    """新兴叙事（早期机会）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM market_narratives WHERE lifecycle_phase = 'emerging' "
        "ORDER BY ts DESC, attention_score DESC LIMIT 20",
    )
    return {"count": len(rows), "emerging": rows}


@router.get("/context")
def get_narrative_context() -> dict[str, Any]:
    """叙事状态机 AI 上下文 bundle。"""
    from logic_layer.narrative_regime.service import NarrativeRegimeService
    service = NarrativeRegimeService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
