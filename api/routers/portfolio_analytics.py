"""Portfolio Analytics 路由 — 组合风险分析（快照、回撤、集中度、VaR分解、相关性风险、趋势）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _linear_slope, _safe_float

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/snapshot")
def get_portfolio_snapshot(
    portfolio: str = Query("default", description="组合名称"),
) -> dict[str, Any]:
    """最新组合风险快照（完整解析）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC LIMIT 1""",
        (portfolio,),
    )
    if not row:
        row = db.fetch_one(
            "SELECT * FROM portfolio_risk_snapshots ORDER BY snapshot_time DESC LIMIT 1",
            (),
        )
    if not row:
        raise HTTPException(status_code=404, detail="No portfolio snapshot found.")

    data = dict(row)
    # Parse JSON fields
    for field in ("weights_json", "risk_contributions_json", "sector_concentration_json"):
        if data.get(field):
            try:
                data[field.replace("_json", "")] = json.loads(data[field])
                del data[field]
            except json.JSONDecodeError:
                pass
    return data


@router.get("/drawdown")
def get_drawdown(
    portfolio: str = Query("default", description="组合名称"),
    limit: int = Query(50, ge=1, le=500, description="历史快照数"),
) -> dict[str, Any]:
    """最大回撤 + 当前回撤 + 恢复时间。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, annualized_volatility, daily_var_95
           FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (portfolio, limit),
    )
    if not rows:
        rows = db.fetch_all(
            "SELECT snapshot_time, annualized_volatility, daily_var_95 "
            "FROM portfolio_risk_snapshots ORDER BY snapshot_time DESC LIMIT ?",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No portfolio data found.")

    rows_asc = list(reversed(rows))
    var_series = [_safe_float(r["daily_var_95"]) or 0 for r in rows_asc]

    # Compute drawdown from VaR series (higher VaR = more risk)
    peak_var = var_series[0] if var_series else 0
    max_dd = 0.0
    current_dd = 0.0
    peak_idx = 0
    max_dd_start = 0
    max_dd_end = 0

    for i, v in enumerate(var_series):
        if v < peak_var:
            peak_var = v
            peak_idx = i
        dd = (v - peak_var) / (abs(peak_var) + 1e-9)
        if dd > max_dd:
            max_dd = dd
            max_dd_start = peak_idx
            max_dd_end = i
        current_dd = dd

    return {
        "portfolio": portfolio,
        "snapshot_count": len(rows),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "current_drawdown_pct": round(current_dd * 100, 4),
        "max_dd_period": {
            "start": rows_asc[max_dd_start]["snapshot_time"] if max_dd_start < len(rows_asc) else None,
            "end": rows_asc[max_dd_end]["snapshot_time"] if max_dd_end < len(rows_asc) else None,
        },
        "latest_var_95": var_series[-1] if var_series else None,
    }


@router.get("/concentration")
def get_concentration(
    portfolio: str = Query("default", description="组合名称"),
    limit: int = Query(50, ge=1, le=500, description="历史快照数"),
) -> dict[str, Any]:
    """HHI 集中度 + 有效资产数历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, hhi, effective_n, max_weight, asset_count,
                  diversification_ratio
           FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (portfolio, limit),
    )
    if not rows:
        rows = db.fetch_all(
            """SELECT snapshot_time, hhi, effective_n, max_weight, asset_count,
                      diversification_ratio
               FROM portfolio_risk_snapshots
               ORDER BY snapshot_time DESC LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No portfolio data found.")

    records = [dict(r) for r in rows]
    latest = records[0]
    hhi_values = [_safe_float(r["hhi"]) or 0 for r in records]
    hhi_trend = _linear_slope(list(reversed(hhi_values))) if len(hhi_values) >= 3 else 0

    return {
        "portfolio": portfolio,
        "snapshot_count": len(records),
        "latest": {
            "hhi": latest.get("hhi"),
            "effective_n": latest.get("effective_n"),
            "max_weight": latest.get("max_weight"),
            "diversification_ratio": latest.get("diversification_ratio"),
        },
        "hhi_trend_slope": round(hhi_trend, 6),
        "history": records,
    }


@router.get("/var-decomposition")
def get_var_decomposition(
    portfolio: str = Query("default", description="组合名称"),
) -> dict[str, Any]:
    """VaR 分解（各资产贡献）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT snapshot_time, daily_var_95, daily_var_99,
                  risk_contributions_json, weights_json
           FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC LIMIT 1""",
        (portfolio,),
    )
    if not row:
        row = db.fetch_one(
            """SELECT snapshot_time, daily_var_95, daily_var_99,
                      risk_contributions_json, weights_json
               FROM portfolio_risk_snapshots
               ORDER BY snapshot_time DESC LIMIT 1""",
            (),
        )
    if not row:
        raise HTTPException(status_code=404, detail="No portfolio data found.")

    data = dict(row)
    contributions = {}
    weights = {}
    if data.get("risk_contributions_json"):
        try:
            contributions = json.loads(data["risk_contributions_json"])
        except json.JSONDecodeError:
            pass
    if data.get("weights_json"):
        try:
            weights = json.loads(data["weights_json"])
        except json.JSONDecodeError:
            pass

    return {
        "snapshot_time": data["snapshot_time"],
        "daily_var_95": data["daily_var_95"],
        "daily_var_99": data["daily_var_99"],
        "asset_contributions": contributions,
        "weights": weights,
    }


