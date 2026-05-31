"""共享工具函数 — 避免各 router 重复定义。"""

from __future__ import annotations

import math
from typing import Any


def _normalize_symbol(symbol: str) -> str:
    """统一符号格式为 'XXX/USDT'。"""
    normalized = symbol.upper().replace("-", "/")
    if not normalized.endswith("/USDT"):
        normalized = f"{normalized}/USDT"
    return normalized


def _safe_float(v: Any) -> float | None:
    """安全转换为 float，失败返回 None。"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compute_volatility(prices: list[float]) -> tuple[float, float]:
    """从价格序列计算日波动率和年化波动率（假设 1h bar）。

    Returns: (daily_vol, annualized_vol)
    """
    if len(prices) < 2:
        return 0.0, 0.0
    log_rets = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i - 1] > 0
    ]
    if not log_rets:
        return 0.0, 0.0
    mean_r = sum(log_rets) / len(log_rets)
    variance = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
    hourly_vol = math.sqrt(variance)
    daily_vol = hourly_vol * math.sqrt(24)
    annualized_vol = daily_vol * math.sqrt(365)
    return daily_vol, annualized_vol


def _percentile_rank(values: list[float], target: float) -> float:
    """计算 target 在 values 中的百分位排名 (0-100)。"""
    if not values:
        return 50.0
    count_below = sum(1 for v in values if v < target)
    count_equal = sum(1 for v in values if v == target)
    return (count_below + 0.5 * count_equal) / len(values) * 100


def _zscore(values: list[float], target: float) -> float:
    """计算 target 相对于 values 的 z-score。"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (target - mean) / std


def _risk_level(annualized_vol: float) -> tuple[float, str]:
    """根据年化波动率返回 (risk_score, risk_level_str)。"""
    if annualized_vol < 0.5:
        level = "low"
        score = round(annualized_vol / 0.5 * 25, 1)
    elif annualized_vol < 1.0:
        level = "medium"
        score = round(25 + (annualized_vol - 0.5) / 0.5 * 25, 1)
    elif annualized_vol < 2.0:
        level = "high"
        score = round(50 + (annualized_vol - 1.0) / 1.0 * 25, 1)
    else:
        level = "extreme"
        score = min(100.0, round(75 + (annualized_vol - 2.0) / 2.0 * 25, 1))
    return score, level
