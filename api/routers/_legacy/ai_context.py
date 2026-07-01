"""AI Context 路由 — AI 决策上下文端点。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db
from api.routers._helpers import _normalize_symbol, _safe_float
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/ai-context", tags=["ai-context"])


@router.get("/decision-bundle/{symbol}")
def decision_bundle(
    symbol: str,
    exchange: str = Query("binance", description="交易所"),
) -> dict[str, Any]:
    """AI 决策所需全部信息一次返回。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_analytics_db()
    exchange_db = get_exchange_db()

    # AI market context
    ctx = analytics_db.fetch_one(
        "SELECT entity_key, coverage_score, data_quality_flag, bundle_json "
        "FROM ai_market_context_snapshots WHERE entity_key = ? "
        "ORDER BY snapshot_time DESC LIMIT 1",
        (normalized,),
    )
    context_data = None
    if ctx:
        try:
            context_data = json.loads(ctx["bundle_json"]) if ctx["bundle_json"] else None
        except (json.JSONDecodeError, TypeError):
            context_data = None

    # Feature composites
    composites = analytics_db.fetch_all(
        "SELECT composite_name, composite_zscore, composite_percentile, "
        "regime_label, confidence, cross_asset_rank, cross_asset_rank_total "
        "FROM feature_standardization_composites WHERE symbol = ? "
        "ORDER BY snapshot_time DESC LIMIT 10",
        (normalized,),
    )
    composite_data = [
        {
            "name": c["composite_name"],
            "zscore": _safe_float(c["composite_zscore"]),
            "percentile": _safe_float(c["composite_percentile"]),
            "regime": c["regime_label"],
            "confidence": c["confidence"],
            "rank": c["cross_asset_rank"],
            "rank_total": c["cross_asset_rank_total"],
        }
        for c in composites
    ] if composites else []

    # Exchange comparison
    comparison = analytics_db.fetch_one(
        "SELECT best_buy_exchange, best_sell_exchange, opportunity_type, "
        "signal_label, signal_strength, net_cross_spread_max_bps, "
        "market_regime_label FROM exchange_comparison_snapshots "
        "WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
        (normalized,),
    )
    exchange_info = None
    if comparison:
        exchange_info = {
            "best_buy": comparison["best_buy_exchange"],
            "best_sell": comparison["best_sell_exchange"],
            "opportunity": comparison["opportunity_type"],
            "signal": comparison["signal_label"],
            "signal_strength": _safe_float(comparison["signal_strength"]),
            "cross_spread_bps": _safe_float(comparison["net_cross_spread_max_bps"]),
            "regime": comparison["market_regime_label"],
        }

    # Latest price from exchange_db
    ticker = exchange_db.fetch_one(
        "SELECT last_price, change_24h, quote_volume_24h FROM latest_tickers "
        "WHERE symbol = ? AND exchange = ?", (normalized, exchange),
    )
    price_info = None
    if ticker:
        price_info = {
            "price": _safe_float(ticker["last_price"]),
            "change_24h": _safe_float(ticker["change_24h"]),
            "volume_24h": _safe_float(ticker["quote_volume_24h"]),
        }

    return {
        "symbol": normalized, "exchange": exchange,
        "coverage_score": _safe_float(ctx["coverage_score"]) if ctx else None,
        "data_quality": ctx["data_quality_flag"] if ctx else None,
        "price": price_info,
        "ai_context": context_data,
        "factor_composites": composite_data,
        "exchange_comparison": exchange_info,
    }


