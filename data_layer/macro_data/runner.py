import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from config.settings import MACRO_CONFIG
from data_layer.macro_data.service import MacroDataService
from data_layer.macro_data.sources import load_macro_factors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="宏观数据模块运行入口")
    parser.add_argument(
        "--mode",
        choices=["bootstrap", "once", "scheduler"],
        default="once",
        help="bootstrap: 初始化因子目录+历史回填；once: 执行一次最新采集；scheduler: 启动定时采集",
    )
    parser.add_argument(
        "--factors",
        type=str,
        default="",
        help="按 factor_id 过滤，逗号分隔，例如 dxy,nasdaq_100",
    )
    parser.add_argument(
        "--market-history-days",
        type=int,
        default=MACRO_CONFIG["bootstrap_market_history_days"],
        help="bootstrap 模式下小时级市场因子的历史回填天数",
    )
    parser.add_argument(
        "--daily-history-years",
        type=int,
        default=MACRO_CONFIG["bootstrap_daily_history_years"],
        help="bootstrap 模式下日频历史回填年数",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="scheduler 模式下跳过启动时的初始化历史回填",
    )
    parser.add_argument(
        "--async-scheduler",
        action="store_true",
        help="scheduler 模式下使用 AsyncIOScheduler（推荐）",
    )
    parser.add_argument(
        "--strict-bootstrap",
        action="store_true",
        help="bootstrap 阶段遇到单个上游失败时立即退出，而不是保留部分成功结果继续运行",
    )
    parser.add_argument(
        "--list-factors",
        action="store_true",
        help="列出当前宏观 factor 注册表",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出 AI 可直接读取的宏观上下文 bundle",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出当前宏观 source 覆盖情况、最近采集状态和新鲜度",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("macro_data")

    factor_ids = [
        item.strip()
        for item in args.factors.split(",")
        if item.strip()
    ] or None

    service = MacroDataService()
    service.init_storage()

    if args.list_factors:
        rows = [
            {
                "factor_id": factor.factor_id,
                "name": factor.name,
                "category": factor.category,
                "factor_type": factor.factor_type,
                "default_interval": factor.default_interval,
                "source_name": factor.source_name,
                "enabled": factor.enabled,
            }
            for factor in load_macro_factors(enabled_only=False, factor_ids=factor_ids)
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.print_context:
        bundle = service.load_latest_context_bundle(
            factor_ids=factor_ids,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.print_coverage:
        bundle = service.load_source_coverage(
            factor_ids=factor_ids,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap(
            factor_ids=factor_ids,
            market_history_days=args.market_history_days,
            daily_history_years=args.daily_history_years,
            continue_on_error=not args.strict_bootstrap,
        )
        service.close()
        return

    if args.mode == "once":
        service.collect_once(factor_ids=factor_ids)
        service.close()
        return

    if not args.skip_bootstrap:
        try:
            service.bootstrap(
                factor_ids=factor_ids,
                market_history_days=args.market_history_days,
                daily_history_years=args.daily_history_years,
                continue_on_error=not args.strict_bootstrap,
            )
        except Exception as exc:
            if args.strict_bootstrap:
                service.close()
                raise
            logger.exception(
                "macro_data 启动回填失败，但保留常驻调度继续运行: {}: {}",
                type(exc).__name__,
                exc,
            )

    if args.async_scheduler:
        _run_async_scheduler(service, factor_ids)
    else:
        _run_blocking_scheduler(service, factor_ids)


def _run_blocking_scheduler(service, factor_ids):
    """使用 BlockingScheduler 运行（传统模式）。"""
    scheduler = service.build_scheduler(factor_ids=factor_ids)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 macro_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("macro_data 调度器已启动（BlockingScheduler），按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


def _run_async_scheduler(service, factor_ids):
    """使用 AsyncIOScheduler 运行 — 利用 asyncio 事件循环。"""
    scheduler = service.build_async_scheduler(factor_ids=factor_ids)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 macro_data 异步调度器...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()
    logger.info("macro_data 异步调度器已启动（AsyncIOScheduler），按 Ctrl+C 停止")
    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        service.close()
        loop.close()


if __name__ == "__main__":
    main()
