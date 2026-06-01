"""信号衰减与拥挤度 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.alpha_decay.service import AlphaDecayService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 信号衰减与拥挤度分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新信号衰减与拥挤度上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--decay-only",
        action="store_true",
        help="只计算信号衰减",
    )
    parser.add_argument(
        "--crowding-only",
        action="store_true",
        help="只计算拥挤度",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = AlphaDecayService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        if args.decay_only:
            result = service.compute_decay()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if args.crowding_only:
            result = service.compute_crowding()
            print(json.dumps(result, ensure_ascii=False, indent=2))
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
