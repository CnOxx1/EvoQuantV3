import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from config.settings import NEWS_CONFIG
from data_layer.news_data.service import NewsDataService


def _parse_csv_arg(raw_value: str) -> list[str] | None:
    values = [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]
    return values or None


def _format_sources(rows: list[dict]) -> str:
    lines = [f"已注册新闻源：{len(rows)}"]
    for row in rows:
        lines.append(
            f"- {row['name']} "
            f"[group={row.get('source_group') or 'ungrouped'} "
            f"category={row.get('category') or 'uncategorized'} "
            f"lang={row.get('language') or 'unknown'}] "
            f"tags={','.join(row.get('tags') or []) or '-'} "
            f"url={row['feed_url']}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="新闻数据模块运行入口")
    parser.add_argument(
        "--mode",
        choices=["once", "scheduler"],
        default="once",
        help="once: 执行一次新闻采集；scheduler: 启动定时采集",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=NEWS_CONFIG["lookback_hours"],
        help="只保留最近多少小时内的新闻（发布时间为空时回退到采集时间）",
    )
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=NEWS_CONFIG["max_items_per_source"],
        help="每个 feed 最多解析多少条",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="",
        help="按名称过滤新闻源，逗号分隔，例如 CoinDesk,Cointelegraph",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="",
        help="按 category 过滤新闻源，逗号分隔，例如 crypto-news,governance",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="按 tag 过滤新闻源，逗号分隔，例如 regulatory,official,forum",
    )
    parser.add_argument(
        "--groups",
        type=str,
        default="",
        help="按 source_group 过滤新闻源，逗号分隔，例如 core_media,ecosystem",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="列出当前新闻源清单，可叠加 sources/categories/tags/groups 过滤",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出当前新闻源覆盖情况、最近采集状态和新鲜度",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最近新闻上下文 bundle，供 AI 直接消费",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="scheduler 模式下跳过启动时的首次采集",
    )
    parser.add_argument(
        "--async-scheduler",
        action="store_true",
        help="scheduler 模式下使用 AsyncIOScheduler（推荐）",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("news_data")

    source_names = _parse_csv_arg(args.sources)
    categories = _parse_csv_arg(args.categories)
    tags = _parse_csv_arg(args.tags)
    source_groups = _parse_csv_arg(args.groups)

    service = NewsDataService()

    if args.list_sources:
        print(
            _format_sources(
                service.describe_sources(
                    source_names=source_names,
                    categories=categories,
                    tags=tags,
                    source_groups=source_groups,
                )
            )
        )
        service.close()
        return

    service.init_storage()

    if args.print_coverage:
        print(
            json.dumps(
                service.load_source_coverage(
                    hours=args.hours,
                    source_names=source_names,
                    categories=categories,
                    tags=tags,
                    source_groups=source_groups,
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
                service.load_latest_context_bundle(
                    hours=args.hours,
                    source_names=source_names,
                    categories=categories,
                    tags=tags,
                    source_groups=source_groups,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        service.close()
        return

    if args.mode == "once":
        service.collect_once(
            hours=args.hours,
            limit_per_source=args.limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        service.close()
        return

    if not args.skip_initial_run:
        service.collect_once(
            hours=args.hours,
            limit_per_source=args.limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )

    if args.async_scheduler:
        _run_async_scheduler(
            service, args.hours, args.limit_per_source,
            source_names, categories, tags, source_groups,
        )
    else:
        _run_blocking_scheduler(
            service, args.hours, args.limit_per_source,
            source_names, categories, tags, source_groups,
        )


def _run_blocking_scheduler(
    service, hours, limit_per_source,
    source_names, categories, tags, source_groups,
):
    """使用 BlockingScheduler 运行（传统模式）。"""
    scheduler = service.build_scheduler(
        hours=hours,
        limit_per_source=limit_per_source,
        source_names=source_names,
        categories=categories,
        tags=tags,
        source_groups=source_groups,
    )

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 news_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("news_data 调度器已启动（BlockingScheduler），按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


def _run_async_scheduler(
    service, hours, limit_per_source,
    source_names, categories, tags, source_groups,
):
    """使用 AsyncIOScheduler 运行 — 利用 asyncio 事件循环。"""
    scheduler = service.build_async_scheduler(
        hours=hours,
        limit_per_source=limit_per_source,
        source_names=source_names,
        categories=categories,
        tags=tags,
        source_groups=source_groups,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 news_data 异步调度器...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    scheduler.start()
    logger.info("news_data 异步调度器已启动（AsyncIOScheduler），按 Ctrl+C 停止")
    try:
        loop.run_forever()
    finally:
        scheduler.shutdown(wait=False)
        service.close()
        loop.close()


if __name__ == "__main__":
    main()
