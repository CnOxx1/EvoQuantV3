"""Retail FOMO 路由 — 散户情绪狂热指数端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/retail-fomo", tags=["retail-fomo"])


@router.get("/state")
def get_retail_fomo_state() -> dict[str, Any]:
    """当前 FOMO/FUD 状态。"""
    db = get_analytics_db()
    row = db.fetch_one(
        "SELECT * FROM retail_fomo_states ORDER BY ts DESC LIMIT 1",
    )
    return {"state": row}


@router.get("/history")
def get_retail_fomo_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
) -> dict[str, Any]:
    """历史 FOMO/FUD 数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM retail_fomo_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "history": rows}


@router.get("/contrarian")
def get_contrarian_signal(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """逆向信号数据。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM retail_fomo_states "
        "WHERE contrarian_signal IS NOT NULL "
        "ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "contrarian": rows}


@router.get("/components")
def get_fomo_components(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """FOMO 组成成分拆解（搜索热度、社交、上币热度、恐惧贪婪）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM retail_fomo_states ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "components": rows}


@router.get("/context")
def get_retail_fomo_context() -> dict[str, Any]:
    """散户情绪狂热 AI 上下文 bundle。"""
    from logic_layer.retail_fomo_index.service import RetailFomoIndexService
    service = RetailFomoIndexService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
