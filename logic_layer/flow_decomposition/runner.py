"""流量分解 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.flow_decomposition.service import FlowDecompositionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 流量分解")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新流量分解上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="指定要分析的 symbol 列表",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = FlowDecompositionService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all(symbols=args.symbols)
        print(json.dumps(
            {k: v is not None for k, v in results.items()},
            indent=2,
        ))
    finally:
        service.close()


if __name__ == "__main__":
    main()
