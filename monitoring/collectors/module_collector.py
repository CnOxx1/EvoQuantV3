"""Module supervisor state collector.

Exports module status, restart counts, and uptime to Prometheus gauges.
"""

import time

from monitoring.metrics import (
    METRICS_AVAILABLE,
    MODULE_RESTART_COUNT,
    MODULE_STATUS,
    MODULE_UPTIME_SECONDS,
)


def export_module_status(children: dict) -> None:
    """Update Prometheus gauges from ManagedProcess dict.

    Args:
        children: dict of {name: ManagedProcess} from main.py supervisor.
    """
    if not METRICS_AVAILABLE:
        return

    now = time.time()
    for name, mp in children.items():
        kind = mp.spec.kind

        if mp.disabled_after_failure:
            status = -1
        elif mp.process and mp.process.poll() is None:
            status = 1
        else:
            status = 0

        MODULE_STATUS.labels(module=name, kind=kind).set(status)
        MODULE_RESTART_COUNT.labels(module=name).set(mp.restart_count)

        if mp.last_started_at and status == 1:
            uptime = now - mp.last_started_at
            MODULE_UPTIME_SECONDS.labels(module=name).set(uptime)
        else:
            MODULE_UPTIME_SECONDS.labels(module=name).set(0)
