"""Pipeline domain freshness and latency collector.

Fetches /domains/ and /health/ endpoints locally and updates Prometheus gauges.
"""

import httpx

from monitoring.metrics import (
    DOMAIN_FRESHNESS_STATUS,
    DOMAIN_LATENCY_SECONDS,
    HEALTH_STATUS,
    METRICS_AVAILABLE,
    WMI_SCORE,
)

_FRESHNESS_MAP = {
    "fresh": 0,
    "acceptable": 1,
    "stale": 2,
    "unavailable": 3,
}

API_BASE = "http://127.0.0.1:8000"


def collect_pipeline_metrics() -> None:
    """Fetch domain and health data from local API and update gauges."""
    if not METRICS_AVAILABLE:
        return

    try:
        with httpx.Client(timeout=5.0) as client:
            # Domain freshness and latency
            resp = client.get(f"{API_BASE}/domains/")
            if resp.status_code == 200:
                data = resp.json()
                domains = data if isinstance(data, list) else data.get("domains", [])
                for domain in domains:
                    name = domain.get("domain", domain.get("name", "unknown"))
                    freshness = domain.get("freshness", "unavailable")
                    latency = domain.get("latency_seconds", domain.get("latency", 0))

                    DOMAIN_FRESHNESS_STATUS.labels(domain=name).set(
                        _FRESHNESS_MAP.get(freshness, 3)
                    )
                    if latency is not None:
                        DOMAIN_LATENCY_SECONDS.labels(domain=name).set(latency)

            # Health and WMI
            resp = client.get(f"{API_BASE}/health/")
            if resp.status_code == 200:
                data = resp.json()
                wmi = data.get("wmi_score", data.get("wmi", 0))
                WMI_SCORE.set(wmi if wmi is not None else 0)

                status = data.get("status", "healthy")
                status_map = {"healthy": 0, "degraded": 1, "unhealthy": 2}
                HEALTH_STATUS.set(status_map.get(status, 2))

    except Exception:
        # Network errors are non-fatal; metrics just won't update this cycle
        pass
