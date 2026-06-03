"""FastAPI middleware for Prometheus HTTP request metrics."""

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from monitoring.metrics import (
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    METRICS_AVAILABLE,
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records request count, duration, and in-progress gauge."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not METRICS_AVAILABLE:
            return await call_next(request)

        method = request.method
        # Normalize path to first two segments to avoid high cardinality
        path = request.url.path
        parts = path.strip("/").split("/")
        normalized = "/" + "/".join(parts[:2]) if parts else path

        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path=normalized, status=status).inc()
            HTTP_REQUEST_DURATION.labels(method=method, path=normalized).observe(elapsed)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()

        return response
