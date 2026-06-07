from __future__ import annotations

import re
import threading


_PK_COLUMNS = {"id", "symbol", "timestamp", "open_time", "exchange"}
_SELECT_STAR_RE = re.compile(r"\bSELECT\s+\*", re.IGNORECASE)


class ColumnSelector:
    """Rewrites SELECT * queries to explicit column lists."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registry: dict[str, list[str]] = {}

    def register_table(self, table_name: str, columns: list[str]) -> None:
        with self._lock:
            self._registry[table_name] = list(columns)

    def get_columns(self, table_name: str) -> list[str] | None:
        with self._lock:
            cols = self._registry.get(table_name)
            return list(cols) if cols is not None else None

    def rewrite_select(self, sql: str, requested_fields: set[str] | None) -> str:
        if requested_fields is None:
            return sql
        fields = requested_fields | _PK_COLUMNS
        # Only keep fields that could be valid identifiers
        cols = sorted(f for f in fields if re.match(r"^\w+$", f))
        if not cols:
            return sql
        col_list = ", ".join(cols)
        return _SELECT_STAR_RE.sub(f"SELECT {col_list}", sql, count=1)


column_selector = ColumnSelector()
