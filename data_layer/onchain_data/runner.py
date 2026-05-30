import argparse
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from config.settings import ONCHAIN_CONFIG
from data_layer.onchain_data.service import OnchainDataService


def _parse_csv_arg(raw_value: str) -> list[str] | None:
    values = [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]
    return values or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="链上数据模块运行入口")
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
        help="按来源过滤，逗号分隔，例如 exchange_flow,whale_activity,stablecoin_flow,bridge_netflow,exchange_reserve,protocol_tvl,network_usage,staking_flow",
    )
    parser.add_argument(
        "--factors",
        type=str,
        default="",
        help="按 factor_id 过滤，逗号分隔",
    )
    parser.add_argument(
        "--entities",
        type=str,
        default="",
        help="按实体过滤，逗号分隔，例如 BTC,ETH,USDT",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=ONCHAIN_CONFIG["default_interval"],
        help="标准化频率，例如 15m / 1h / 1d",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=ONCHAIN_CONFIG["default_lookback_hours"],
        help="每次请求回看小时数",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="scheduler 模式下跳过启动时的首轮采集",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="列出当前链上 source 注册表",
    )
    parser.add_argument(
        "--list-factors",
        action="store_true",
        help="列出当前链上 factor 注册表",
    )
    parser.add_argument(
        "--list-entities",
        action="store_true",
        help="列出当前链上 entity 注册表",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出 latest_onchain_timeseries 的 AI 可读上下文 bundle",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出当前链上 source 覆盖情况、最近采集状态和实体覆盖",
    )
    return parser


def _format_sources(rows: list[dict]) -> str:
    lines = ["已注册 source："]
    for row in rows:
        enabled_text = "enabled" if row["enabled"] else "disabled"
        lines.append(
            f"- {row['source_name']} {enabled_text} collector={row['collector_key']} "
            f"factor={row['factor_id']} entity_type={row['entity_type']}: "
            f"{row['description']}"
        )
    return "\n".join(lines)


def _format_factors(rows: list[dict]) -> str:
    lines = ["已注册 factor："]
    for row in rows:
        enabled_text = "enabled" if row["enabled"] else "disabled"
        lines.append(
            f"- {row['factor_id']} [{row['source_name']}] {enabled_text} "
            f"entity_type={row['entity_type']} interval={row['default_interval']}: "
            f"{row['name']}"
        )
    return "\n".join(lines)


def _format_entities(rows: list[dict]) -> str:
    lines = ["已注册 entity："]
    for row in rows:
        lines.append(
            f"- {row['entity_key']} [{row['source_name']}/{row['entity_type']}] "
            f"{row['name']}: {row['description']}"
        )
    return "\n".join(lines)


def main():
    args = build_parser().parse_args()
    source_names = _parse_csv_arg(args.sources)
    factor_ids = _parse_csv_arg(args.factors)
    entity_keys = _parse_csv_arg(args.entities)

    service = OnchainDataService()

    if args.list_sources or args.list_factors or args.list_entities:
        registry = service.describe_registry(
            source_names=source_names,
            factor_ids=factor_ids,
            entity_keys=entity_keys,
        )
        outputs: list[str] = []
        if args.list_sources:
            outputs.append(_format_sources(registry["sources"]))
        if args.list_factors:
            outputs.append(_format_factors(registry["factors"]))
        if args.list_entities:
            outputs.append(_format_entities(registry["entities"]))
        print("\n\n".join(outputs))
        service.close()
        return

    service.init_storage()

    if args.print_context:
        bundle = service.load_latest_context_bundle(
            entity_keys=entity_keys,
            factor_ids=factor_ids,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.print_coverage:
        bundle = service.load_source_coverage(
            source_names=source_names,
            factor_ids=factor_ids,
            entity_keys=entity_keys,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        service.close()
        return

    setup_logger("onchain_data")

    if args.mode == "once":
        service.collect_once(
            source_names=source_names,
            factor_ids=factor_ids,
            entity_keys=entity_keys,
            interval=args.interval,
            lookback_hours=args.lookback_hours,
        )
        service.close()
        return

    if not args.skip_initial_run:
        service.collect_once(
            source_names=source_names,
            factor_ids=factor_ids,
            entity_keys=entity_keys,
            interval=args.interval,
            lookback_hours=args.lookback_hours,
        )

    scheduler = service.build_scheduler(
        entity_keys=entity_keys,
        interval=args.interval,
        lookback_hours=args.lookback_hours,
    )

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 onchain_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("onchain_data 调度器已启动，按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


if __name__ == "__main__":
    main()
