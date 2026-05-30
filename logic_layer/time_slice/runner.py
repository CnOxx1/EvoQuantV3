"""时间切片查询 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="时间切片查询 — 查看任意历史时刻的全市场特征快照"
    )
    parser.add_argument(
        "--timestamp", "-t",
        type=str,
        default=None,
        help="目标时间戳 ISO 格式 (e.g. 2025-05-20T12:00:00)，默认当前时间",
    )
    parser.add_argument(
        "--range-start",
        type=str,
        default=None,
        help="范围查询起始时间",
    )
    parser.add_argument(
        "--range-end",
        type=str,
        default=None,
        help="范围查询结束时间",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3600,
        help="范围查询间隔秒数 (default: 3600)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="按资产过滤，逗号分隔 (e.g. BTC/USDT,ETH/USDT)",
    )
    parser.add_argument(
        "--domains",
        type=str,
        default=None,
        help="按域过滤，逗号分隔 (e.g. klines,technical_indicators)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="只输出覆盖摘要，不输出完整 payload",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="输出完整 JSON bundle（等同于默认行为）",
    )
    parser.add_argument(
        "--feature-history",
        action="store_true",
        help="特征历史序列查询模式",
    )
    parser.add_argument(
        "--features",
        type=str,
        default=None,
        help="指定特征列名，逗号分隔 (e.g. rsi_14,macd_line)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="technical_indicators",
        choices=["klines", "technical_indicators", "feature_standardization"],
        help="特征数据源 (default: technical_indicators)",
    )
    return parser


def _serialize_slice(slice_obj, summary_only: bool = False) -> dict:
    """将 TimeSlice 转为可序列化 dict。"""
    result = {
        "requested_at": slice_obj.requested_at,
        "generated_at": slice_obj.generated_at,
        "symbols": slice_obj.symbols,
        "coverage_summary": slice_obj.coverage_summary,
    }
    if not summary_only:
        domains = {}
        for name, ds in slice_obj.domains.items():
            domains[name] = {
                "status": ds.status,
                "data_timestamp": ds.data_timestamp,
                "staleness_seconds": ds.staleness_seconds,
                "payload": ds.payload,
            }
        result["domains"] = domains
    else:
        domains_brief = {}
        for name, ds in slice_obj.domains.items():
            domains_brief[name] = {
                "status": ds.status,
                "data_timestamp": ds.data_timestamp,
                "staleness_seconds": ds.staleness_seconds,
            }
        result["domains"] = domains_brief
    return result


def main():
    args = build_parser().parse_args()

    from logic_layer.time_slice.service import TimeSliceService

    service = TimeSliceService()
    service.init_storage()

    try:
        symbols = args.symbols.split(",") if args.symbols else None
        domains = args.domains.split(",") if args.domains else None
        features = args.features.split(",") if args.features else None

        # 特征历史模式
        if args.feature_history:
            if not args.range_start or not args.range_end:
                print("错误: --feature-history 需要 --range-start 和 --range-end")
                sys.exit(1)
            if not symbols or len(symbols) != 1:
                print("错误: --feature-history 需要指定单个 --symbols")
                sys.exit(1)
            result = service.get_feature_history(
                symbol=symbols[0],
                start=args.range_start,
                end=args.range_end,
                features=features,
                source=args.source,
            )
            output = {
                "symbol": result.symbol,
                "features": result.features,
                "start": result.start,
                "end": result.end,
                "point_count": result.point_count,
                "series": result.series,
            }
        elif args.range_start and args.range_end:
            result = service.get_slices_range(
                start=args.range_start,
                end=args.range_end,
                interval_seconds=args.interval,
                symbols=symbols,
                domains=domains,
            )
            output = {
                "start": result.start,
                "end": result.end,
                "interval_seconds": result.interval_seconds,
                "slice_count": result.slice_count,
                "slices": [
                    _serialize_slice(s, args.summary_only) for s in result.slices
                ],
            }
        else:
            ts = args.timestamp or datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            result = service.get_slice_at(
                timestamp=ts, symbols=symbols, domains=domains
            )
            output = _serialize_slice(result, args.summary_only)

        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
