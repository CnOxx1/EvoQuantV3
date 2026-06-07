"""连接池配置 — 环境变量驱动的数据库连接参数。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PoolConfig:
    """数据库连接池配置（从环境变量读取）。

    优化 #10: 集成 AdaptivePoolManager，运行时动态调整池大小。
    """

    # 后端类型: sqlite | postgres
    backend: str = field(default_factory=lambda: os.getenv("DB_BACKEND", "sqlite"))

    # PostgreSQL 连接参数
    pg_host: str = field(default_factory=lambda: os.getenv("PG_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: int(os.getenv("PG_PORT", "5432")))
    pg_database: str = field(default_factory=lambda: os.getenv("PG_DATABASE", "evoquant"))
    pg_user: str = field(default_factory=lambda: os.getenv("PG_USER", "evoquant"))
    pg_password: str = field(default_factory=lambda: os.getenv("PG_PASSWORD", ""))

    # 连接池参数
    pool_min: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MIN", "10")))
    pool_max: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MAX", "50")))
    pool_overflow: int = field(default_factory=lambda: int(os.getenv("DB_POOL_OVERFLOW", "10")))
    idle_timeout: int = field(default_factory=lambda: int(os.getenv("DB_POOL_IDLE_TIMEOUT", "300")))

    # 自适应池是否启用
    adaptive_enabled: bool = field(
        default_factory=lambda: os.getenv("DB_POOL_ADAPTIVE", "1") == "1"
    )

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

    def get_adaptive_pool_size(self) -> tuple[int, int]:
        """获取自适应池推荐大小，未启用时返回静态配置。"""
        if not self.adaptive_enabled:
            return (self.pool_min, self.pool_max)
        from database.adaptive_pool import adaptive_pool
        return adaptive_pool.recommend_size()