@router.get("/correlation-risk")
def get_correlation_risk(
    limit: int = Query(20, ge=1, le=100, description="历史快照数"),
) -> dict[str, Any]:
    """组合相关性聚类风险。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, avg_correlation, max_correlation, min_correlation,
                  matrix_json, symbols_json
           FROM cross_asset_correlation_snapshots
           ORDER BY snapshot_time DESC LIMIT ?""",
        (limit,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No correlation data found.")

    latest = dict(rows[0])
    matrix = {}
    symbols = []
    if latest.get("matrix_json"):
        try:
            matrix = json.loads(latest["matrix_json"])
        except json.JSONDecodeError:
            pass
    if latest.get("symbols_json"):
        try:
            symbols = json.loads(latest["symbols_json"])
        except json.JSONDecodeError:
            pass

    # Identify highly correlated clusters (> 0.7)
    clusters = []
    if isinstance(matrix, dict):
        for pair, corr in matrix.items():
            if isinstance(corr, (int, float)) and abs(corr) > 0.7:
                clusters.append({"pair": pair, "correlation": corr})

    avg_corr_series = [_safe_float(r["avg_correlation"]) or 0 for r in reversed(rows)]
    corr_trend = _linear_slope(avg_corr_series) if len(avg_corr_series) >= 3 else 0

    return {
        "snapshot_time": latest["snapshot_time"],
        "avg_correlation": latest.get("avg_correlation"),
        "max_correlation": latest.get("max_correlation"),
        "min_correlation": latest.get("min_correlation"),
        "high_correlation_pairs": clusters[:20],
        "correlation_trend_slope": round(corr_trend, 6),
        "risk_level": "high" if (latest.get("avg_correlation") or 0) > 0.6 else "moderate"
            if (latest.get("avg_correlation") or 0) > 0.4 else "low",
    }


@router.get("/risk-trend")
def get_risk_trend(
    portfolio: str = Query("default", description="组合名称"),
    limit: int = Query(30, ge=5, le=200, description="历史快照数"),
) -> dict[str, Any]:
    """风险指标趋势（VaR/vol 斜率）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, annualized_volatility, daily_var_95, daily_var_99, hhi
           FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC LIMIT ?""",
        (portfolio, limit),
    )
    if not rows:
        rows = db.fetch_all(
            """SELECT snapshot_time, annualized_volatility, daily_var_95, daily_var_99, hhi
               FROM portfolio_risk_snapshots
               ORDER BY snapshot_time DESC LIMIT ?""",
            (limit,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="No portfolio data found.")

    rows_asc = list(reversed(rows))
    vol_series = [_safe_float(r["annualized_volatility"]) or 0 for r in rows_asc]
    var95_series = [_safe_float(r["daily_var_95"]) or 0 for r in rows_asc]
    var99_series = [_safe_float(r["daily_var_99"]) or 0 for r in rows_asc]

    return {
        "portfolio": portfolio,
        "snapshot_count": len(rows),
        "trends": {
            "volatility_slope": round(_linear_slope(vol_series), 6),
            "var_95_slope": round(_linear_slope(var95_series), 6),
            "var_99_slope": round(_linear_slope(var99_series), 6),
        },
        "latest": {
            "annualized_volatility": vol_series[-1] if vol_series else None,
            "daily_var_95": var95_series[-1] if var95_series else None,
            "daily_var_99": var99_series[-1] if var99_series else None,
        },
        "direction": "increasing" if _linear_slope(vol_series) > 0 else "decreasing",
    }
