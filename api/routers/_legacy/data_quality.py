"""Data Quality 路由 — 数据质量审计、资产就绪度、市场结构、采集运行。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


@router.get("/audit/latest")
def get_audit_latest() -> dict[str, Any]:
    """返回最新数据质量审计快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM data_quality_audit_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No audit data found.")

    data = dict(row)
    for field in ("critical_gap_band_names_json", "blocked_band_names_json",
                  "partial_band_names_json", "bands_json"):
        if data.get(field):
            try:
                key = field.replace("_json", "")
                data[key] = json.loads(data[field])
                del data[field]
            except (json.JSONDecodeError, KeyError):
                pass
    return data


@router.get("/audit/history")
def get_audit_history(
    limit: int = Query(48, ge=1, le=500, description="返回最近 N 条审计记录"),
) -> dict[str, Any]:
    """返回数据质量审计历史（摘要列）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT audit_scope, snapshot_time, world_model_status,
                  is_market_data_ready_for_ai, required_band_count,
                  required_ready_band_count, critical_gap_count
           FROM data_quality_audit_snapshots
           ORDER BY snapshot_time DESC
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No audit history found.")
    return {"count": len(rows), "history": [dict(r) for r in rows]}


@router.get("/readiness/latest")
def get_readiness_latest() -> dict[str, Any]:
    """返回最新资产就绪度快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM asset_readiness_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No readiness data found.")

    data = dict(row)
    if data.get("bundle_json"):
        try:
            data["bundle"] = json.loads(data["bundle_json"])
            del data["bundle_json"]
        except (json.JSONDecodeError, KeyError):
            pass
    return data


@router.get("/readiness/history")
def get_readiness_history(
    limit: int = Query(48, ge=1, le=500, description="返回最近 N 条就绪度记录"),
) -> dict[str, Any]:
    """返回资产就绪度趋势。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, scope_kind, market_world_status,
                  asset_count, ready_asset_count, partial_asset_count,
                  thin_asset_count, blocked_asset_count,
                  average_readiness_score, data_quality_flag
           FROM asset_readiness_snapshots
           ORDER BY snapshot_time DESC
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No readiness history found.")
    return {"count": len(rows), "history": [dict(r) for r in rows]}


@router.get("/market-structure")
def get_market_structure() -> dict[str, Any]:
    """返回最新市场结构快照。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM market_structure_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No market structure data found.")

    data = dict(row)
    if data.get("bundle_json"):
        try:
            data["bundle"] = json.loads(data["bundle_json"])
            del data["bundle_json"]
        except (json.JSONDecodeError, KeyError):
            pass
    return data


@router.get("/collection-runs")
def get_collection_runs(
    module: str | None = Query(None, description="按模块名过滤"),
    status: str | None = Query(None, description="按状态过滤"),
    limit: int = Query(50, ge=1, le=500, description="返回最近 N 条"),
) -> dict[str, Any]:
    """返回最近的数据采集运行记录。"""
    db = get_analytics_db()
    conditions = []
    params: list[Any] = []
    if module:
        conditions.append("module_name = ?")
        params.append(module)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = db.fetch_all(
        f"""SELECT module_name, source_name, job_name, status,
                   item_count, started_at, finished_at,
                   duration_seconds, message
            FROM collection_runs
            {where}
            ORDER BY started_at DESC
            LIMIT ?""",
        tuple(params),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No collection runs found.")
    return {"count": len(rows), "runs": [dict(r) for r in rows]}


@router.get("/availability-shocks")
def get_availability_shocks(
    start: str | None = Query(None, description="起始时间 ISO"),
    end: str | None = Query(None, description="结束时间 ISO"),
    module: str | None = Query(None, description="逗号分隔模块名过滤"),
    limit: int = Query(200, ge=1, le=5000, description="最多返回条数"),
) -> dict[str, Any]:
    """一等公民可用性冲击 \(O_t\)（collection_runs 失败/空跑 + 元数据标记）。

    对应论文 DAG 中的可观测可用性冲击，供 PIT 事件研究与种植冲击审计使用。
    """
    from data_layer.data_quality.availability import load_availability_shocks

    modules = [m.strip() for m in module.split(",") if m.strip()] if module else None
    shocks = load_availability_shocks(start=start, end=end, modules=modules, limit=limit)
    return {
        "object": "O_t",
        "count": len(shocks),
        "disclosure": (
            "Availability shocks from collection_runs (status error/empty) "
            "across split DBs; metadata may carry planted=true for audit designs."
        ),
        "shocks": shocks,
    }
