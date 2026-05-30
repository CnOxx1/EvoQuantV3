"""特征标准化 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import logging

from logic_layer.feature_standardization.service import FeatureStandardizationService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 特征标准化")
    parser.add_argument(
        "--print-context", action="store_true",
        help="输出最新标准化上下文 JSON",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--timeframe", default="1h",
        help="目标时间帧 (默认 1h)",
    )
    return parser


def main():
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    service = FeatureStandardizationService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        result = service.run_standardization(
            timeframe=args.timeframe, save=not args.no_save
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
