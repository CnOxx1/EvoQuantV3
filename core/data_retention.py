from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetentionPolicy:
    table_name: str
    hot_days: int
    warm_days: int
    archive_after_days: int
    rollup_interval: str


class DataRetentionService:
    def __init__(self) -> None:
        self._policies: dict[str, RetentionPolicy] = {}
        defaults = [
            ("tickers", 7, 30, 90, "5m"),
            ("orderbooks", 3, 14, 30, "1m"),
            ("klines", 90, 365, 730, "1d"),
            ("funding_rates", 30, 365, 730, "1h"),
            ("technical_indicators", 30, 180, 365, "1h"),
        ]
        for name, hot, warm, archive, rollup in defaults:
            self._policies[name] = RetentionPolicy(
                table_name=name,
                hot_days=hot,
                warm_days=warm,
                archive_after_days=archive,
                rollup_interval=rollup,
            )

    def get_policy(self, table_name: str) -> RetentionPolicy:
        if table_name not in self._policies:
            raise KeyError(f"No retention policy defined for '{table_name}'")
        return self._policies[table_name]

    def get_cleanup_sql(self, table_name: str) -> str:
        policy = self.get_policy(table_name)
        return (
            f"DELETE FROM {policy.table_name} "
            f"WHERE timestamp < NOW() - INTERVAL '{policy.archive_after_days} days';"
        )

    def get_rollup_sql(self, table_name: str, interval: str | None = None) -> str:
        policy = self.get_policy(table_name)
        iv = interval or policy.rollup_interval
        dest = f"{policy.table_name}_rollup_{iv.replace(' ', '')}"
        return (
            f"INSERT INTO {dest} (bucket, open, high, low, close, volume) "
            f"SELECT time_bucket('{iv}', timestamp) AS bucket, "
            f"first(price, timestamp) AS open, max(price) AS high, "
            f"min(price) AS low, last(price, timestamp) AS close, "
            f"sum(volume) AS volume "
            f"FROM {policy.table_name} "
            f"WHERE timestamp >= NOW() - INTERVAL '{policy.warm_days} days' "
            f"GROUP BY bucket;"
        )


retention_service = DataRetentionService()
