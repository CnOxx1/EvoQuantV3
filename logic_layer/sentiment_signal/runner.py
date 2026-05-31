"""sentiment_signal 模块运行入口。"""

import argparse
import json

from loguru import logger

from config.logging import setup_logger
from logic_layer.sentiment_signal.service import SentimentSignalService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="情绪信号模块运行入口")
    parser.add_argument(
        "--mode", choices=["analyze", "causality"], default="analyze",
        help="analyze: 执行信号分析；causality: 因果检验",
    )
    parser.add_argument("--symbols", type=str, default="", help="按标的过滤，逗号分隔")
    parser.add_argument("--no-save", action="store_true", help="不保存结果")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    return parser


def main():
    args = build_parser().parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None

    setup_logger("sentiment_signal")
    service = SentimentSignalService()
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
