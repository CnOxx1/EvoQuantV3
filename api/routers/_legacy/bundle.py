"""Bundle 路由 — AI 市场上下文 bundle 查询。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import get_ai_market_context_service
from config.symbols import TARGET_SYMBOLS
from logic_layer.decision_handoff.service import DecisionHandoffService

router = APIRouter(prefix="/bundle", tags=["bundle"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


def _require_symbol(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol '{normalized}' not in universe. "
            f"Available: {TARGET_SYMBOLS}",
        )
    return normalized


def _entity_key(symbol: str) -> str:
    return _normalize_symbol(symbol).split("/", 1)[0]


@router.get("/{symbol}/handoff")
def get_bundle_handoff(symbol: str) -> dict[str, Any]:
    """Data-end → decision-layer handoff proxy (no LLM).

    Abstains when ``should_ai_abstain`` is true; otherwise acts on disclosed
    PIT tilts. This is the callable proof that an open valve can be consumed.
    """
    normalized = _require_symbol(symbol)
    entity = _entity_key(normalized)
    svc = get_ai_market_context_service()
    try:
        bundle = svc.build_bundle_for_entity(entity)
    except Exception as e:
        logger.error("handoff build failed for {}: {}: {}", normalized, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

    decision = DecisionHandoffService(require_open_valve=True).act(bundle)
    wmi = bundle.get("world_model_index") or {}
    return {
        "symbol": normalized,
        "entity_key": entity,
        "world_model_index": {
            "wmi": wmi.get("wmi"),
            "should_ai_abstain": wmi.get("should_ai_abstain"),
            "band_scope": wmi.get("band_scope"),
            "archive_complete": wmi.get("archive_complete"),
            "full_schema_wmi": wmi.get("full_schema_wmi"),
            "abstain_threshold": wmi.get("abstain_threshold"),
        },
        "decision": decision,
    }


@router.get("/{symbol}")
def get_bundle(symbol: str) -> dict[str, Any]:
    """获取指定资产的完整 AI 市场上下文 bundle。"""
    normalized = _require_symbol(symbol)
    svc = get_ai_market_context_service()
    try:
        bundle = svc.build_bundle_for_entity(_entity_key(normalized))
    except Exception as e:
        logger.error("bundle build failed for {}: {}: {}", normalized, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return bundle


@router.get("/")
def get_bundle_summary() -> dict[str, Any]:
    """获取所有资产的 bundle 摘要（WMI + quality_flag + handoff）。"""
    svc = get_ai_market_context_service()
    handoff = DecisionHandoffService(require_open_valve=True)
    results = {}
    for symbol in TARGET_SYMBOLS:
        try:
            bundle = svc.build_bundle_for_entity(_entity_key(symbol))
            decision = handoff.act(bundle)
            results[symbol] = {
                "data_quality_flag": bundle.get("data_quality_flag"),
                "coverage_score": bundle.get("coverage_score"),
                "world_model_index": bundle.get("world_model_index"),
                "handoff": {
                    "action": decision.get("action"),
                    "valve_open": decision.get("valve_open"),
                    "handoff": decision.get("handoff"),
                },
            }
        except Exception as e:
            logger.warning("bundle summary failed for {}: {}", symbol, e)
            results[symbol] = {"data_quality_flag": "error", "error": True}
    return {"symbols": results, "count": len(results)}
