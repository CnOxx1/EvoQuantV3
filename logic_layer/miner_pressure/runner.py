"""矿工压力分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.miner_pressure.service import MinerPressureService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 矿工压力分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新矿工压力分析上下文 JSON",
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

    service = MinerPressureService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all()
        if args.no_save:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(
                {k: v is not None for k, v in results.items()},
                indent=2,
            ))
    finally:
        service.close()


if __name__ == "__main__":
    main()
