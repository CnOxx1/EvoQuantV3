import argparse
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from data_layer.exchange_data.service import ExchangeDataService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="交易所数据模块运行入口")
    parser.add_argument(
        "--mode",
        choices=[
            "bootstrap",
            "once",
            "scheduler",
            "context-burst",
            "funding-backfill",
            "derivatives-once",
            "liquidations-repair",
        ],
        default="once",
        help="bootstrap: 初始化市场信息+历史K线；once: 执行一次完整采集；scheduler: 启动定时采集；context-burst: 高频积累ticker/funding/orderbook/trades；funding-backfill: 回填历史资金费率；derivatives-once: 单独执行一轮衍生品结构采集；liquidations-repair: 基于 raw_payload_json 修复旧版清算字段语义",
    )
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="跳过历史K线回填（适合快速验证连通性）",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="scheduler 模式下跳过启动时的初始化采集",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=120,
        help="context-burst 模式的采样轮数",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=3.0,
        help="context-burst 模式的轮次间隔秒数",
    )
    parser.add_argument(
        "--funding-every",
        type=int,
        default=20,
        help="context-burst 模式下每多少轮补采一次 funding",
    )
    parser.add_argument(
        "--funding-history-days",
        type=int,
        default=0,
        help="context-burst 或 funding-backfill 模式下回填多少天的 funding 历史",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出 exchange_data 当前 AI 上下文 bundle",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出 exchange_data 当前 source 覆盖率、运行状态与新鲜度",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("exchange_data")

    service = ExchangeDataService()
    service.init_storage()

    if args.print_context:
        print(
            json.dumps(
                service.load_latest_market_context_bundle(),
                ensure_ascii=False,
                indent=2,
            )
        )
        service.close()
        return

    if args.print_coverage:
        print(
            json.dumps(
                service.load_source_coverage(),
                ensure_ascii=False,
                indent=2,
            )
        )
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap(include_backfill=not args.skip_backfill)
        service.close()
        return

    if args.mode == "once":
        service.collect_once(include_backfill=not args.skip_backfill)
        service.close()
        return

    if args.mode == "funding-backfill":
        service.backfill_funding_history(days=args.funding_history_days or 30)
        service.close()
        return

    if args.mode == "derivatives-once":
        service.collect_derivatives_once()
        service.close()
        return

    if args.mode == "liquidations-repair":
        repair_summary = service.repair_liquidation_semantics_from_raw_payload()
        print(json.dumps(repair_summary, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.mode == "context-burst":
        service.collect_market_context_burst(
            cycles=args.cycles,
            interval_seconds=args.interval_seconds,
            funding_every=args.funding_every,
            funding_history_days=args.funding_history_days,
        )
        service.close()
        return

    if not args.skip_bootstrap:
        service.bootstrap(include_backfill=not args.skip_backfill)

    scheduler = service.build_scheduler()

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 exchange_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("exchange_data 调度器已启动，按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


if __name__ == "__main__":
    main()
