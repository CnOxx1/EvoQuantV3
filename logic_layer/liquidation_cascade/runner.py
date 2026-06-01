"""清算级联预测 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.liquidation_cascade.service import LiquidationCascadeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 清算级联预测")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新清算级联分析上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="按标的过滤，逗号分隔",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = LiquidationCascadeService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        symbols = None
        if args.symbols:
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

        results = service.run_all(symbols=symbols)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
