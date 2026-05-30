import argparse
import json

from config.logging import setup_logger
from logic_layer.market_breadth.service import MarketBreadthService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="跨资产市场广度上下文构建入口")
    parser.add_argument(
        "--assets",
        type=str,
        default="",
        help="按资产过滤，逗号分隔，例如 BTC,ETH,SOL",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出当前基于真实数据计算的市场广度 bundle",
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        help="计算并保存市场广度快照",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("market_breadth")
    service = MarketBreadthService()
    service.init_storage()
    try:
        asset_keys = [
            item.strip()
            for item in args.assets.split(",")
            if item.strip()
        ] or None
        bundle = service.build_latest_context_bundle(asset_keys=asset_keys)
        if args.print_context or not args.save_snapshot:
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            if not args.save_snapshot:
                return
        snapshot = service.save_snapshot(bundle)
        print(
            json.dumps(
                {
                    "snapshot": snapshot,
                    "summary": {
                        "breadth_status": bundle.get("breadth_status"),
                        "breadth_score": bundle.get("breadth_score"),
                        "ai_ready_asset_count": bundle.get("ai_ready_asset_count"),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        service.close()


if __name__ == "__main__":
    main()
