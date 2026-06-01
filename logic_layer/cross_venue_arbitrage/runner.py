"""跨场所套利分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 跨场所套利分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新跨场所套利分析上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="逗号分隔的 symbol 过滤列表（如 BTC,ETH,SOL）",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = CrossVenueArbService()
    service.init_storage()

    # 应用 symbol 过滤
    if args.symbols:
        service.SYMBOLS = [
            s.strip().upper() for s in args.symbols.split(",")
        ]

    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all()
        print(json.dumps(
            {k: v is not None for k, v in results.items()},
            indent=2,
        ))
    finally:
        service.close()


if __name__ == "__main__":
    main()
