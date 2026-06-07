"""database.managers — DBManager 模块化拆分入口。

将原 3070 行的 db_manager.py 拆分为聚焦模块，
通过 Mixin 模式组合还原完整 DBManager 类。

架构：
    ConnectionMixin  — 连接管理、线程本地存储
    SchemaUtilsMixin — 字段检测、补列、列定义
    TableCreationMixin — 所有 _create_*_table 方法
    SyncSnapshotMixin — latest 表同步、域初始化
    QueryMethodsMixin — execute/fetch/close 等查询方法
    DataWriteMixin   — record_collection_run 等写入方法

向后兼容：
    from database.managers import DBManager
    from database.db_manager import DBManager  # 也可以
"""

from database.managers.connection import ConnectionMixin
from database.managers.schema_utils import SchemaUtilsMixin
from database.managers.query_methods import QueryMethodsMixin


class DBManager(ConnectionMixin, SchemaUtilsMixin, QueryMethodsMixin):
    """SQLite 数据库连接与表管理 — Mixin 组合架构。

    注意：完整的表创建和写入方法仍通过原 db_manager.py 提供，
    本包通过 Mixin 提供核心的连接、查询、schema 管理能力。
    原 db_manager.py 继承本类并保留所有表创建方法。
    """
    pass
