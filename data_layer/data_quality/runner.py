import argparse
import json
import signal
import sys

from loguru import logger

from config.logging import setup_logger
from config.settings import DATA_QUALITY_CONFIG
from data_layer.data_quality.audit import DataLayerAuditService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="数据层真实证据带审计模块运行入口")
    parser.add_argument(
        "--mode",
        choices=["once", "scheduler"],
        default="once",
        help="once: 执行一次真实审计并落库；scheduler: 启动定时审计",
    )
    parser.add_argument(
        "--audit-scope",
        type=str,
        default=DATA_QUALITY_CONFIG["default_audit_scope"],
        help="审计范围标识，默认 market_world_model",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="scheduler 模式下跳过启动时的首轮审计",
    )
    parser.add_argument(
        "--print-market-audit",
        action="store_true",
        help="输出跨模块市场世界模型健康摘要，不写入审计快照",
    )
    parser.add_argument(
        "--save-market-audit",
        action="store_true",
        help="计算并保存跨模块市场世界模型健康快照",
    )
    return parser


def _print_json(payload: object):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _log_audit_result(result: dict[str, object]):
    summary = dict(result.get("summary") or {})
    logger.info(
        "数据质量审计完成 scope={} world_model_status={} critical_gap_count={}",
        result.get("snapshot", {}).get("audit_scope")
        or DATA_QUALITY_CONFIG["default_audit_scope"],
        summary.get("world_model_status"),
        int(summary.get("critical_gap_count") or 0),
    )


def main():
    args = build_parser().parse_args()
    audit_scope = str(args.audit_scope).strip() or DATA_QUALITY_CONFIG["default_audit_scope"]
    service = DataLayerAuditService()

    try:
        if args.print_market_audit:
            service.init_storage()
            _print_json(service.load_market_world_audit())
            return

        if args.save_market_audit:
            _print_json(service.run_market_world_audit(audit_scope=audit_scope))
            return

        setup_logger("data_quality_audit")

        if args.mode == "once":
            result = service.run_market_world_audit(audit_scope=audit_scope)
            _log_audit_result(result)
            _print_json(result)
            return

        if not args.skip_initial_run:
            result = service.run_market_world_audit(audit_scope=audit_scope)
            _log_audit_result(result)

        scheduler = service.build_scheduler(
            interval_seconds=DATA_QUALITY_CONFIG["audit_interval_seconds"],
            audit_scope=audit_scope,
        )

        def shutdown(signum, frame):
            logger.info("收到关闭信号，正在停止 data_quality_audit 模块...")
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                logger.debug("调度器已经停止，无需重复关闭")
            service.close()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        logger.info(
            "data_quality_audit 调度器已启动 interval_seconds={}，按 Ctrl+C 停止",
            DATA_QUALITY_CONFIG["audit_interval_seconds"],
        )
        try:
            scheduler.start()
        finally:
            service.close()
    finally:
        service.close()


if __name__ == "__main__":
    main()
