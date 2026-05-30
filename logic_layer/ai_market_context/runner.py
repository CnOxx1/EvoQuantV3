import argparse
import json
from datetime import datetime, timezone

from config.logging import setup_logger
from logic_layer.ai_market_context.service import AIMarketContextService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - AI 市场上下文聚合")
    parser.add_argument(
        "--entities",
        type=str,
        default="BTC,ETH,SOL,SUI",
        help="按实体过滤，逗号分隔",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只构建不落库",
    )
    parser.add_argument(
        "--print-bundle",
        action="store_true",
        help="输出 AI 最终 bundle JSON",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    entity_keys = [item.strip().upper() for item in args.entities.split(",") if item.strip()]
    service = AIMarketContextService()
    service.init_storage()
    try:
        snapshots = service.build_latest_snapshots(
            entity_keys=entity_keys,
            persist=not args.no_save,
        )
        if args.print_bundle:
            bundle = {
                "as_of": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "entity_count": len(snapshots),
                "entities": [snapshot.bundle for snapshot in snapshots],
            }
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
