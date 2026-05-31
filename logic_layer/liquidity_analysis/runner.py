"""liquidity_analysis 模块运行入口。"""

import argparse
import json

from loguru import logger

from config.logging import setup_logger
from logic_layer.liquidity_analysis.service import LiquidityAnalysisService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="流动性分析模块运行入口")
    parser.add_argument(
        "--mode", choices=["analyze", "alerts"], default="analyze",
        help="analyze: 执行流动性分析；alerts: 查看预警",
    )
    parser.add_argument("--symbols", type=str, default="", help="按标的过滤，逗号分隔")
    parser.add_argument("--no-save", action="store_true", help="不保存结果")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    return parser


def main():
    args = build_parser().parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None

    setup_logger("liquidity_analysis")
    service = LiquidityAnalysisService()
    service.init_storage()

    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle(symbols=symbols)
            print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
            return

        result = service.run_analysis(symbols=symbols, save=not args.no_save)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
