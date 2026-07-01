"""Cross-Chain Messaging 路由 — 跨链消息传递端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/cross-chain-msg", tags=["cross-chain-msg"])


@router.get("/latest")
def get_latest_messaging_stats(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """最新跨链消息统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM messaging_metrics ORDER BY ts DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "metrics": rows}


@router.get("/by-protocol")
def get_messages_by_protocol(
    protocol: str = Query("layerzero", description="协议名称"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """按协议筛选跨链消息。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM cross_chain_messages WHERE protocol = ? "
        "ORDER BY timestamp DESC LIMIT ?",
        (protocol.lower(), limit),
    )
    return {"protocol": protocol.lower(), "count": len(rows), "messages": rows}


@router.get("/volume")
def get_messaging_volume(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
) -> dict[str, Any]:
    """跨链消息量时序统计。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM messaging_metrics "
        "WHERE ts >= datetime('now', '-' || ? || ' days') ORDER BY ts ASC",
        (days,),
    )
    return {"days": days, "count": len(rows), "volume": rows}


@router.get("/chains")
def get_chain_activity_ranking(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """跨链消息活跃链排名。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM cross_chain_messages "
        "GROUP BY chain ORDER BY COUNT(*) DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "chains": rows}


@router.get("/context")
def get_cross_chain_msg_context() -> dict[str, Any]:
    """跨链消息 AI 上下文 bundle。"""
    from data_layer.cross_chain_messaging.service import CrossChainMessagingService
    service = CrossChainMessagingService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
