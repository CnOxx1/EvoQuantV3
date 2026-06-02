"""连接池配置 — 环境变量驱动的数据库连接参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PoolConfig:
    """数据库连接池配置（从环境变量读取）。"""

    # 后端类型: sqlite | postgres
    backend: str = field(default_factory=lambda: os.getenv("DB_BACKEND", "sqlite"))

    # PostgreSQL 连接参数
    pg_host: str = field(default_factory=lambda: os.getenv("PG_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: int(os.getenv("PG_PORT", "5432")))
    pg_database: str = field(default_factory=lambda: os.getenv("PG_DATABASE", "evoquant"))
    pg_user: str = field(default_factory=lambda: os.getenv("PG_USER", "evoquant"))
    pg_password: str = field(default_factory=lambda: os.getenv("PG_PASSWORD", ""))

    # 连接池参数
    pool_min: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MIN", "5")))
    pool_max: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MAX", "20")))

    # Schema 映射（PostgreSQL 用 schema 替代 SQLite 的 ATTACH）
    schema_exchange_data: str = field(
        default_factory=lambda: os.getenv("PG_SCHEMA_EXCHANGE", "exchange_data")
    )
    schema_market_data: str = field(
        default_factory=lambda: os.getenv("PG_SCHEMA_MARKET", "market_data")
    )
    schema_analytics: str = field(
        default_factory=lambda: os.getenv("PG_SCHEMA_ANALYTICS", "analytics")
    )

    @property
    def is_postgres(self) -> bool:
        return self.backend.lower() in ("postgres", "postgresql", "pg")

    @property
    def is_sqlite(self) -> bool:
        return self.backend.lower() in ("sqlite", "sqlite3")
