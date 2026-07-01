"""Signals 路由 — 综合量化信号，供 Sui Bridge 直接消费。

这是 Bridge 最核心的接口，输出标准化信号 bundle，包含：
- 市场方向信号（trend_signal）
- 动量信号（momentum_signal）
- 波动率状态（volatility_regime）
- 资金费率异常（funding_anomaly）
- 综合 AI 判断（ai_verdict）
- 风险评分（risk_score）
"""

from __future__ import annotations

import json
import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.dependencies import get_analytics_db, get_exchange_db
from config.symbols import TARGET_SYMBOLS

router = APIRouter(prefix="/signals", tags=["signals"])


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _compute_trend_signal(rsi: float | None, macd_hist: float | None) -> dict[str, Any]:
    """基于 RSI + MACD 计算趋势信号。"""
    score = 0.0
    signals = []

    if rsi is not None:
        if rsi > 70:
            score -= 1.0
            signals.append("rsi_overbought")
        elif rsi > 55:
            score += 0.5
            signals.append("rsi_bullish")
        elif rsi < 30:
            score += 1.0
            signals.append("rsi_oversold")
        elif rsi < 45:
            score -= 0.5
            signals.append("rsi_bearish")

    if macd_hist is not None:
        if macd_hist > 0:
            score += 0.5
            signals.append("macd_positive")
        else:
            score -= 0.5
            signals.append("macd_negative")

    if score > 0.5:
        direction = "bullish"
    elif score < -0.5:
        direction = "bearish"
    else:
        direction = "neutral"

    return {"direction": direction, "score": round(score, 2), "signals": signals}


def _compute_volatility_regime(annualized_vol: float | None) -> str:
    """将年化波动率映射为 regime 标签。"""
    if annualized_vol is None:
        return "unknown"
    if annualized_vol < 0.4:
        return "low"
    elif annualized_vol < 0.8:
        return "normal"
    elif annualized_vol < 1.5:
        return "elevated"
    else:
        return "extreme"


def _compute_funding_anomaly(funding_rate: float | None) -> dict[str, Any]:
    """判断资金费率是否异常（绝对值 > 0.1% 视为显著）。"""
    if funding_rate is None:
        return {"is_anomaly": False, "direction": "neutral", "rate": None}
    threshold = 0.001
    is_anomaly = abs(funding_rate) > threshold
    direction = "long_biased" if funding_rate > 0 else "short_biased"
    return {
        "is_anomaly": is_anomaly,
        "direction": direction if is_anomaly else "neutral",
        "rate": round(funding_rate, 6),
        "annualized_rate": round(funding_rate * 3 * 365, 4),
    }


