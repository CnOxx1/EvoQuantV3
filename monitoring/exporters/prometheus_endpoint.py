"""Prometheus metrics endpoint for FastAPI.

Exposes /metrics/prometheus in Prometheus text exposition format.
Background thread periodically collects pipeline and database metrics.
"""

import threading
import time

from fastapi import APIRouter, Response

from monitoring.metrics import METRICS_AVAILABLE

metrics_router = APIRouter(tags=["monitoring"])

_COLLECTION_STARTED = False
_COLLECTION_LOCK = threading.Lock()


def _start_background_collection() -> None:
    """Start a daemon thread that collects pipeline/db metrics every 15s."""
    global _COLLECTION_STARTED
    with _COLLECTION_LOCK:
        if _COLLECTION_STARTED:
            return
        _COLLECTION_STARTED = True

    def _loop():
        from monitoring.collectors.database_collector import collect_database_sizes
        from monitoring.collectors.pipeline_collector import collect_pipeline_metrics

        while True:
            try:
                collect_pipeline_metrics()
            except Exception:
                pass
            try:
                collect_database_sizes()
            except Exception:
                pass
            time.sleep(15)

    t = threading.Thread(target=_loop, daemon=True, name="prom-collector")
    t.start()


@metrics_router.get("/metrics/prometheus", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Return metrics in Prometheus text exposition format."""
    if not METRICS_AVAILABLE:
        return Response(
            content="# prometheus_client not installed\n",
            media_type="text/plain; charset=utf-8",
            status_code=200,
        )

    # Lazy-start background collection on first scrape
    _start_background_collection()

    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
