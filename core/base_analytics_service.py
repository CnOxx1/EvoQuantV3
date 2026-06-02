"""BaseAnalyticsService — 逻辑层 Service 模板基类。

子类实现：
    _get_repositories() — 返回所需 Repository 列表
    _run_analysis(**kwargs) — 执行分析逻辑
    _build_context_bundle(**kwargs) — 构建上下文包

示例：
    class MyAnalytics(BaseAnalyticsService):
        MODULE_NAME = "my_analytics"

        def _run_analysis(self, symbols=None, **kwargs):
            for symbol in symbols:
                score = self._compute(symbol)
                self.repo.save_state(symbol=symbol, score=score)

        def _build_context_bundle(self, **kwargs):
            return {"scores": self.repo.load_history(limit=50)}
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from loguru import logger


class BaseAnalyticsService(ABC):
    """逻辑层 Service 基类。"""

    MODULE_NAME: str = "unnamed_analytics"

    def __init__(self, db: Any, **kwargs: Any):
        self.db = db
        self._initialized = False
        self._run_count = 0
        self._last_run_time: float = 0.0
        self._kwargs = kwargs

    def init_storage(self) -> None:
        """初始化所有 Repository 表（幂等）。"""
        if not self._initialized:
            for repo in self._get_repositories():
                repo.ensure_table()
            self._initialized = True
            logger.info("[{}] Repository 初始化完成", self.MODULE_NAME)

    def run_all(self, **kwargs: Any) -> dict[str, Any]:
        """执行完整分析流程，返回结果摘要。"""
        self.init_storage()
        start = time.time()
        try:
            result = self._run_analysis(**kwargs)
            elapsed = time.time() - start
            self._run_count += 1
            self._last_run_time = time.time()
            logger.info(
                "[{}] 分析完成 #{} ({:.2f}s)",
                self.MODULE_NAME, self._run_count, elapsed,
            )
            return {
                "module": self.MODULE_NAME,
                "status": "ok",
                "elapsed_seconds": round(elapsed, 3),
                "run_count": self._run_count,
                "result": result,
            }
        except Exception as exc:
            elapsed = time.time() - start
            logger.error("[{}] 分析失败 ({:.2f}s): {}", self.MODULE_NAME, elapsed, exc)
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
        return {
            "module": self.MODULE_NAME,
            "initialized": self._initialized,
            "run_count": self._run_count,
            "last_run_time": self._last_run_time or None,
        }

    @abstractmethod
    def _get_repositories(self) -> list[Any]:
        """返回本模块需要的 Repository 实例列表。"""

    @abstractmethod
    def _run_analysis(self, **kwargs: Any) -> Any:
        """执行分析逻辑。子类必须实现。"""

    @abstractmethod
    def _build_context_bundle(self, **kwargs: Any) -> dict[str, Any]:
        """构建上下文数据包。子类必须实现。"""
