"""DatabaseBackend ABC — 数据库后端接口定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence


class DatabaseBackend(ABC):
    """数据库后端抽象基类。

    所有后端（SQLite、PostgreSQL）必须实现此接口。
    DBManager 通过此接口与底层数据库交互。
    """

    @abstractmethod
    def execute(self, sql: str, params: Sequence = ()) -> Any:
        """执行写操作（INSERT/UPDATE/DELETE/DDL）。"""

    @abstractmethod
    def executemany(self, sql: str, params_list: Sequence[Sequence]) -> Any:
        """批量执行。"""

    @abstractmethod
    def fetch_one(self, sql: str, params: Sequence = ()) -> Optional[Any]:
        """查询单行。"""

    @abstractmethod
    def fetch_all(self, sql: str, params: Sequence = ()) -> list[Any]:
        """查询所有行。"""

    @abstractmethod
    def commit(self) -> None:
        """提交事务。"""

    @abstractmethod
    def rollback(self) -> None:
        """回滚事务。"""

    @abstractmethod
    def close(self) -> None:
        """关闭连接/归还连接池。"""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """返回连接健康状态。"""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """连接是否存活。"""
