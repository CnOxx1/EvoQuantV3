"""Database Backends — 可插拔数据库后端接口。

使用方式：
    from database.backends import get_backend

    backend = get_backend()  # 根据 DB_BACKEND 环境变量自动选择
"""

from database.backends.base import DatabaseBackend
from database.backends.sqlite_backend import SQLiteBackend


def get_backend(
    backend_type: str = "sqlite",
    **kwargs,
) -> DatabaseBackend:
    """工厂函数：根据类型创建数据库后端。

    Parameters
    ----------
    backend_type : str
        "sqlite" 或 "postgres"
    **kwargs
        传递给对应 Backend 构造器的参数
    """
    if backend_type == "sqlite":
        return SQLiteBackend(**kwargs)
    elif backend_type == "postgres":
        from database.backends.postgres_backend import PostgresBackend
        return PostgresBackend(**kwargs)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}. Use 'sqlite' or 'postgres'.")


__all__ = [
    "DatabaseBackend",
    "SQLiteBackend",
    "get_backend",
]
