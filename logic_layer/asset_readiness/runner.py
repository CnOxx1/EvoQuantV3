import argparse
import json

from config.logging import setup_logger
from logic_layer.asset_readiness.service import AssetReadinessService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="资产级真实证据可用性矩阵构建入口")
    parser.add_argument(
        "--assets",
        type=str,
        default="",
        help="按资产过滤，逗号分隔，例如 BTC,ETH,SOL",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出当前基于真实数据计算的资产级 readiness bundle",
    )
    parser.add_argument(
        "--save-snapshot",
        action="store_true",
        help="计算并保存资产级 readiness 快照",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger("asset_readiness")
    service = AssetReadinessService()
    service.init_storage()
    try:
        asset_keys = [item.strip() for item in args.assets.split(",") if item.strip()] or None
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
                        "market_world_status": bundle.get("market_world_status"),
                        "asset_count": bundle.get("asset_count"),
                        "ready_asset_count": bundle.get("ready_asset_count"),
                        "partial_asset_count": bundle.get("partial_asset_count"),
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
