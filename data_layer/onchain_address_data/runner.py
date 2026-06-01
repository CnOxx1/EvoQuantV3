"""链上地址行为数据模块运行入口。"""

import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from data_layer.onchain_address_data.service import OnchainAddressService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="链上地址行为数据模块运行入口")
    parser.add_argument(
        "--mode", choices=["bootstrap", "once", "scheduler"], default="once",
        help="bootstrap: 回填数据；once: 单次采集；scheduler: 定时采集（每10分钟）",
    )
    parser.add_argument("--async-scheduler", action="store_true", help="使用 AsyncIOScheduler")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    parser.add_argument(
        "--addresses", nargs="*", default=None,
        help="指定采集的地址列表（覆盖默认跟踪地址）",
    )
    return parser


def main():
    args = build_parser().parse_args()

    setup_logger("onchain_address_data")
    service = OnchainAddressService()
    service.init_storage()

    # 如果指定了地址列表，覆盖默认跟踪地址
    if args.addresses:
        service.TRACKED_ADDRESSES = args.addresses
        logger.info(f"使用自定义地址列表: {len(args.addresses)} 个地址")

    if args.print_context:
        bundle = service.load_latest_context_bundle()
        print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap()
    elif args.mode == "once":
        service.collect_once()
    else:
        if args.async_scheduler:
            _run_async_scheduler(service)
        else:
            _run_blocking_scheduler(service)
        return
    service.close()


def _run_blocking_scheduler(service):
    """运行阻塞式调度器。"""
    scheduler = service.build_scheduler()

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 onchain_address_data...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    logger.info("onchain_address_data 调度器已启动（BlockingScheduler），每10分钟采集")
    try:
        scheduler.start()
    finally:
        service.close()


def _run_async_scheduler(service):
    """运行异步调度器。"""
    scheduler = service.build_async_scheduler()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 onchain_address_data 异步调度器...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    scheduler.start()
    logger.info("onchain_address_data 异步调度器已启动")
    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        service.close()
        loop.close()


if __name__ == "__main__":
    main()
