"""共享工具函数 — 避免各 router 重复定义。"""

from __future__ import annotations

import functools
import hashlib
import math
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


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


def _linear_slope(values: list[float]) -> float:
    """简单线性回归斜率（用于趋势检测）。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _detect_divergence(series_a: list[float], series_b: list[float]) -> dict:
    """检测两个序列的背离（higher high vs lower high 等）。"""
    min_len = min(len(series_a), len(series_b))
    if min_len < 4:
        return {"divergence": "insufficient_data", "strength": 0.0}
    a = series_a[-min_len:]
    b = series_b[-min_len:]
    mid = min_len // 2
    a_first, a_second = a[:mid], a[mid:]
    b_first, b_second = b[:mid], b[mid:]
    a_trend = max(a_second) - max(a_first)
    b_trend = max(b_second) - max(b_first)
    if a_trend > 0 and b_trend < 0:
        div_type = "bearish"
    elif a_trend < 0 and b_trend > 0:
        div_type = "bullish"
    else:
        div_type = "none"
    strength = abs(a_trend - b_trend) / (abs(a_trend) + abs(b_trend) + 1e-9)
    return {"divergence": div_type, "strength": round(strength, 4)}


def cached_response(prefix: str, ttl: float = 60.0):
    """装饰器：对 FastAPI 端点做 TTL 缓存。

    用法::

        @router.get("/bundle/{entity}")
        @cached_response("bundle", ttl=60)
        def get_bundle(entity: str, request: Request):
            ...

    缓存 key = prefix:path:query_hash
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            cache_key = _build_cache_key(prefix, request)
            from api.cache import cache

            cached = cache.get(cache_key)
            if cached is not None:
                return JSONResponse(
                    content=cached,
                    headers={"X-Cache": "HIT"},
                )
            result = await func(*args, **kwargs) if _is_coroutine(func) else func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            cache_key = _build_cache_key(prefix, request)
            from api.cache import cache

            cached = cache.get(cache_key)
            if cached is not None:
                return JSONResponse(
                    content=cached,
                    headers={"X-Cache": "HIT"},
                )
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _is_coroutine(func) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(func)


def _build_cache_key(prefix: str, request: Request | None) -> str:
    """从请求构建缓存 key。"""
    if request is None:
        return prefix
    path = request.url.path
    query = str(sorted(request.query_params.items()))
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8] if query != "[]" else ""
    parts = [prefix, path]
    if query_hash:
        parts.append(query_hash)
    return ":".join(parts)
