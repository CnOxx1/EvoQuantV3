"""数据库域路由器：按写入频率将表分配到不同 SQLite 文件或 PostgreSQL schema。

使用方式：
- 数据层模块：router.get_manager(Domain.EXCHANGE_DATA)
- 逻辑层模块：router.get_analytics_db()（自动 ATTACH 其他域 + 创建 VIEW）
- 测试/向后兼容：DatabaseRouter(single_file=True) 或直接 DBManager(":memory:")
- PostgreSQL: DB_BACKEND=postgres 时自动切换后端
"""

from __future__ import annotations

import os
import sqlite3
from enum import Enum
from typing import Any, Optional

from loguru import logger


class Domain(Enum):
    """数据库域枚举。"""

    EXCHANGE_DATA = "exchange_data"
    MARKET_DATA = "market_data"
    ANALYTICS = "analytics"


class _PostgresManagerAdapter:
    """将 PostgresBackend 适配为 DBManager 兼容接口。

    通过创建一个 DBManager 实例但把底层 I/O 方法替换为走 PostgreSQL，
    从而复用 DBManager 所有高层方法（record_collection_run 等）。
    """

    def __init__(self, backend):
        self._backend = backend
        self.conn = self
        self.total_changes = 0  # SQLite 兼容属性

    def execute(self, sql: str, params=()):
        result = self._backend.execute(sql, params)
        self.total_changes += 1
        return result

    def execute_many(self, sql: str, params_list=None):
        if params_list is None:
            params_list = []
        result = self._backend.executemany(sql, params_list)
        self.total_changes += len(params_list) if params_list else 1
        return result

    def executemany(self, sql: str, params_list=None):
        if params_list is None:
            params_list = []
        result = self._backend.executemany(sql, params_list)
        self.total_changes += len(params_list) if params_list else 1
        return result

    def fetch_one(self, sql: str, params=()):
        return self._backend.fetch_one(sql, params)

    def fetch_all(self, sql: str, params=()):
        return self._backend.fetch_all(sql, params)

    def commit(self):
        self._backend.commit()

    def rollback(self):
        self._backend.rollback()

    def close(self):
        self._backend.close()

    def __getattr__(self, name):
        """动态转发 DBManager 高层方法（如 record_collection_run 等）。

        创建一个临时的绑定，把 DBManager 的方法绑定到本适配器实例上，
        这样方法内部调用 self.execute() 时会走 PostgreSQL 后端。
        """
        from database.db_manager import DBManager
        method = getattr(DBManager, name, None)
        if method is not None and callable(method):
            import types
            return types.MethodType(method, self)
        raise AttributeError(
            f"'_PostgresManagerAdapter' object has no attribute '{name}'"
        )

    def rollback(self):
        self._backend.rollback()

    def close(self):
        self._backend.close()

    def init_exchange_data_tables(self):
        """从 SQLite schema 自动建表到 PostgreSQL。"""
        self._sync_tables_from_sqlite("exchange_data")

    def init_market_data_tables(self):
        """从 SQLite schema 自动建表到 PostgreSQL。"""
        self._sync_tables_from_sqlite("market_data")

    def init_analytics_tables(self):
        """从 SQLite schema 自动建表到 PostgreSQL。"""
        self._sync_tables_from_sqlite("analytics")

    def _sync_tables_from_sqlite(self, domain_name: str):
        """从对应的 SQLite 数据库提取 CREATE TABLE DDL 并在 PostgreSQL 中执行。"""
        import sqlite3 as _sqlite3
        from database.backends.query_adapter import adapt_query
        from config.settings import (
            EXCHANGE_DATA_DB_PATH,
            MARKET_DATA_DB_PATH,
            ANALYTICS_DB_PATH,
        )

        path_map = {
            "exchange_data": EXCHANGE_DATA_DB_PATH,
            "market_data": MARKET_DATA_DB_PATH,
            "analytics": ANALYTICS_DB_PATH,
        }
        db_path = path_map[domain_name]
        if not os.path.exists(db_path):
            return

        conn = _sqlite3.connect(db_path)
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
        ).fetchall()
        conn.close()

        for name, ddl in tables:
            try:
                pg_ddl = adapt_query(ddl)
                # SQLite 的 AUTOINCREMENT 由 query_adapter 处理
                # 确保用 IF NOT EXISTS
                if "IF NOT EXISTS" not in pg_ddl.upper():
                    pg_ddl = pg_ddl.replace(
                        "CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1
                    )
                self._backend.execute(pg_ddl, ())
                self._backend.commit()
            except Exception as exc:
                try:
                    self._backend.rollback()
                except Exception:
                    pass
                # 表已存在等非致命错误静默跳过
                if "already exists" not in str(exc).lower():
                    logger.debug(
                        "PostgreSQL 建表跳过 {}.{}: {}", domain_name, name, exc
                    )

    def attach_domain_views(self, *args, **kwargs):
        """PostgreSQL 使用 schema 代替 ATTACH，此处为兼容性空操作。"""
        pass

    def init_storage(self):
        """PostgreSQL 表由 Alembic 管理，此处为兼容性空操作。"""
        pass


