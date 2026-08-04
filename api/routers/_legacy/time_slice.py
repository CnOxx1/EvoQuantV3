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
    from api.routers._helpers import validate_time_range
    ts_start, ts_end = validate_time_range(start, end)

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
    from api.routers._helpers import validate_time_range, validate_symbol
    ts_start, ts_end = validate_time_range(start, end)
    validated_symbol = validate_symbol(symbol)

    feature_list = [f.strip() for f in features.split(",")] if features else None

    svc = get_time_slice_service()
    try:
        result = svc.get_feature_history(
            symbol=validated_symbol,
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


@router.get("/paper-world-model")
def get_paper_world_model(
    date: str | None = Query(None, description="决策日 YYYY-MM-DD（previous-close clock）"),
    asset: str | None = Query(None, description="资产代码，如 BTC"),
    symbol: str | None = Query(None, description="交易对，如 BTC/USDT"),
    limit: int = Query(100, ge=1, le=5000, description="最多返回行数"),
) -> dict[str, Any]:
    """论文引擎世界模型对象（B,U,H,S,C,WMI,ACWMI,tilts）。

    ``acwmi_input_source`` 恒为 ``paper_engines``。生产代理 ACWMI 请走
    ``/ai-context`` / ``/health`` 中的 ``world_model_index``（可能为
    ``production_proxy``）。二者不可互换。
    """
    from pdf.sci.persist_paper_objects import load_paper_world_model

    rows = load_paper_world_model(date=date, asset=asset, symbol=symbol, limit=limit)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                "No paper_world_model_snapshots found. "
                "Run pdf/sci/run_pit_jf_experiments.py (or make paper-lab) first."
            ),
        )
    return {
        "count": len(rows),
        "acwmi_input_source": "paper_engines",
        "disclosure": (
            "Paper-engine S/C from return engines + PIT band content; "
            "not interchangeable with production_proxy ACWMI."
        ),
        "rows": rows,
    }
