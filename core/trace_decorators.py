"""轻量级追踪装饰器，为关键函数创建 OpenTelemetry span。"""

from __future__ import annotations

import functools
from typing import Any, Callable


def traced(name: str | None = None):
    """装饰器：为函数创建 span，自动记录参数和异常。

    未启用 OTel 时为 no-op（零开销）。

    Usage:
        @traced("pipeline.refresh_all")
        def refresh_all(self, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = _get_tracer()
            if tracer is None:
                return func(*args, **kwargs)

            with tracer.start_as_current_span(span_name) as span:
                # 记录关键 kwargs 到 span attributes
                for k, v in kwargs.items():
                    if isinstance(v, (str, int, float, bool)):
                        span.set_attribute(f"arg.{k}", v)
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    span.set_status(_StatusCode_ERROR, str(exc))
                    span.record_exception(exc)
                    raise

        return wrapper
    return decorator


def _get_tracer():
    """安全获取 tracer，未安装 OTel 时返回 None。"""
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("evoquant")
        return tracer
    except ImportError:
        return None


try:
    from opentelemetry.trace import StatusCode
    _StatusCode_ERROR = StatusCode.ERROR
except ImportError:
    _StatusCode_ERROR = None
