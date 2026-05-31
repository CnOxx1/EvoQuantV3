"""数据库域路由器：按写入频率将表分配到不同 SQLite 文件。

使用方式：
- 数据层模块：router.get_manager(Domain.EXCHANGE_DATA)
- 逻辑层模块：router.get_analytics_db()（自动 ATTACH 其他域 + 创建 VIEW）
- 测试/向后兼容：DatabaseRouter(single_file=True) 或直接 DBManager(":memory:")
"""

from __future__ import annotations

import os
import sqlite3
from enum import Enum
from typing import Optional

from loguru import logger


class Domain(Enum):
    """数据库域枚举。"""

    EXCHANGE_DATA = "exchange_data"
    MARKET_DATA = "market_data"
    ANALYTICS = "analytics"


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
        from config.settings import DATABASE_DIR, DATABASE_SPLIT_ENABLED

        self.db_dir = db_dir or DATABASE_DIR
        self.single_file = single_file or (not DATABASE_SPLIT_ENABLED)
        self._single_file_path = single_file_path
        self._managers: dict[Domain, "DBManager"] = {}

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

    def get_manager(self, domain: Domain) -> "DBManager":
        """获取指定域的 DBManager（懒加载、缓存、自动建表）。"""
        if domain not in self._managers:
            from database.db_manager import DBManager

            db = DBManager(db_path=self._path_for(domain))
            # 自动初始化域表，确保即使未显式调用 init_storage 也能查询
            if domain == Domain.EXCHANGE_DATA:
                db.init_exchange_data_tables()
            elif domain == Domain.MARKET_DATA:
                db.init_market_data_tables()
            elif domain == Domain.ANALYTICS:
                db.init_analytics_tables()
            self._managers[domain] = db
        return self._managers[domain]

    def get_analytics_db(self) -> "DBManager":
        """返回 analytics 域 DBManager，附带 ATTACH + VIEW 跨域读取能力。

        逻辑层模块使用此方法获取 DB 实例：
        - 写入落到 analytics.db 本地表
        - 读取通过 VIEW 透明访问 exchange_data.db / market_data.db
        """
        db = self.get_manager(Domain.ANALYTICS)
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

    def close_all(self):
        """关闭所有域连接。"""
        for manager in self._managers.values():
            manager.close()
        self._managers.clear()
