"""etf_flow_data 模块运行入口。"""

import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from data_layer.etf_flow_data.service import EtfFlowDataService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETF 资金流数据模块运行入口")
    parser.add_argument(
        "--mode", choices=["bootstrap", "once", "scheduler"], default="once",
        help="bootstrap: 回填数据；once: 单次采集；scheduler: 定时采集",
    )
    parser.add_argument("--assets", type=str, default="", help="按资产过滤，逗号分隔 (BTC,ETH)")
    parser.add_argument("--async-scheduler", action="store_true", help="使用 AsyncIOScheduler")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    return parser


def main():
    args = build_parser().parse_args()
    assets = [s.strip() for s in args.assets.split(",") if s.strip()] or None

    setup_logger("etf_flow_data")
    service = EtfFlowDataService()
    service.init_storage()

    if args.print_context:
        bundle = service.load_latest_context_bundle(assets=assets)
        print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap(assets=assets)
    elif args.mode == "once":
        service.collect_once(assets=assets)
    else:
        if args.async_scheduler:
            _run_async_scheduler(service, assets)
        else:
            _run_blocking_scheduler(service, assets)
        return
    service.close()


def _run_blocking_scheduler(service, assets):
    scheduler = service.build_scheduler(assets=assets)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 etf_flow_data...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    logger.info("etf_flow_data 调度器已启动（BlockingScheduler）")
    try:
        scheduler.start()
    finally:
        service.close()


def _run_async_scheduler(service, assets):
    scheduler = service.build_async_scheduler(assets=assets)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 etf_flow_data 异步调度器...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    scheduler.start()
    logger.info("etf_flow_data 异步调度器已启动")
    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        service.close()
        loop.close()


if __name__ == "__main__":
    main()
