import argparse
import json

from config.logging import setup_logger
from logic_layer.market_structure.service import MarketStructureService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="市场结构上下文构建入口")
    parser.add_argument(
        "--assets",
        type=str,
        default="",
        help="按资产过滤，逗号分隔，例如 BTC,ETH,SOL",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出当前基于真实交易所数据构建的市场结构 bundle",
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        help="计算并保存市场结构快照",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("market_structure")
    service = MarketStructureService()
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
                        "asset_count": bundle.get("asset_count"),
                        "data_quality_flag": bundle.get("data_quality_flag"),
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
