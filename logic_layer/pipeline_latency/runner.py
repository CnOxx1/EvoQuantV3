"""数据管道延迟追踪 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="数据管道延迟追踪 — 暴露各域端到端数据新鲜度指标"
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出完整延迟报告 JSON",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="只输出汇总信息",
    )
    return parser


def main():
    args = build_parser().parse_args()

    from logic_layer.pipeline_latency.service import PipelineLatencyService

    service = PipelineLatencyService()
    service.init_storage()

    try:
        report = service.measure_all()
        if args.summary_only:
            output = {"measured_at": report.measured_at, "summary": report.summary}
        else:
            domains_dict = {}
            for name, dl in report.domains.items():
                domains_dict[name] = {
                    "status": dl.status,
                    "latest_data_time": dl.latest_data_time,
                    "latency_seconds": dl.latency_seconds,
                }
            output = {
                "measured_at": report.measured_at,
                "domains": domains_dict,
                "summary": report.summary,
            }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