class DatabaseRouter:
    """根据域返回对应的 DBManager 实例。

    Parameters
    ----------
    db_dir : str | None
        数据库文件所在目录，默认使用 config.settings.DATABASE_DIR。
    single_file : bool
        为 True 时所有域退化为同一文件（向后兼容/测试用）。
    single_file_path : str | None
        single_file 模式下使用的文件路径。
    """

    def __init__(
        self,
        db_dir: Optional[str] = None,
        single_file: bool = False,
        single_file_path: Optional[str] = None,
    ):
        from config.settings import DATABASE_DIR, DATABASE_SPLIT_ENABLED, DB_BACKEND

        self.db_dir = db_dir or DATABASE_DIR
        self.single_file = single_file or (not DATABASE_SPLIT_ENABLED)
        self._single_file_path = single_file_path
        self._managers: dict[Domain, Any] = {}
        self._use_postgres = DB_BACKEND == "postgres"

    def _path_for(self, domain: Domain) -> str:
        if self.single_file:
            if self._single_file_path:
                return self._single_file_path
            from config.settings import DATABASE_PATH

            return DATABASE_PATH
        from config.settings import (
            ANALYTICS_DB_PATH,
            EXCHANGE_DATA_DB_PATH,
            MARKET_DATA_DB_PATH,
        )

        mapping = {
            Domain.EXCHANGE_DATA: EXCHANGE_DATA_DB_PATH,
            Domain.MARKET_DATA: MARKET_DATA_DB_PATH,
            Domain.ANALYTICS: ANALYTICS_DB_PATH,
        }
        return mapping[domain]

    def get_manager(self, domain: Domain) -> Any:
        """获取指定域的数据库管理器（懒加载、缓存）。

        DB_BACKEND=postgres 时返回 _PostgresManagerAdapter，否则返回 DBManager（SQLite）。
        """
        if domain not in self._managers:
            if self._use_postgres:
                self._managers[domain] = self._create_postgres_manager(domain)
            else:
                self._managers[domain] = self._create_sqlite_manager(domain)
        return self._managers[domain]

    def _create_postgres_manager(self, domain: Domain) -> _PostgresManagerAdapter:
        """创建 PostgreSQL 后端适配器。"""
        from database.pool_config import PoolConfig
        from database.backends.postgres_backend import PostgresBackend

        cfg = PoolConfig()
        schema = {
            Domain.EXCHANGE_DATA: cfg.schema_exchange_data,
            Domain.MARKET_DATA: cfg.schema_market_data,
            Domain.ANALYTICS: cfg.schema_analytics,
        }[domain]
        backend = PostgresBackend(
            host=cfg.pg_host,
            port=cfg.pg_port,
            database=cfg.pg_database,
            user=cfg.pg_user,
            password=cfg.pg_password,
            schema=schema,
            pool_min=cfg.pool_min,
            pool_max=cfg.pool_max,
        )
        logger.info("PostgreSQL 后端已创建: domain={}, schema={}", domain.value, schema)
        return _PostgresManagerAdapter(backend)

    def _create_sqlite_manager(self, domain: Domain):
        """创建 SQLite DBManager（原有逻辑）。"""
        from database.db_manager import DBManager

        db = DBManager(db_path=self._path_for(domain))
        # 自动初始化域表，确保即使未显式调用 init_storage 也能查询
        if domain == Domain.EXCHANGE_DATA:
            db.init_exchange_data_tables()
        elif domain == Domain.MARKET_DATA:
            db.init_market_data_tables()
        elif domain == Domain.ANALYTICS:
            db.init_analytics_tables()
        # 自动补充优化索引
        self._ensure_domain_indexes(domain, db)
        return db

    def _ensure_domain_indexes(self, domain: Domain, db: "DBManager") -> None:
        """为指定域补充优化索引（幂等）。"""
        try:
            from database.indexes import (
                ANALYTICS_INDEXES,
                EXCHANGE_DATA_INDEXES,
                MARKET_DATA_INDEXES,
                _apply_indexes,
            )

            mapping = {
                Domain.EXCHANGE_DATA: EXCHANGE_DATA_INDEXES,
                Domain.MARKET_DATA: MARKET_DATA_INDEXES,
                Domain.ANALYTICS: ANALYTICS_INDEXES,
            }
            indexes = mapping.get(domain, [])
            if indexes:
                _apply_indexes(db.conn, indexes)
                db.conn.commit()
        except Exception as exc:
            logger.debug("域 {} 索引优化跳过: {}", domain.value, exc)

    def get_analytics_db(self) -> Any:
        """返回 analytics 域管理器，附带跨域读取能力。

        SQLite: ATTACH + VIEW 跨域读取
        PostgreSQL: schema 直接跨域读取（无需 ATTACH）
        """
        db = self.get_manager(Domain.ANALYTICS)
        if not self._use_postgres:
            db.init_analytics_tables()
            if not self.single_file:
                exchange_path = self._path_for(Domain.EXCHANGE_DATA)
                market_path = self._path_for(Domain.MARKET_DATA)
                if os.path.exists(exchange_path) and os.path.exists(market_path):
                    db.attach_domain_views(exchange_path, market_path)
        return db

    def get_exchange_db(self) -> "DBManager":
        """返回 exchange_data 域 DBManager。"""
        return self.get_manager(Domain.EXCHANGE_DATA)

    def get_market_db(self) -> "DBManager":
        """返回 market_data 域 DBManager。"""
        return self.get_manager(Domain.MARKET_DATA)

    def get_market_data_db(self) -> "DBManager":
        """返回 market_data 域 DBManager（get_market_db 的别名）。"""
        return self.get_manager(Domain.MARKET_DATA)

    def close_all(self):
        """关闭所有域连接。"""
        for manager in self._managers.values():
            manager.close()
        self._managers.clear()

    def get_backend_health(self) -> dict[str, Any]:
        """返回当前后端健康状态（供 /health/db 使用）。"""
        from config.settings import DB_BACKEND

        if DB_BACKEND == "postgres":
            from database.pool_config import PoolConfig
            from database.backends.postgres_backend import PostgresBackend

            cfg = PoolConfig()
            # 尝试获取池状态（不一定有活跃连接）
            return {
                "backend": "postgres",
                "config": {
                    "host": cfg.pg_host,
                    "port": cfg.pg_port,
                    "database": cfg.pg_database,
                    "pool_min": cfg.pool_min,
                    "pool_max": cfg.pool_max,
                },
                "domains": [d.value for d in Domain],
            }
        else:
            import os
            from config.settings import (
                EXCHANGE_DATA_DB_PATH,
                MARKET_DATA_DB_PATH,
                ANALYTICS_DB_PATH,
            )

            def _db_info(path: str) -> dict:
                exists = os.path.exists(path)
                return {
                    "path": path,
                    "exists": exists,
                    "size_mb": round(os.path.getsize(path) / 1024 / 1024, 1) if exists else 0,
                }

            return {
                "backend": "sqlite",
                "databases": {
                    "exchange_data": _db_info(EXCHANGE_DATA_DB_PATH),
                    "market_data": _db_info(MARKET_DATA_DB_PATH),
                    "analytics": _db_info(ANALYTICS_DB_PATH),
                },
            }
