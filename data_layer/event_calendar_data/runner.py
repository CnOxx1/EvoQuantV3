import argparse
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from config.settings import EVENT_CALENDAR_CONFIG
from data_layer.event_calendar_data.service import EventCalendarDataService


def _parse_csv_arg(raw_value: str) -> list[str] | None:
    values = [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]
    return values or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="事件日历模块运行入口")
    parser.add_argument(
        "--mode",
        choices=["once", "scheduler"],
        default="once",
        help="once: 执行一次采集；scheduler: 启动定时采集",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="",
        help="按来源过滤，逗号分隔",
    )
    parser.add_argument(
        "--event-types",
        type=str,
        default="",
        help="按事件类型过滤，逗号分隔，例如 macro,etf,unlock,upgrade",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="按关联 symbol 过滤，逗号分隔，例如 BTC,ETH,MARKET",
    )
    parser.add_argument(
        "--lookahead-days",
        type=int,
        default=EVENT_CALENDAR_CONFIG["lookahead_days"],
        help="采集窗口，默认向前看 90 天",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="scheduler 模式下跳过启动时的首轮采集",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="列出当前事件源配置",
    )
    parser.add_argument(
        "--print-upcoming",
        action="store_true",
        help="输出数据库中当前即将发生的事件",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出当前事件源覆盖情况、最近采集状态和未来事件覆盖",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出未来事件上下文 bundle，供 AI 直接消费",
    )
    parser.add_argument(
        "--statuses",
        type=str,
        default="scheduled,updated",
        help="print-upcoming 模式下的状态过滤",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="print-upcoming 模式下输出条数",
    )
    return parser


def _format_sources(rows: list[dict]) -> str:
    lines = ["已注册事件源："]
    for row in rows:
        enabled_text = "enabled" if row["enabled"] else "disabled"
        lines.append(
            f"- {row['name']} [{row['event_type']}] {enabled_text} "
            f"adapter={row['adapter']} default_symbol={row['default_symbol']}: "
            f"{row['description'] or ''}"
        )
    return "\n".join(lines)


def main():
    args = build_parser().parse_args()
    source_names = _parse_csv_arg(args.sources)
    event_types = _parse_csv_arg(args.event_types)
    symbols = _parse_csv_arg(args.symbols)
    statuses = _parse_csv_arg(args.statuses)

    service = EventCalendarDataService()

    if args.list_sources:
        rows = service.describe_sources(
            source_names=source_names,
            event_types=event_types,
        )
        print(_format_sources(rows))
        service.close()
        return

    service.init_storage()

    if args.print_upcoming:
        rows = service.load_upcoming_events(
            horizon_days=args.lookahead_days,
            event_types=event_types,
            symbols=symbols,
            statuses=statuses,
            limit=args.limit,
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.print_coverage:
        print(
            json.dumps(
                service.load_source_coverage(
                    horizon_days=args.lookahead_days,
                    source_names=source_names,
                    event_types=event_types,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        service.close()
        return

    if args.print_context:
        print(
            json.dumps(
                service.load_upcoming_context_bundle(
                    horizon_days=args.lookahead_days,
                    event_types=event_types,
                    symbols=symbols,
                    statuses=statuses,
                    limit=args.limit,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        service.close()
        return

    setup_logger("event_calendar_data")

    if args.mode == "once":
        service.collect_once(
            lookahead_days=args.lookahead_days,
            source_names=source_names,
            event_types=event_types,
            symbols=symbols,
        )
        service.close()
        return

    if not args.skip_initial_run:
        service.collect_once(
            lookahead_days=args.lookahead_days,
            source_names=source_names,
            event_types=event_types,
            symbols=symbols,
        )

    scheduler = service.build_scheduler(
        lookahead_days=args.lookahead_days,
        source_names=source_names,
        event_types=event_types,
        symbols=symbols,
    )

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 event_calendar_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("event_calendar_data 调度器已启动，按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


if __name__ == "__main__":
    main()
