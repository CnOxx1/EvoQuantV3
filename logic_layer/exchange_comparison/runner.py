import argparse

from config.logging import setup_logger
from logic_layer.exchange_comparison.models import ExchangeComparisonConfig
from logic_layer.exchange_comparison.service import ExchangeComparisonService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 交易所对比模块")
    parser.add_argument("--symbol", help="按交易对过滤，例如 BTC/USDT")
    parser.add_argument(
        "--market-type",
        default="spot",
        help="优先使用的市场类型，例如 spot / swap / future",
    )
    parser.add_argument(
        "--indicator-timeframe",
        default="1h",
        help="技术背景特征使用的周期，默认 1h",
    )
    parser.add_argument(
        "--compare-window-seconds",
        type=int,
        default=5,
        help="不同交易所 ticker 对比窗口，默认 5 秒",
    )
    parser.add_argument(
        "--orderbook-window-seconds",
        type=int,
        default=5,
        help="orderbook 对齐窗口，默认 5 秒",
    )
    parser.add_argument(
        "--snapshot-lookback-seconds",
        type=int,
        default=1800,
        help="读取 orderbook 候选快照的回看窗口，默认 1800 秒",
    )
    parser.add_argument(
        "--target-notional",
        type=float,
        default=10000.0,
        help="滑点估算目标成交额，默认 10000 quote",
    )
    parser.add_argument(
        "--min-actionable-net-spread-bps",
        type=float,
        default=2.0,
        help="净价差达到该阈值时标记为 actionable，默认 2 bps",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("exchange_comparison")

    config = ExchangeComparisonConfig(
        market_type=args.market_type,
        indicator_timeframe=args.indicator_timeframe,
        snapshot_lookback_seconds=args.snapshot_lookback_seconds,
        compare_window_seconds=args.compare_window_seconds,
        orderbook_window_seconds=args.orderbook_window_seconds,
        target_notional=args.target_notional,
        min_actionable_net_spread_bps=args.min_actionable_net_spread_bps,
    )

    service = ExchangeComparisonService(config=config)
    service.init_storage()

    try:
        service.build_latest_snapshots(
            symbol=args.symbol,
            persist=not args.no_save,
            config=config,
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()
