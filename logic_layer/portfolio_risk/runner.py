"""组合风险分析 CLI 入口。"""

import argparse
import json

from config.logging import setup_logger
from logic_layer.portfolio_risk.service import PortfolioRiskService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="逻辑处理层 - 组合风险分析")
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出最新组合风险上下文 JSON",
    )
    parser.add_argument(
        "--portfolio-name",
        type=str,
        default="default",
        help="组合名称",
    )
    return parser


def main():
    args = build_parser().parse_args()
    setup_logger()

    service = PortfolioRiskService()
    service.init_storage()
    try:
        if args.print_context:
            bundle = service.load_latest_context_bundle()
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
            return

        result = service.compute_risk(portfolio_name=args.portfolio_name)
        if result:
            print(json.dumps({
                "status": "computed",
                "asset_count": result["asset_count"],
                "annualized_volatility": result["annualized_volatility"],
                "diversification_ratio": result["diversification_ratio"],
            }, indent=2))
        else:
            print(json.dumps({"status": "no_data"}, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
