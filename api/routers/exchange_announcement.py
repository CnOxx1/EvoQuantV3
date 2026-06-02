"""Exchange Announcement 路由 — 交易所公告端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.dependencies import get_market_db

router = APIRouter(prefix="/exchange-announcement", tags=["exchange-announcement"])


@router.get("/recent")
def get_recent_announcements(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """最近交易所公告列表。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM exchange_announcements ORDER BY published_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "announcements": rows}


@router.get("/listings")
def get_listing_events(
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """上币/下币事件列表。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM listing_events "
        "WHERE category IN ('listing', 'delisting') "
        "ORDER BY published_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "listings": rows}


@router.get("/by-exchange")
def get_announcements_by_exchange(
    exchange: str = Query("binance", description="交易所名称"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """按交易所筛选公告。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM exchange_announcements WHERE exchange = ? "
        "ORDER BY published_at DESC LIMIT ?",
        (exchange.lower(), limit),
    )
    return {"exchange": exchange.lower(), "count": len(rows), "announcements": rows}


@router.get("/by-token")
def get_announcements_by_token(
    token: str = Query(..., description="代币符号"),
    limit: int = Query(30, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """按代币筛选相关公告。"""
    db = get_market_db()
    rows = db.fetch_all(
        "SELECT * FROM exchange_announcements WHERE token = ? "
        "ORDER BY published_at DESC LIMIT ?",
        (token.upper(), limit),
    )
    return {"token": token.upper(), "count": len(rows), "announcements": rows}


@router.get("/context")
def get_exchange_announcement_context() -> dict[str, Any]:
    """交易所公告 AI 上下文 bundle。"""
    from data_layer.exchange_announcement.service import ExchangeAnnouncementService
    service = ExchangeAnnouncementService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
