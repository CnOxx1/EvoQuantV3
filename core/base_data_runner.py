"""BaseDataRunner — 数据层 CLI 模板：--mode bootstrap/once/scheduler。

子类只需设置：
    MODULE_NAME: str — 模块名
    SERVICE_CLASS: type[BaseDataService] — Service 类

示例：
    class MyRunner(BaseDataRunner):
        MODULE_NAME = "my_module"
        SERVICE_CLASS = MyService

    if __name__ == "__main__":
        MyRunner.main()
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from abc import ABC
from typing import Any, ClassVar, Optional, Type

from loguru import logger


class BaseDataRunner(ABC):
    """数据层 CLI 入口基类。"""

    MODULE_NAME: ClassVar[str] = "unnamed_module"
    SERVICE_CLASS: ClassVar[Any] = None  # type: ignore[assignment]
    DEFAULT_INTERVAL: int = 60

    def __init__(self):
        self._running = False
        self._service: Optional[Any] = None

    @classmethod
    def create_service(cls, **kwargs: Any) -> Any:
        """创建 Service 实例。子类可覆盖以注入依赖。"""
        if cls.SERVICE_CLASS is None:
            raise NotImplementedError("SERVICE_CLASS must be set")
        return cls.SERVICE_CLASS(**kwargs)

    @classmethod
    def build_parser(cls) -> argparse.ArgumentParser:
        """构建 CLI 参数解析器。子类可覆盖扩展。"""
        parser = argparse.ArgumentParser(
            description=f"EvoQuant {cls.MODULE_NAME} 数据采集器"
        )
        parser.add_argument(
            "--mode",
            choices=["bootstrap", "once", "scheduler"],
            default="once",
            help="运行模式: bootstrap(历史回填), once(单次), scheduler(定时循环)",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=cls.DEFAULT_INTERVAL,
            help=f"scheduler 模式采集间隔秒数 (默认 {cls.DEFAULT_INTERVAL})",
        )
        return parser

    def run_scheduler(self, interval: int, **kwargs: Any) -> None:
        """定时循环模式。"""
        self._running = True

        def _stop(*_: Any) -> None:
            logger.info("[{}] 收到停止信号", self.MODULE_NAME)
            self._running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info("[{}] scheduler 启动, 间隔 {}s", self.MODULE_NAME, interval)
        service = self._get_service(**kwargs)
        while self._running:
            service.collect_once(**kwargs)
            time.sleep(interval)

    def _get_service(self, **kwargs: Any) -> Any:
        if self._service is None:
            self._service = self.create_service(**kwargs)
        return self._service

    @classmethod
    def main(cls) -> None:
        """CLI 入口点。"""
        parser = cls.build_parser()
        args = parser.parse_args()
        runner = cls()
        kwargs = vars(args)
        mode = kwargs.pop("mode")
        interval = kwargs.pop("interval", cls.DEFAULT_INTERVAL)

        logger.info("[{}] mode={}", cls.MODULE_NAME, mode)

        if mode == "scheduler":
            runner.run_scheduler(interval=interval, **kwargs)
        else:
            service = runner._get_service(**kwargs)
            service.collect_once(mode=mode, **kwargs)
