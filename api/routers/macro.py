"""Macro 路由 — 宏观因子快照查询（利率、汇率、股指、VIX、商品等）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_market_db

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/latest")
def get_macro_latest() -> dict[str, Any]:
    """返回最新宏观上下文快照（AI 聚合后的结构化结果）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM macro_context_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(
            status_code=404,
            detail="No macro context data found. Run logic_pipeline first.",
        )

    data = dict(row)
    for field in list(data.keys()):
        if field.endswith("_json") and data[field]:
            try:
                key = field[:-5]
                data[key] = json.loads(data[field])
                del data[field]
            except (json.JSONDecodeError, KeyError):
                pass

    return data


@router.get("/history")
def get_macro_history(
    limit: int = Query(48, ge=1, le=500, description="返回最近 N 条宏观快照"),
) -> dict[str, Any]:
    """返回宏观上下文历史（用于趋势跟踪）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, risk_regime, macro_regime,
                  dxy_level, dxy_trend, us10y_level, us10y_trend,
                  vix_level, vix_regime,
                  btc_macro_tailwind, btc_macro_headwind
           FROM macro_context_snapshots
           ORDER BY snapshot_time DESC
           LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No macro history found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "count": len(records),
        "history": records,
    }


@router.get("/factors")
def get_macro_factors(
    factor_id: str | None = Query(None, description="指定因子 ID，如 dxy/vix/us10y"),
    limit: int = Query(100, ge=1, le=1000, description="返回最近 N 条时序数据"),
) -> dict[str, Any]:
    """返回原始宏观因子时序数据（DXY、VIX、利率等）。"""
    db = get_market_db()

    if factor_id:
        rows = db.fetch_all(
            """SELECT mts.factor_id, mts.value, mts.timestamp,
                      mfc.factor_name, mfc.unit
               FROM macro_timeseries mts
               LEFT JOIN macro_factor_catalog mfc ON mts.factor_id = mfc.factor_id
               WHERE mts.factor_id = ?
               ORDER BY mts.timestamp DESC
               LIMIT ?""",
            (factor_id, limit),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Factor '{factor_id}' not found.")
        records = [dict(r) for r in rows]
        records.reverse()
        return {"factor_id": factor_id, "count": len(records), "timeseries": records}

    # 返回所有因子的最新值
    rows = db.fetch_all(
        """SELECT mts.factor_id, mts.value, mts.timestamp,
                  mfc.factor_name, mfc.unit, mfc.source
           FROM macro_timeseries mts
           INNER JOIN (
               SELECT factor_id, MAX(timestamp) AS max_ts
               FROM macro_timeseries
               GROUP BY factor_id
           ) latest ON mts.factor_id = latest.factor_id AND mts.timestamp = latest.max_ts
           LEFT JOIN macro_factor_catalog mfc ON mts.factor_id = mfc.factor_id
           ORDER BY mts.factor_id""",
        (),
    )

    result: dict[str, Any] = {}
    for row in rows:
        d = dict(row)
        result[d["factor_id"]] = d

    return {
        "factor_count": len(result),
        "latest_values": result,
    }


@router.get("/regime")
def get_macro_regime() -> dict[str, Any]:
    """返回当前宏观市场情绪与风险环境摘要（给 Bridge 和 Dashboard 使用）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT snapshot_time, risk_regime, macro_regime,
                  dxy_level, dxy_trend, us10y_level, us10y_trend,
                  vix_level, vix_regime,
                  btc_macro_tailwind, btc_macro_headwind,
                  macro_summary
           FROM macro_context_snapshots
           ORDER BY snapshot_time DESC LIMIT 1""",
        (),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No macro regime data found.")

    data = dict(row)

    risk_on = (
        data.get("vix_regime") in ("low", "normal")
        and data.get("dxy_trend") in ("falling", "flat")
    )
    risk_off = (
        data.get("vix_regime") in ("elevated", "extreme")
        or data.get("dxy_trend") == "rising_strongly"
    )

    data["overall_stance"] = "risk_on" if risk_on else "risk_off" if risk_off else "neutral"
    return data