@router.get("/market-state")
def market_state() -> dict[str, Any]:
    """全局市场状态（结构+就绪度+广度）。"""
    analytics_db = get_analytics_db()

    # Market structure
    structure = analytics_db.fetch_one(
        "SELECT snapshot_time, asset_count, data_quality_flag, bundle_json "
        "FROM market_structure_snapshots ORDER BY snapshot_time DESC LIMIT 1",
    )
    structure_data = None
    if structure:
        try:
            structure_data = json.loads(structure["bundle_json"]) if structure["bundle_json"] else None
        except (json.JSONDecodeError, TypeError):
            pass

    # Asset readiness
    readiness = analytics_db.fetch_one(
        "SELECT market_world_status, asset_count, ready_asset_count, "
        "partial_asset_count, blocked_asset_count, average_readiness_score "
        "FROM asset_readiness_snapshots ORDER BY snapshot_time DESC LIMIT 1",
    )
    readiness_data = None
    if readiness:
        readiness_data = {
            "world_status": readiness["market_world_status"],
            "total_assets": readiness["asset_count"],
            "ready": readiness["ready_asset_count"],
            "partial": readiness["partial_asset_count"],
            "blocked": readiness["blocked_asset_count"],
            "avg_score": _safe_float(readiness["average_readiness_score"]),
        }

    # Market breadth
    breadth = analytics_db.fetch_one(
        "SELECT breadth_status, asset_count, ai_ready_asset_count, "
        "breadth_score FROM market_breadth_snapshots "
        "ORDER BY snapshot_time DESC LIMIT 1",
    )
    breadth_data = None
    if breadth:
        breadth_data = {
            "status": breadth["breadth_status"],
            "asset_count": breadth["asset_count"],
            "ai_ready": breadth["ai_ready_asset_count"],
            "breadth_score": _safe_float(breadth["breadth_score"]),
        }

    return {
        "market_structure": structure_data,
        "asset_readiness": readiness_data,
        "market_breadth": breadth_data,
    }


@router.get("/factor-regime")
def factor_regime() -> dict[str, Any]:
    """全资产因子体制矩阵。"""
    analytics_db = get_analytics_db()

    rows = analytics_db.fetch_all(
        "SELECT symbol, composite_name, composite_zscore, composite_percentile, "
        "regime_label, confidence, cross_asset_rank, cross_asset_rank_total "
        "FROM feature_standardization_composites "
        "WHERE snapshot_time = (SELECT MAX(snapshot_time) FROM feature_standardization_composites)",
    )
    if not rows:
        return {"assets": {}, "regimes_summary": {}}

    assets: dict[str, list] = {}
    regime_counts: dict[str, int] = {}
    for r in rows:
        sym = r["symbol"]
        assets.setdefault(sym, []).append({
            "factor": r["composite_name"],
            "zscore": _safe_float(r["composite_zscore"]),
            "percentile": _safe_float(r["composite_percentile"]),
            "regime": r["regime_label"],
            "confidence": r["confidence"],
            "rank": r["cross_asset_rank"],
        })
        regime = r["regime_label"] or "unknown"
        regime_counts[regime] = regime_counts.get(regime, 0) + 1

    return {
        "asset_count": len(assets),
        "factor_count": len(rows),
        "assets": assets,
        "regimes_summary": regime_counts,
    }


@router.get("/arbitrage-opportunities")
def arbitrage_opportunities(
    min_spread_bps: float = Query(5.0, ge=0, description="最小跨交易所价差 (bps)"),
) -> dict[str, Any]:
    """跨交易所套利机会。"""
    analytics_db = get_analytics_db()
    exchange_db = get_exchange_db()

    rows = analytics_db.fetch_all(
        "SELECT symbol, exchange_a, exchange_b, net_cross_spread_max_bps, "
        "best_buy_exchange, best_sell_exchange, opportunity_type, signal_label, "
        "signal_strength, is_actionable, last_price_a, last_price_b, "
        "spread_bps_a, spread_bps_b FROM exchange_comparison_snapshots "
        "WHERE timestamp = (SELECT MAX(timestamp) FROM exchange_comparison_snapshots) "
        "AND net_cross_spread_max_bps >= ?",
        (min_spread_bps,),
    )
    if not rows:
        return {"min_spread_bps": min_spread_bps, "opportunities": []}

    opportunities = [
        {
            "symbol": r["symbol"],
            "exchange_a": r["exchange_a"],
            "exchange_b": r["exchange_b"],
            "net_spread_bps": _safe_float(r["net_cross_spread_max_bps"]),
            "best_buy": r["best_buy_exchange"],
            "best_sell": r["best_sell_exchange"],
            "opportunity_type": r["opportunity_type"],
            "signal": r["signal_label"],
            "strength": _safe_float(r["signal_strength"]),
            "actionable": bool(r["is_actionable"]),
            "price_a": _safe_float(r["last_price_a"]),
            "price_b": _safe_float(r["last_price_b"]),
        }
        for r in rows
    ]
    opportunities.sort(key=lambda x: x.get("net_spread_bps") or 0, reverse=True)
    return {
        "min_spread_bps": min_spread_bps,
        "count": len(opportunities),
        "opportunities": opportunities[:30],
    }


