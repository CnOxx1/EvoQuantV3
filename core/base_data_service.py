"""BaseDataService — 数据层 Service 模板方法基类。

子类只需实现：
    _init_tables() — 创建/确认数据表
    _do_collect(**kwargs) — 执行一次数据采集
    _build_context_bundle(**kwargs) — 构建上下文快照

示例：
    class MyService(BaseDataService):
        MODULE_NAME = "my_module"

        def _init_tables(self):
            self.db.execute("CREATE TABLE IF NOT EXISTS ...")

        def _do_collect(self, **kwargs):
            data = self.client.fetch_data()
            self.db.execute("INSERT ...", data)

        def _build_context_bundle(self, **kwargs):
            return {"latest": self.db.fetch_one("SELECT ...")}
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from loguru import logger


class BaseDataService(ABC):
    """数据层 Service 基类（模板方法模式）。"""

    MODULE_NAME: str = "unnamed_module"

    def __init__(self, db: Any, client: Optional[Any] = None, **kwargs: Any):
        self.db = db
        self.client = client
        self._initialized = False
        self._collect_count = 0
        self._last_collect_time: float = 0.0
        self._kwargs = kwargs

    def init_storage(self) -> None:
        """初始化存储（幂等）。"""
        if not self._initialized:
            self._init_tables()
            self._initialized = True
            logger.info("[{}] 存储初始化完成", self.MODULE_NAME)

    def collect_once(self, **kwargs: Any) -> dict[str, Any]:
        """执行单次采集，返回采集结果摘要。"""
        self.init_storage()
        start = time.time()
        try:
            result = self._do_collect(**kwargs)
            elapsed = time.time() - start
            self._collect_count += 1
            self._last_collect_time = time.time()
            logger.info(
                "[{}] 采集完成 #{} ({:.2f}s)",
                self.MODULE_NAME, self._collect_count, elapsed,
            )
            return {
                "module": self.MODULE_NAME,
                "status": "ok",
                "elapsed_seconds": round(elapsed, 3),
                "collect_count": self._collect_count,
                "result": result,
            }
        except Exception as exc:
            elapsed = time.time() - start
            logger.error(
                "[{}] 采集失败 ({:.2f}s): {}",
                self.MODULE_NAME, elapsed, exc,
            )
            return {
                "module": self.MODULE_NAME,
                "status": "error",
                "elapsed_seconds": round(elapsed, 3),
                "error": str(exc),
            }

    def build_context(self, **kwargs: Any) -> dict[str, Any]:
        """构建上下文快照供 AI / 策略层使用。"""
        self.init_storage()
        return self._build_context_bundle(**kwargs)

    @property
    def stats(self) -> dict[str, Any]:
        """返回模块运行统计。"""
        return {
            "module": self.MODULE_NAME,
            "initialized": self._initialized,
            "collect_count": self._collect_count,
            "last_collect_time": self._last_collect_time or None,
        }

    @abstractmethod
    def _init_tables(self) -> None:
        """创建数据表（幂等）。子类必须实现。"""

    @abstractmethod
    def _do_collect(self, **kwargs: Any) -> Any:
        """执行一次数据采集。子类必须实现。"""

    @abstractmethod
    def _build_context_bundle(self, **kwargs: Any) -> dict[str, Any]:
        """构建上下文数据包。子类必须实现。"""
