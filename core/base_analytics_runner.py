"""BaseAnalyticsRunner — 逻辑层 CLI 模板：--print-context 支持。

子类只需设置：
    MODULE_NAME: str — 模块名
    SERVICE_CLASS: type[BaseAnalyticsService] — Service 类

示例：
    class MyRunner(BaseAnalyticsRunner):
        MODULE_NAME = "my_analytics"
        SERVICE_CLASS = MyAnalyticsService

    if __name__ == "__main__":
        MyRunner.main()
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, ClassVar, Optional

from loguru import logger


class BaseAnalyticsRunner:
    """逻辑层 CLI 入口基类。"""

    MODULE_NAME: ClassVar[str] = "unnamed_analytics"
    SERVICE_CLASS: ClassVar[Any] = None  # type: ignore[assignment]

    def __init__(self):
        self._service: Optional[Any] = None

    @classmethod
    def create_service(cls, **kwargs: Any) -> Any:
        """创建 Service 实例。子类可覆盖以注入依赖。"""
        if cls.SERVICE_CLASS is None:
            raise NotImplementedError("SERVICE_CLASS must be set")
        return cls.SERVICE_CLASS(**kwargs)

    @classmethod
    def build_parser(cls) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description=f"EvoQuant {cls.MODULE_NAME} 分析引擎"
        )
        parser.add_argument(
            "--print-context",
            action="store_true",
            help="输出当前上下文快照 (JSON) 到 stdout",
        )
        parser.add_argument(
            "--run",
            action="store_true",
            help="执行分析流程",
        )
        return parser

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
        kwargs = {k: v for k, v in vars(args).items() if k not in ("print_context", "run")}

        service = runner._get_service(**kwargs)

        if args.print_context:
            bundle = service.build_context(**kwargs)
            json.dump(bundle, sys.stdout, ensure_ascii=False, indent=2, default=str)
            sys.stdout.write("\n")
        elif args.run:
            result = service.run_all(**kwargs)
            logger.info("[{}] 结果: {}", cls.MODULE_NAME, result.get("status"))
        else:
            parser.print_help()
