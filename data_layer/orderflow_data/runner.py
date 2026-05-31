"""orderflow_data 模块运行入口。"""

import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from data_layer.orderflow_data.service import OrderflowDataService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="订单流数据模块运行入口")
    parser.add_argument(
        "--mode", choices=["bootstrap", "once", "scheduler"], default="once",
        help="bootstrap: 回填数据；once: 单次采集；scheduler: 定时采集（每 5 分钟）",
    )
    parser.add_argument("--symbols", type=str, default="", help="按标的过滤，逗号分隔")
    parser.add_argument("--async-scheduler", action="store_true", help="使用 AsyncIOScheduler")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    return parser


def main():
    args = build_parser().parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None

    setup_logger("orderflow_data")
    service = OrderflowDataService()
    service.init_storage()

    if args.print_context:
        bundle = service.load_latest_context_bundle(symbols=symbols)
        print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap(symbols=symbols)
    elif args.mode == "once":
        service.collect_once(symbols=symbols)
    else:
        if args.async_scheduler:
            _run_async_scheduler(service, symbols)
        else:
            _run_blocking_scheduler(service, symbols)
        return
    service.close()


def _run_blocking_scheduler(service, symbols):
    scheduler = service.build_scheduler(symbols=symbols)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 orderflow_data...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    logger.info("orderflow_data 调度器已启动（BlockingScheduler），每 5 分钟采集")
    try:
        scheduler.start()
    finally:
        service.close()


def _run_async_scheduler(service, symbols):
    scheduler = service.build_async_scheduler(symbols=symbols)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 orderflow_data 异步调度器...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    scheduler.start()
    logger.info("orderflow_data 异步调度器已启动")
    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        service.close()
        loop.close()


if __name__ == "__main__":
    main()
