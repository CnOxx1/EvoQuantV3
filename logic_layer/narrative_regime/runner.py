"""叙事状态机 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.narrative_regime.service import NarrativeRegimeService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 叙事状态机")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新叙事状态机上下文 JSON",
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

    service = NarrativeRegimeService()
    service.init_storage()
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
