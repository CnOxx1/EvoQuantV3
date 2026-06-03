"""Database file size collector.

Reports SQLite database file sizes to Prometheus gauge.
"""

import os

from monitoring.metrics import DATABASE_SIZE_BYTES, METRICS_AVAILABLE

# Known database paths relative to project root
_DB_PATHS = [
    ("market_data", "data/market_data.db"),
    ("logic_data", "data/logic_data.db"),
    ("quality_data", "data/quality_data.db"),
]


def collect_database_sizes(project_root: str | None = None) -> None:
    """Scan database files and update size gauge.

    Args:
        project_root: Absolute path to EvoQuant root. Auto-detected if None.
    """
    if not METRICS_AVAILABLE:
        return

    if project_root is None:
        # Assume we're running from project root
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for db_name, rel_path in _DB_PATHS:
        full_path = os.path.join(project_root, rel_path)
        try:
            size = os.path.getsize(full_path)
            DATABASE_SIZE_BYTES.labels(database=db_name).set(size)
        except OSError:
            # File doesn't exist or isn't accessible
            DATABASE_SIZE_BYTES.labels(database=db_name).set(0)