@router.get("/data-freshness")
def data_freshness() -> dict[str, Any]:
    """数据新鲜度报告（哪些数据过期）。"""
    analytics_db = get_analytics_db()
    exchange_db = get_exchange_db()

    # Collection runs from analytics
    runs = analytics_db.fetch_all(
        "SELECT module_name, source_name, job_name, status, item_count, "
        "finished_at, duration_seconds FROM collection_runs "
        "ORDER BY finished_at DESC LIMIT 50",
    )
    # Collection runs from exchange
    ex_runs = exchange_db.fetch_all(
        "SELECT module_name, source_name, job_name, status, item_count, "
        "finished_at, duration_seconds FROM collection_runs "
        "ORDER BY finished_at DESC LIMIT 50",
    )

    # Group by module
    modules: dict[str, dict] = {}
    for r in (runs or []) + (ex_runs or []):
        mod = r["module_name"]
        if mod not in modules or (r["finished_at"] or "") > (modules[mod].get("last_run") or ""):
            modules[mod] = {
                "module": mod,
                "source": r["source_name"],
                "last_job": r["job_name"],
                "status": r["status"],
                "items": r["item_count"],
                "last_run": r["finished_at"],
                "duration_s": _safe_float(r["duration_seconds"]),
            }

    # Check latest_* table timestamps
    latest_tables = [
        ("latest_tickers", "updated_at"),
        ("latest_funding_rates", "updated_at"),
        ("latest_orderbook_snapshots", "updated_at"),
        ("latest_trade_flow_bars", "updated_at"),
    ]
    table_freshness = {}
    for table, ts_col in latest_tables:
        row = exchange_db.fetch_one(
            f"SELECT MAX({ts_col}) as latest FROM {table}",
        )
        table_freshness[table] = row["latest"] if row else None

    sorted_modules = sorted(modules.values(), key=lambda x: x.get("last_run") or "", reverse=True)
    return {
        "module_count": len(sorted_modules),
        "modules": sorted_modules,
        "table_freshness": table_freshness,
    }


@router.get("/trading-readiness/{symbol}")
def trading_readiness(
    symbol: str,
) -> dict[str, Any]:
    """单资产可交易性评估。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_analytics_db()

    # Asset readiness
    readiness = analytics_db.fetch_one(
        "SELECT snapshot_time, market_world_status, average_readiness_score, "
        "data_quality_flag, bundle_json FROM asset_readiness_snapshots "
        "ORDER BY snapshot_time DESC LIMIT 1",
    )
    asset_ready = None
    if readiness and readiness["bundle_json"]:
        try:
            bundle = json.loads(readiness["bundle_json"])
            # Look for this symbol in the bundle
            if isinstance(bundle, dict):
                asset_ready = bundle.get(normalized) or bundle.get(normalized.split("/")[0])
            elif isinstance(bundle, list):
                for item in bundle:
                    if isinstance(item, dict) and item.get("symbol") == normalized:
                        asset_ready = item
                        break
        except (json.JSONDecodeError, TypeError):
            pass

    # Data quality audit
    audit = analytics_db.fetch_one(
        "SELECT world_model_status, is_market_data_ready_for_ai, "
        "critical_gap_count, critical_gap_band_names_json "
        "FROM data_quality_audit_snapshots WHERE audit_scope = ? "
        "ORDER BY snapshot_time DESC LIMIT 1",
        (normalized,),
    )
    if not audit:
        # Try global audit
        audit = analytics_db.fetch_one(
            "SELECT world_model_status, is_market_data_ready_for_ai, "
            "critical_gap_count, critical_gap_band_names_json "
            "FROM data_quality_audit_snapshots "
            "ORDER BY snapshot_time DESC LIMIT 1",
        )

    quality_info = None
    if audit:
        gaps = None
        if audit["critical_gap_band_names_json"]:
            try:
                gaps = json.loads(audit["critical_gap_band_names_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        quality_info = {
            "world_status": audit["world_model_status"],
            "ai_ready": bool(audit["is_market_data_ready_for_ai"]),
            "critical_gaps": audit["critical_gap_count"],
            "gap_details": gaps,
        }

    # Determine overall readiness
    is_ready = bool(audit and audit["is_market_data_ready_for_ai"])
    readiness_label = "ready" if is_ready else "partial" if audit else "unknown"

    return {
        "symbol": normalized,
        "readiness_label": readiness_label,
        "is_tradeable": is_ready,
        "asset_readiness": asset_ready,
        "data_quality": quality_info,
    }
