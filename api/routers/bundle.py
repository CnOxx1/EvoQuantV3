"""Bundle 路由 — AI 市场上下文 bundle 查询。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api.dependencies import get_ai_market_context_service
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/bundle", tags=["bundle"])


@router.get("/{symbol}")
def get_bundle(symbol: str) -> dict[str, Any]:
    """获取指定资产的完整 AI 市场上下文 bundle。"""
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"

    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{normalized}' not in universe. "
            f"Available: {TARGET_SYMBOLS}",
        )

    svc = get_ai_market_context_service()
    try:
        bundle = svc.build_bundle_for_entity(normalized)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return bundle


@router.get("/")
def get_bundle_summary() -> dict[str, Any]:
    """获取所有资产的 bundle 摘要（WMI + quality_flag）。"""
    svc = get_ai_market_context_service()
    results = {}
    for symbol in TARGET_SYMBOLS:
        try:
            bundle = svc.build_bundle_for_entity(symbol)
            results[symbol] = {
                "data_quality_flag": bundle.get("data_quality_flag"),
                "coverage_score": bundle.get("coverage_score"),
                "world_model_index": bundle.get("world_model_index"),
            }
        except Exception:
            results[symbol] = {"data_quality_flag": "error", "error": True}
    return {"symbols": results, "count": len(results)}
