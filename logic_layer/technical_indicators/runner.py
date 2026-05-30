import argparse

from config.logging import setup_logger
from logic_layer.technical_indicators.service import TechnicalIndicatorService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 技术指标模块")
    parser.add_argument(
        "--mode",
        choices=["merge", "indicators", "all"],
        default="all",
        help="merge: 仅合并K线；indicators: 仅计算指标；all: 合并并计算指标",
    )
    parser.add_argument("--symbol", help="按交易对过滤，例如 BTC/USDT")
    parser.add_argument("--timeframe", help="按周期过滤，例如 1h")
    parser.add_argument("--since-days", type=int, help="仅处理最近N天数据")
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="强制全量重算，不走增量窗口",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("technical_indicators")

    service = TechnicalIndicatorService()
    service.init_storage()

    try:
        if args.mode == "merge":
            service.merge_klines(
                args.symbol,
                args.timeframe,
                args.since_days,
                full_refresh=args.full_refresh,
            )
            return
        if args.mode == "indicators":
            service.calculate_indicators(
                args.symbol,
                args.timeframe,
                args.since_days,
                full_refresh=args.full_refresh,
            )
            return
        service.refresh_all(
            args.symbol,
            args.timeframe,
            args.since_days,
            full_refresh=args.full_refresh,
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()
