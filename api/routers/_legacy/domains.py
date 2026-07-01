"""Domains 路由 — 单域数据查询。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import get_pipeline_latency_service
from api.models import DomainListItem, DomainsListResponse

router = APIRouter(prefix="/domains", tags=["domains"])

AVAILABLE_DOMAINS = [
    "klines",
    "technical_indicators",
    "feature_standardization",
    "cross_asset",
    "portfolio_risk",
    "macro_context",
    "market_breadth",
    "asset_readiness",
    "ai_market_context",
    "exchange_comparison",
    "news_sentiment",
    "pipeline_latency",
]


@router.get("/", response_model=DomainsListResponse)
def list_domains() -> DomainsListResponse:
    """列出所有可用域及其当前健康状态。"""
    svc = get_pipeline_latency_service()
    try:
        report = svc.measure_all()
    except Exception as e:
        logger.warning("domains health check failed: {}: {}", type(e).__name__, e)
        return DomainsListResponse(
            domains=[
                DomainListItem(name=d, status="unknown") for d in AVAILABLE_DOMAINS
            ]
        )

    items = []
    for name in AVAILABLE_DOMAINS:
        dl = report.domains.get(name)
        if dl:
            items.append(DomainListItem(
                name=name,
                status=dl.status,
                latest_data_time=dl.latest_data_time,
                latency_seconds=dl.latency_seconds,
            ))
        else:
            items.append(DomainListItem(name=name, status="not_tracked"))
    return DomainsListResponse(domains=items)
