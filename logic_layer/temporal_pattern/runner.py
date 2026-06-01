"""时间模式分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.temporal_pattern.service import TemporalPatternService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 时间模式分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新时间模式分析上下文 JSON",
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
        help="逗号分隔的 symbol 列表（如 BTC/USDT,ETH/USDT）",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    symbols = None
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",")]

    service = TemporalPatternService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all(symbols=symbols)
        print(json.dumps(
            {k: v is not None for k, v in results.items()},
            indent=2,
        ))
    finally:
        service.close()


if __name__ == "__main__":
    main()
