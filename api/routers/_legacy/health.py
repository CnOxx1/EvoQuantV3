"""Health 路由 — 管道健康状态和 WMI 摘要。"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter
from loguru import logger

from api.dependencies import get_ai_market_context_service, get_pipeline_latency_service
from api.models import HealthSummary
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/health", tags=["health"])

HEALTH_STALE_THRESHOLD_MINUTES = int(
    os.environ.get("HEALTH_STALE_THRESHOLD_MINUTES", "30")
)


@router.get("/", response_model=HealthSummary)
def get_health() -> HealthSummary:
    """管道整体健康状态 + WMI 摘要。"""
    latency_svc = get_pipeline_latency_service()
    try:
        report = latency_svc.measure_all()
        domains = {
            name: {
                "status": dl.status,
                "latest_data_time": dl.latest_data_time,
                "latency_seconds": dl.latency_seconds,
            }
            for name, dl in report.domains.items()
        }
        summary = report.summary
        pipeline_status = summary.get("health", "unknown")
    except Exception as e:
        logger.warning("health latency check failed: {}: {}", type(e).__name__, e)
        domains = {}
        summary = {}
        pipeline_status = "unknown"

    # 取第一个 core 资产的 WMI 作为代表
    wmi_data: dict[str, Any] = {}
    try:
        svc = get_ai_market_context_service()
        bundle = svc.build_bundle_for_entity("BTC/USDT")
        wmi_data = bundle.get("world_model_index") or {}
    except Exception as e:
        logger.warning("health WMI check failed: {}: {}", type(e).__name__, e)

    return HealthSummary(
        status=pipeline_status,
        wmi=wmi_data.get("wmi"),
        interpretation=wmi_data.get("interpretation"),
        should_ai_abstain=wmi_data.get("should_ai_abstain"),
        measured_at=summary.get("measured_at") or report.measured_at if 'report' in dir() else None,
        domains=domains,
        summary=summary,
    )


@router.get("/db")
def get_db_health() -> dict:
    """数据库后端连接池健康状态。"""
    from database.router import DatabaseRouter
    try:
        dr = DatabaseRouter()
        return dr.get_backend_health()
    except Exception as e:
        logger.warning("health db check failed: {}: {}", type(e).__name__, e)
        return {"status": "error", "error": str(e)}


@router.get("/collectors")
def get_collector_health() -> dict:
    """按模块报告最近一次采集状态和数据新鲜度。"""
    from database.db_manager import DBManager

    db = DBManager()
    now = datetime.now(timezone.utc)
    threshold_seconds = HEALTH_STALE_THRESHOLD_MINUTES * 60

    try:
        rows = db.fetch_all("""
            SELECT module_name, status, item_count, finished_at,
                   ROW_NUMBER() OVER (PARTITION BY module_name ORDER BY finished_at DESC) AS rn
            FROM collection_runs
        """)
        # 只取每个模块最新一条
        latest = [r for r in rows if r["rn"] == 1]
    except Exception as e:
        logger.warning("health collectors check failed: {}: {}", type(e).__name__, e)
        return {"status": "error", "error": str(e)}

    modules = {}
    for row in latest:
        finished_at = row["finished_at"]
        if finished_at:
            try:
                if isinstance(finished_at, str):
                    ft = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                else:
                    ft = finished_at
                if ft.tzinfo is None:
                    ft = ft.replace(tzinfo=timezone.utc)
                age_seconds = (now - ft).total_seconds()
            except (ValueError, TypeError):
                age_seconds = None
        else:
            age_seconds = None

        module_status = row["status"]
        if age_seconds is not None and age_seconds > threshold_seconds:
            module_status = "stale"

        modules[row["module_name"]] = {
            "status": module_status,
            "last_run_at": str(finished_at) if finished_at else None,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "item_count": row["item_count"],
        }

    overall = "healthy"
    stale_count = sum(1 for m in modules.values() if m["status"] == "stale")
    error_count = sum(1 for m in modules.values() if m["status"] == "error")
    if stale_count > 0 or error_count > 0:
        overall = "degraded"

    return {
        "status": overall,
        "stale_threshold_minutes": HEALTH_STALE_THRESHOLD_MINUTES,
        "modules": modules,
        "summary": {
            "total": len(modules),
            "stale": stale_count,
            "error": error_count,
        },
    }


@router.get("/external")
async def get_external_health() -> dict:
    """探测关键外部 API 端点连通性。"""
    endpoints = {
        "binance": "https://api.binance.com/api/v3/ping",
        "coingecko": "https://api.coingecko.com/api/v3/ping",
        "deribit": "https://www.deribit.com/api/v2/public/test",
    }

    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in endpoints.items():
            start = time.time()
            try:
                resp = await client.get(url)
                latency_ms = round((time.time() - start) * 1000, 1)
                results[name] = {
                    "reachable": resp.status_code < 500,
                    "status_code": resp.status_code,
                    "latency_ms": latency_ms,
                }
            except Exception as e:
                latency_ms = round((time.time() - start) * 1000, 1)
                results[name] = {
                    "reachable": False,
                    "error": f"{type(e).__name__}: {e}",
                    "latency_ms": latency_ms,
                }

    all_reachable = all(r["reachable"] for r in results.values())
    return {
        "status": "healthy" if all_reachable else "degraded",
        "endpoints": results,
    }
