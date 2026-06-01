"""链上领先-滞后分析路由 — 链上信号预测性分析端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from api.routers._helpers import _safe_float

router = APIRouter(prefix="/onchain-lead-lag", tags=["onchain-lead-lag"])


@router.get("/signals")
def get_lead_lag_signals(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """所有领先-滞后信号及其相关性。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM lead_lag_signals WHERE ts = "
        "(SELECT MAX(ts) FROM lead_lag_signals) "
        "ORDER BY ABS(correlation) DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "signals": rows}


@router.get("/relations/{symbol}")
def get_price_relations(
    symbol: str,
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """指定资产的链上指标与价格关系。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM onchain_price_relations WHERE symbol = ? "
        "ORDER BY predictive_power DESC LIMIT ?",
        (symbol.upper(), limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No relations for {symbol}")
    return {"symbol": symbol.upper(), "count": len(rows), "relations": rows}


@router.get("/alerts")
def get_signal_alerts(
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
) -> dict[str, Any]:
    """当前活跃的信号触发告警。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM signal_alerts ORDER BY triggered_at DESC LIMIT ?",
        (limit,),
    )
    return {"count": len(rows), "alerts": rows}


@router.get("/predictive-ranking")
def get_predictive_ranking() -> dict[str, Any]:
    """按预测力排名所有信号。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT signal_name, AVG(predictive_power) as avg_power, "
        "AVG(ABS(correlation)) as avg_corr, COUNT(DISTINCT symbol) as symbol_count "
        "FROM onchain_price_relations WHERE ts = "
        "(SELECT MAX(ts) FROM onchain_price_relations) "
        "GROUP BY signal_name ORDER BY avg_power DESC",
        (),
    )
    return {"count": len(rows), "ranking": rows}


@router.get("/optimal-lag/{signal_name}")
def get_optimal_lag(
    signal_name: str,
) -> dict[str, Any]:
    """指定信号的最优领先时间。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM lead_lag_signals WHERE signal_name = ? "
        "ORDER BY ts DESC LIMIT 1",
        (signal_name,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No data for signal {signal_name}")
    return {"signal_name": signal_name, "result": rows[0]}


@router.get("/granger/{symbol}")
def get_granger_results(
    symbol: str,
) -> dict[str, Any]:
    """指定资产的 Granger 因果检验结果。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT metric_name, lead_lag_hours, granger_f_stat, predictive_power "
        "FROM onchain_price_relations WHERE symbol = ? "
        "AND ts = (SELECT MAX(ts) FROM onchain_price_relations WHERE symbol = ?) "
        "ORDER BY granger_f_stat DESC",
        (symbol.upper(), symbol.upper()),
    )
    return {"symbol": symbol.upper(), "count": len(rows), "granger_results": rows}


@router.get("/signal-history/{signal_name}")
def get_signal_history(
    signal_name: str,
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
) -> dict[str, Any]:
    """信号触发历史。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT * FROM signal_alerts WHERE signal_name = ? "
        "ORDER BY triggered_at DESC LIMIT ?",
        (signal_name, limit),
    )
    return {"signal_name": signal_name, "count": len(rows), "history": rows}


@router.get("/cross-signal")
def get_cross_signal_confluence() -> dict[str, Any]:
    """多信号共振检测（多个链上信号同时触发）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        "SELECT symbol, COUNT(DISTINCT signal_name) as signal_count, "
        "GROUP_CONCAT(signal_name) as signals, "
        "GROUP_CONCAT(expected_price_direction) as directions "
        "FROM signal_alerts WHERE triggered_at >= datetime('now', '-24 hours') "
        "GROUP BY symbol HAVING signal_count >= 2 "
        "ORDER BY signal_count DESC",
        (),
    )
    return {"count": len(rows), "confluences": rows}


@router.get("/context")
def get_onchain_lead_lag_context() -> dict[str, Any]:
    """链上领先-滞后分析 AI 上下文 bundle。"""
    from logic_layer.onchain_lead_lag.service import OnchainLeadLagService
    service = OnchainLeadLagService()
    bundle = service.load_latest_context_bundle()
    service.close()
    return bundle
