"""anomaly_detection 模块运行入口。"""

import argparse
import json

from loguru import logger

from config.logging import setup_logger
from logic_layer.anomaly_detection.service import AnomalyDetectionService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="异常检测模块运行入口")
    parser.add_argument(
        "--mode", choices=["detect", "review"], default="detect",
        help="detect: 执行异常检测；review: 查看近期异常",
    )
    parser.add_argument("--symbols", type=str, default="", help="按标的过滤，逗号分隔")
    parser.add_argument("--hours", type=int, default=24, help="回顾窗口（小时）")
    parser.add_argument("--no-save", action="store_true", help="不保存结果")
    parser.add_argument("--print-context", action="store_true", help="输出 AI 上下文 bundle")
    return parser


def main():
    args = build_parser().parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()] or None

    setup_logger("anomaly_detection")
    service = AnomalyDetectionService()
    service.init_storage()

    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle(symbols=symbols, hours=args.hours)
            print(json.dumps(bundle, ensure_ascii=False, indent=2, default=str))
            return

        result = service.run_detection(symbols=symbols, save=not args.no_save)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
