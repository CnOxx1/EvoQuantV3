"""Health 路由 — 管道健康状态和 WMI 摘要。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.dependencies import get_ai_market_context_service, get_pipeline_latency_service
from api.models import HealthSummary
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/health", tags=["health"])


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
    except Exception:
        domains = {}
        summary = {}
        pipeline_status = "unknown"

    # 取第一个 core 资产的 WMI 作为代表
    wmi_data: dict[str, Any] = {}
    try:
        svc = get_ai_market_context_service()
        bundle = svc.build_bundle_for_entity("BTC/USDT")
        wmi_data = bundle.get("world_model_index") or {}
    except Exception:
        pass

    return HealthSummary(
        status=pipeline_status,
        wmi=wmi_data.get("wmi"),
        interpretation=wmi_data.get("interpretation"),
        should_ai_abstain=wmi_data.get("should_ai_abstain"),
        measured_at=summary.get("measured_at") or report.measured_at if 'report' in dir() else None,
        domains=domains,
        summary=summary,
    )