@router.get("/{symbol}")
def get_signal_bundle(symbol: str) -> dict[str, Any]:
    """返回指定资产的完整信号 bundle（Sui Bridge 主接口）。"""
    normalized = _normalize_symbol(symbol)
    if normalized not in TARGET_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Symbol '{normalized}' not in universe.")

    analytics_db = get_analytics_db()
    exchange_db = get_exchange_db()

    # 1. 技术指标
    ti_row = analytics_db.fetch_one(
        """SELECT rsi_14, macd_line, macd_signal, macd_hist,
                  bb_upper, bb_lower, bb_middle, atr_14, adx_14,
                  ema_20, ema_50, open_time
           FROM technical_indicators
           WHERE symbol = ? AND timeframe = '1h'
           ORDER BY open_time DESC LIMIT 1""",
        (normalized,),
    )

    # 2. 资金费率
    fr_row = exchange_db.fetch_one(
        """SELECT funding_rate, mark_price, timestamp
           FROM latest_funding_rates
           WHERE symbol = ?
           ORDER BY timestamp DESC LIMIT 1""",
        (normalized,),
    )

    # 3. 计算日波动率
    kline_rows = analytics_db.fetch_all(
        """SELECT close FROM merged_klines
           WHERE symbol = ? AND timeframe = '1h'
           ORDER BY open_time DESC LIMIT 168""",
        (normalized,),
    )

    annualized_vol: float | None = None
    daily_vol: float | None = None
    if len(kline_rows) >= 10:
        prices = [float(r["close"]) for r in kline_rows]
        prices.reverse()
        log_rets = [
            math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices))
            if prices[i - 1] > 0
        ]
        if log_rets:
            mean_r = sum(log_rets) / len(log_rets)
            var = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
            daily_vol = math.sqrt(var) * math.sqrt(24)
            annualized_vol = daily_vol * math.sqrt(365)

    # 4. AI 市场上下文（最新快照）
    ai_row = analytics_db.fetch_one(
        """SELECT bundle_json, snapshot_time
           FROM ai_market_context_snapshots
           WHERE entity_key = ?
           ORDER BY snapshot_time DESC LIMIT 1""",
        (normalized,),
    )
    ai_verdict: dict[str, Any] = {}
    if ai_row and ai_row["bundle_json"]:
        try:
            bundle = json.loads(ai_row["bundle_json"])
            ai_verdict = {
                "data_quality_flag": bundle.get("data_quality_flag"),
                "coverage_score": bundle.get("coverage_score"),
                "world_model_index": bundle.get("world_model_index"),
                "snapshot_time": ai_row["snapshot_time"],
            }
        except (json.JSONDecodeError, TypeError):
            pass

    # 5. 标准化特征（zscore + percentile）
    std_rows = analytics_db.fetch_all(
        """SELECT feature_name, zscore_30d, percentile_30d, regime_label
           FROM feature_standardization_details
           WHERE symbol = ?
           AND snapshot_time = (
               SELECT MAX(snapshot_time)
               FROM feature_standardization_details
               WHERE symbol = ?
           )""",
        (normalized, normalized),
    )
    std_features: dict[str, Any] = {
        r["feature_name"]: {
            "zscore_30d": _safe_float(r["zscore_30d"]),
            "percentile_30d": _safe_float(r["percentile_30d"]),
            "regime_label": r["regime_label"],
        }
        for r in std_rows
    }

    # 6. 组合信号
    rsi = _safe_float(ti_row["rsi_14"]) if ti_row else None
    macd_hist = _safe_float(ti_row["macd_hist"]) if ti_row else None
    funding_rate = _safe_float(fr_row["funding_rate"]) if fr_row else None

    trend = _compute_trend_signal(rsi, macd_hist)
    vol_regime = _compute_volatility_regime(annualized_vol)
    funding_anomaly = _compute_funding_anomaly(funding_rate)

    # 综合风险评分 0-100
    risk_score: float | None = None
    if annualized_vol is not None:
        if annualized_vol < 0.5:
            risk_score = round(annualized_vol / 0.5 * 25, 1)
        elif annualized_vol < 1.0:
            risk_score = round(25 + (annualized_vol - 0.5) / 0.5 * 25, 1)
        elif annualized_vol < 2.0:
            risk_score = round(50 + (annualized_vol - 1.0) / 1.0 * 25, 1)
        else:
            risk_score = min(100.0, round(75 + (annualized_vol - 2.0) / 2.0 * 25, 1))

    return {
        "symbol": normalized,
        "generated_at": ti_row["open_time"] if ti_row else None,
        "trend_signal": trend,
        "volatility": {
            "regime": vol_regime,
            "annualized_vol": round(annualized_vol, 4) if annualized_vol else None,
            "daily_vol": round(daily_vol, 6) if daily_vol else None,
            "var_95_daily": round(daily_vol * 1.645, 6) if daily_vol else None,
        },
        "funding_anomaly": funding_anomaly,
        "risk_score": risk_score,
        "risk_level": (
            "low" if risk_score is not None and risk_score < 25 else
            "medium" if risk_score is not None and risk_score < 50 else
            "high" if risk_score is not None and risk_score < 75 else
            "extreme" if risk_score is not None else "unknown"
        ),
        "standardized_features": std_features,
        "ai_context": ai_verdict,
        "raw_indicators": {
            "rsi_14": rsi,
            "macd_hist": macd_hist,
            "atr_14": _safe_float(ti_row["atr_14"]) if ti_row else None,
            "adx_14": _safe_float(ti_row["adx_14"]) if ti_row else None,
            "bb_upper": _safe_float(ti_row["bb_upper"]) if ti_row else None,
            "bb_lower": _safe_float(ti_row["bb_lower"]) if ti_row else None,
            "ema_20": _safe_float(ti_row["ema_20"]) if ti_row else None,
            "ema_50": _safe_float(ti_row["ema_50"]) if ti_row else None,
        },
    }


@router.get("/")
def get_all_signals(
    risk_level: str | None = Query(None, description="过滤风险等级: low/medium/high/extreme"),
) -> dict[str, Any]:
    """返回所有资产的信号摘要（用于 Dashboard 全局视图）。"""
    results: dict[str, Any] = {}
    for symbol in TARGET_SYMBOLS:
        try:
            bundle = get_signal_bundle(symbol.replace("/USDT", ""))
            if risk_level and bundle.get("risk_level") != risk_level:
                continue
            results[symbol] = {
                "trend": bundle["trend_signal"]["direction"],
                "trend_score": bundle["trend_signal"]["score"],
                "volatility_regime": bundle["volatility"]["regime"],
                "annualized_vol": bundle["volatility"]["annualized_vol"],
                "risk_score": bundle["risk_score"],
                "risk_level": bundle["risk_level"],
                "funding_anomaly": bundle["funding_anomaly"]["is_anomaly"],
                "funding_direction": bundle["funding_anomaly"]["direction"],
            }
        except HTTPException:
            results[symbol] = {"error": "no_data"}

    return {
        "symbol_count": len(results),
        "filter_risk_level": risk_level,
        "signals": results,
    }
