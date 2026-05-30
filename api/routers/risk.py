"""Risk 路由 — 组合风险指标查询（波动率、VaR、集中度、分散化）。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/risk", tags=["risk"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


@router.get("/portfolio/latest")
def get_portfolio_risk_latest(
    portfolio: str = Query("default", description="组合名称"),
) -> dict[str, Any]:
    """返回最新一次组合风险计算结果（VaR、波动率、集中度、分散化）。"""
    db = get_analytics_db()
    row = db.fetch_one(
        """SELECT * FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC
           LIMIT 1""",
        (portfolio,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No portfolio risk data found. Run logic_pipeline first.")

    data = dict(row)
    for json_field in ("weights_json", "risk_contributions_json", "sector_concentration_json"):
        if data.get(json_field):
            try:
                key = json_field.replace("_json", "")
                data[key] = json.loads(data[json_field])
                del data[json_field]
            except (json.JSONDecodeError, KeyError):
                pass

    return data


@router.get("/portfolio/history")
def get_portfolio_risk_history(
    portfolio: str = Query("default", description="组合名称"),
    limit: int = Query(24, ge=1, le=200, description="返回最近 N 条快照"),
) -> dict[str, Any]:
    """返回组合风险历史快照序列（用于趋势分析）。"""
    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT snapshot_time, annualized_volatility, daily_var_95, daily_var_99,
                  hhi, effective_n, max_weight, diversification_ratio
           FROM portfolio_risk_snapshots
           WHERE portfolio_name = ?
           ORDER BY snapshot_time DESC
           LIMIT ?""",
        (portfolio, limit),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No portfolio risk history found.")

    records = [dict(r) for r in rows]
    records.reverse()
    return {
        "portfolio": portfolio,
        "count": len(records),
        "history": records,
    }


@router.get("/volatility")
def get_asset_volatilities() -> dict[str, Any]:
    """返回各资产当前隐含日波动率（从最新 portfolio_risk_snapshots 的 risk_contributions 推导）。"""
    db = get_analytics_db()

    rows = db.fetch_all(
        """SELECT symbol, close, open_time
           FROM merged_klines
           WHERE timeframe = '1h'
           ORDER BY symbol, open_time DESC""",
        (),
    )

    import math
    series: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for row in rows:
        sym = row["symbol"]
        if counts.get(sym, 0) >= 168:
            continue
        series.setdefault(sym, []).append(float(row["close"]))
        counts[sym] = counts.get(sym, 0) + 1

    result: dict[str, Any] = {}
    for sym, prices in series.items():
        prices.reverse()
        if len(prices) < 2:
            continue
        log_rets = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        if not log_rets:
            continue
        mean_r = sum(log_rets) / len(log_rets)
        var = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
        hourly_vol = math.sqrt(var)
        daily_vol = hourly_vol * math.sqrt(24)
        annualized_vol = daily_vol * math.sqrt(365)
        result[sym] = {
            "daily_vol": round(daily_vol, 6),
            "annualized_vol": round(annualized_vol, 4),
            "var_95_daily": round(daily_vol * 1.645, 6),
            "var_99_daily": round(daily_vol * 2.326, 6),
            "sample_bars": len(log_rets),
        }

    if not result:
        raise HTTPException(status_code=404, detail="No kline data available for volatility calculation.")

    return {
        "symbol_count": len(result),
        "window": "7d_1h_bars",
        "volatilities": result,
    }


@router.get("/score/{symbol}")
def get_risk_score(symbol: str) -> dict[str, Any]:
    """返回单个资产的风险评分摘要（给 Sui Bridge 使用）。

    risk_level: low / medium / high / extreme
    """
    import math

    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    db = get_analytics_db()
    rows = db.fetch_all(
        """SELECT close FROM merged_klines
           WHERE symbol = ? AND timeframe = '1h'
           ORDER BY open_time DESC LIMIT 168""",
        (normalized,),
    )
    if len(rows) < 10:
        raise HTTPException(status_code=404, detail="Insufficient kline data for risk score.")

    prices = [float(r["close"]) for r in rows]
    prices.reverse()
    log_rets = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i - 1] > 0
    ]
    mean_r = sum(log_rets) / len(log_rets)
    variance = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
    daily_vol = math.sqrt(variance) * math.sqrt(24)
    annualized_vol = daily_vol * math.sqrt(365)

    if annualized_vol < 0.5:
        risk_level = "low"
        risk_score = round(annualized_vol / 0.5 * 25, 1)
    elif annualized_vol < 1.0:
        risk_level = "medium"
        risk_score = round(25 + (annualized_vol - 0.5) / 0.5 * 25, 1)
    elif annualized_vol < 2.0:
        risk_level = "high"
        risk_score = round(50 + (annualized_vol - 1.0) / 1.0 * 25, 1)
    else:
        risk_level = "extreme"
        risk_score = min(100.0, round(75 + (annualized_vol - 2.0) / 2.0 * 25, 1))

    return {
        "symbol": normalized,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "annualized_vol": round(annualized_vol, 4),
        "daily_vol": round(daily_vol, 6),
        "var_95_daily": round(daily_vol * 1.645, 6),
        "var_99_daily": round(daily_vol * 2.326, 6),
        "sample_bars": len(log_rets),
    }
