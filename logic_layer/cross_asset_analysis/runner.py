"""跨资产分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 跨资产分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新跨资产分析上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--correlation-only",
        action="store_true",
        help="只计算相关性矩阵",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = CrossAssetAnalysisService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        if args.correlation_only:
            result = service.compute_correlation()
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
