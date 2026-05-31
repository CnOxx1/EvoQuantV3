"""Time Slice 路由 — 历史快照和特征历史查询。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.dependencies import get_time_slice_service

router = APIRouter(prefix="/time-slice", tags=["time-slice"])


@router.get("/")
def get_time_slice(
    timestamp: str = Query(..., description="ISO 格式时间戳，如 2025-05-20T12:00:00"),
    symbols: str | None = Query(None, description="逗号分隔的资产列表"),
    domains: str | None = Query(None, description="逗号分隔的域列表"),
) -> dict[str, Any]:
    """获取指定时间点的市场快照。"""
    try:
        ts = datetime.fromisoformat(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {timestamp}")

    symbol_list = [s.strip() for s in symbols.split(",")] if symbols else None
    domain_list = [d.strip() for d in domains.split(",")] if domains else None

    svc = get_time_slice_service()
    try:
        result = svc.get_slice_at(ts, symbols=symbol_list, domains=domain_list)
    except Exception as e:
        logger.error("time_slice failed at {}: {}: {}", timestamp, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return result.__dict__ if hasattr(result, "__dict__") else result


@router.get("/range")
def get_time_slice_range(
    start: str = Query(..., description="范围起始时间 ISO 格式"),
    end: str = Query(..., description="范围结束时间 ISO 格式"),
    interval: int = Query(3600, description="采样间隔秒数"),
    symbols: str | None = Query(None, description="逗号分隔的资产列表"),
    domains: str | None = Query(None, description="逗号分隔的域列表"),
) -> dict[str, Any]:
    """获取时间范围内的多个快照。"""
    try:
        ts_start = datetime.fromisoformat(start)
        ts_end = datetime.fromisoformat(end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {e}")

    symbol_list = [s.strip() for s in symbols.split(",")] if symbols else None
    domain_list = [d.strip() for d in domains.split(",")] if domains else None

    svc = get_time_slice_service()
    try:
        result = svc.get_slices_range(
            ts_start, ts_end, interval, symbols=symbol_list, domains=domain_list
        )
    except Exception as e:
        logger.error("time_slice range {}-{} failed: {}: {}", start, end, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return result.__dict__ if hasattr(result, "__dict__") else result


@router.get("/feature-history")
def get_feature_history(
    symbol: str = Query(..., description="资产符号，如 BTC/USDT"),
    start: str = Query(..., description="起始时间 ISO 格式"),
    end: str = Query(..., description="结束时间 ISO 格式"),
    features: str | None = Query(None, description="逗号分隔的特征名"),
    source: str = Query("technical_indicators", description="数据源"),
    timeframe: str = Query("1h", description="K线周期"),
) -> dict[str, Any]:
    """获取指定资产的连续特征历史序列。"""
    try:
        ts_start = datetime.fromisoformat(start)
        ts_end = datetime.fromisoformat(end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid timestamp: {e}")

    feature_list = [f.strip() for f in features.split(",")] if features else None

    svc = get_time_slice_service()
    try:
        result = svc.get_feature_history(
            symbol=symbol,
            start=ts_start,
            end=ts_end,
            features=feature_list,
            source=source,
            timeframe=timeframe,
        )
    except Exception as e:
        logger.error("feature_history {} failed: {}: {}", symbol, type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    return result.__dict__ if hasattr(result, "__dict__") else result
