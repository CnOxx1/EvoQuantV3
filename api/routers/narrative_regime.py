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


@router.get("/context")
def get_narrative_context() -> dict[str, Any]:
    """叙事状态机 AI 上下文 bundle。"""
    from logic_layer.narrative_regime.service import NarrativeRegimeService
    service = NarrativeRegimeService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
