import argparse
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from data_layer.alternative_data.service import AlternativeDataService


def _parse_csv_arg(raw_value: str) -> list[str] | None:
    values = [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]
    return values or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="补充特征模块运行入口")
    parser.add_argument(
        "--mode",
        choices=["bootstrap", "once", "scheduler"],
        default="once",
        help="bootstrap: 初始化因子目录并做首轮回填；once: 执行一次采集；scheduler: 启动定时采集",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="",
        help="按来源过滤，逗号分隔，例如 google_trends,github,stablecoin",
    )
    parser.add_argument(
        "--entities",
        type=str,
        default="",
        help="按实体过滤，逗号分隔，例如 BTC,USDT,bitcoin,stablecoin",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="scheduler 模式下跳过启动时的首轮回填",
    )
    parser.add_argument(
        "--list-sources",
        action="store_true",
        help="列出当前 source 注册表",
    )
    parser.add_argument(
        "--list-factors",
        action="store_true",
        help="列出当前 factor 注册表",
    )
    parser.add_argument(
        "--list-entities",
        action="store_true",
        help="列出当前 entity 注册表",
    )
    parser.add_argument(
        "--reload-registry",
        action="store_true",
        help="强制刷新 registry 缓存；若未搭配 list 参数，则默认输出 source 注册表",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出当前 latest_alternative_timeseries 的 AI 上下文 bundle",
    )
    parser.add_argument(
        "--print-coverage",
        action="store_true",
        help="输出当前补充特征 source 覆盖率、registry 状态和最近采集健康度",
    )
    return parser


def _format_sources(rows: list[dict]) -> str:
    lines = ["已注册 source："]
    for row in rows:
        enabled_text = "enabled" if row["enabled"] else "disabled"
        lines.append(
            f"- {row['source_name']} [{row['phase']}] {enabled_text} "
            f"entity_type={row['entity_type']} "
            f"registry={row['registry_file']} "
            f"version={row['registry_version']} "
            f"records={row['registry_record_count']}: "
            f"{row['description']}"
        )
    return "\n".join(lines)


def _format_factors(rows: list[dict]) -> str:
    lines = ["已注册 factor："]
    for row in rows:
        enabled_text = "enabled" if row["enabled"] else "disabled"
        lines.append(
            f"- {row['factor_id']} [{row['source_name']}] {enabled_text} "
            f"entity_type={row['entity_type']} interval={row['default_interval']} "
            f"phase={row['phase']}: {row['name']}"
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
    entity_keys = _parse_csv_arg(args.entities)

    service = AlternativeDataService()

    if args.list_sources or args.list_factors or args.list_entities or args.reload_registry:
        registry = service.describe_registry(
            source_names=source_names,
            entity_keys=entity_keys,
            force_reload=args.reload_registry,
        )
        outputs: list[str] = []
        if args.list_sources or (
            args.reload_registry
            and not args.list_factors
            and not args.list_entities
        ):
            outputs.append(_format_sources(registry["sources"]))
        if args.list_factors:
            outputs.append(_format_factors(registry["factors"]))
        if args.list_entities:
            outputs.append(_format_entities(registry["entities"]))
        print("\n\n".join(outputs))
        service.close()
        return

    setup_logger("alternative_data")
    service.init_storage()

    if args.print_context:
        bundle = service.load_latest_context_bundle(
            entity_keys=entity_keys,
            source_names=source_names,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.print_coverage:
        coverage = service.load_source_coverage(
            source_names=source_names,
            entity_keys=entity_keys,
        )
        print(json.dumps(coverage, ensure_ascii=False, indent=2))
        service.close()
        return

    if args.mode == "bootstrap":
        service.bootstrap(source_names=source_names, entity_keys=entity_keys)
        service.close()
        return

    if args.mode == "once":
        service.collect_once(source_names=source_names, entity_keys=entity_keys)
        service.close()
        return

    if not args.skip_bootstrap:
        service.bootstrap(source_names=source_names, entity_keys=entity_keys)

    scheduler = service.build_scheduler(
        source_names=source_names,
        entity_keys=entity_keys,
    )

    def shutdown(signum, frame):
        logger.info("收到关闭信号，正在停止 alternative_data 模块...")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("调度器已经停止，无需重复关闭")
        service.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("alternative_data 调度器已启动，按 Ctrl+C 停止")
    try:
        scheduler.start()
    finally:
        service.close()


if __name__ == "__main__":
    main()
