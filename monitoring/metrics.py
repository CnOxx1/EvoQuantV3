"""Prometheus metric definitions for EvoQuant.

All metrics are defined here as a single source of truth.
Gracefully degrades if prometheus_client is not installed.
"""

try:
    from prometheus_client import Counter, Gauge, Histogram

    HTTP_REQUESTS_TOTAL = Counter(
        "evoquant_http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )

    HTTP_REQUEST_DURATION = Histogram(
        "evoquant_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )

    HTTP_REQUESTS_IN_PROGRESS = Gauge(
        "evoquant_http_requests_in_progress",
        "Number of HTTP requests currently in progress",
        ["method"],
    )

    MODULE_STATUS = Gauge(
        "evoquant_module_status",
        "Module status (1=running, 0=stopped, -1=disabled)",
        ["module", "kind"],
    )

    MODULE_RESTART_COUNT = Gauge(
        "evoquant_module_restart_count",
        "Module restart count",
        ["module"],
    )

    MODULE_UPTIME_SECONDS = Gauge(
        "evoquant_module_uptime_seconds",
        "Module uptime in seconds",
        ["module"],
    )

    DOMAIN_LATENCY_SECONDS = Gauge(
        "evoquant_domain_latency_seconds",
        "Domain data latency in seconds",
        ["domain"],
    )

    DOMAIN_FRESHNESS_STATUS = Gauge(
        "evoquant_domain_freshness_status",
        "Domain freshness (0=fresh, 1=acceptable, 2=stale, 3=unavailable)",
        ["domain"],
    )

    WMI_SCORE = Gauge(
        "evoquant_wmi_score",
        "World Model Index score (0-100)",
    )

    HEALTH_STATUS = Gauge(
        "evoquant_health_status",
        "Overall health (0=healthy, 1=degraded, 2=unhealthy)",
    )

    PIPELINE_PHASE_DURATION = Histogram(
        "evoquant_pipeline_phase_duration_seconds",
        "Pipeline phase execution duration",
        ["phase", "module", "status"],
        buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
    )

    PIPELINE_TOTAL_DURATION = Histogram(
        "evoquant_pipeline_total_duration_seconds",
        "Pipeline total execution duration",
        buckets=(10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0),
    )

    DATABASE_SIZE_BYTES = Gauge(
        "evoquant_database_size_bytes",
        "Database file size in bytes",
        ["database"],
    )

    MARKET_ALERTS_TOTAL = Counter(
        "evoquant_market_alerts_total",
        "Market alert count",
        ["type", "severity"],
    )

    METRICS_AVAILABLE = True

except ImportError:
    METRICS_AVAILABLE = False
