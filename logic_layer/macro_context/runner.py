import argparse
import json

from config.logging import setup_logger
from logic_layer.macro_context.models import MacroContextConfig
from logic_layer.macro_context.service import MacroContextService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 宏观上下文模块")
    parser.add_argument(
        "--factors",
        type=str,
        default="",
        help="按 factor_id 过滤，逗号分隔，例如 dxy,nasdaq_100",
    )
    parser.add_argument(
        "--interval",
        default=None,
        help="按 interval 过滤，例如 1d 或 1h",
    )
    parser.add_argument(
        "--short-lookback-days",
        type=int,
        default=1,
        help="短回看窗口，默认 1 天",
    )
    parser.add_argument(
        "--medium-lookback-days",
        type=int,
        default=5,
        help="中回看窗口，默认 5 天",
    )
    parser.add_argument(
        "--include-disabled-factors",
        action="store_true",
        help="是否包含目录中 disabled 的 P1 因子",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--print-bundle",
        action="store_true",
        help="输出 AI 可直接消费的上下文 JSON bundle",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    factor_ids = [
        item.strip()
        for item in args.factors.split(",")
        if item.strip()
    ] or None

    config = MacroContextConfig(
        short_lookback_days=args.short_lookback_days,
        medium_lookback_days=args.medium_lookback_days,
        include_disabled_factors=args.include_disabled_factors,
        interval_filter=args.interval,
    )

    service = MacroContextService(config=config)
    service.init_storage()

    try:
        snapshots = service.build_latest_snapshots(
            factor_ids=factor_ids,
            persist=not args.no_save,
            config=config,
        )
        if args.print_bundle:
            bundle = (
                service.build_context_bundle_from_snapshots(
                    snapshots,
                    factor_ids=factor_ids,
                    interval=args.interval,
                )
                if args.no_save
                else service.load_latest_context_bundle(
                    factor_ids=factor_ids,
                    interval=args.interval,
                )
            )
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
