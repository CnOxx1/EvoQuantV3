"""持有者行为分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.holder_behavior_analysis.service import HolderBehaviorService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 持有者行为分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新持有者行为分析上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = HolderBehaviorService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all(no_save=args.no_save)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
