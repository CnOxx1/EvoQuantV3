"""逻辑层全链路定时编排 CLI 入口。

用法：
  # 默认定时模式（每 5 分钟执行一次全链路）
  python -m logic_layer.logic_pipeline.runner --mode scheduler

  # 只执行一次
  python -m logic_layer.logic_pipeline.runner --mode once

  # 自定义间隔（秒）
  python -m logic_layer.logic_pipeline.runner --mode scheduler --interval 600
"""

from __future__ import annotations

import argparse
import json

from config.logging import setup_logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="逻辑层全链路定时编排守护进程"
    )
    parser.add_argument(
        "--mode",
        choices=["scheduler", "once"],
        default="scheduler",
        help="scheduler: 定时循环执行; once: 执行一次后退出",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="调度间隔（秒），默认 300（5 分钟）",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("logic_pipeline")

    from logic_layer.logic_pipeline.service import (
        build_scheduler,
        run_full_pipeline,
    )

    if args.mode == "once":
        result = run_full_pipeline()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    scheduler = build_scheduler(interval_seconds=args.interval)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
