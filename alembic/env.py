"""Alembic 多 schema 迁移环境。"""

import os
import sys
from logging.config import fileConfig

from alembic import context

# 将项目根目录加入 Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

# 从环境变量覆盖数据库 URL
db_url = os.getenv("PG_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)
else:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    database = os.getenv("PG_DATABASE", "evoquant")
    user = os.getenv("PG_USER", "evoquant")
    password = os.getenv("PG_PASSWORD", "")
    url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    config.set_main_option("sqlalchemy.url", url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

SCHEMAS = ["exchange_data", "market_data", "analytics"]


def run_migrations_offline() -> None:
    """离线模式运行迁移（生成 SQL 脚本）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式运行迁移（直接执行）。"""
    from sqlalchemy import create_engine, pool, text

    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # 确保 schema 存在
        for schema in SCHEMAS:
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
