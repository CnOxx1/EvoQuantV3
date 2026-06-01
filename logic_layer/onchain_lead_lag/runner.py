"""链上领先-滞后分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.onchain_lead_lag.service import OnchainLeadLagService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 链上领先-滞后分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新链上领先-滞后分析上下文 JSON",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="只计算不落库",
    )
    parser.add_argument(
        "--signals",
        type=str,
        default=None,
        help="逗号分隔的信号名过滤（如 whale_net_flow,gas_spike）",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = OnchainLeadLagService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        results = service.run_all()
        print(json.dumps(
            {
                "signals_count": len(results.get("signals", [])),
                "relations_count": len(results.get("relations", [])),
                "alerts_count": len(results.get("alerts", [])),
            },
            indent=2,
        ))
    finally:
        service.close()


if __name__ == "__main__":
    main()
