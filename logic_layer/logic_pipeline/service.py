"""逻辑层全链路定时编排服务。

按依赖顺序执行逻辑层全部模块，生成 AI 可消费的完整市场上下文。

执行顺序：
  Phase 1: technical_indicators（依赖原始 klines）
  Phase 2: feature_standardization, cross_asset_analysis, exchange_comparison,
           macro_context, news_sentiment（互相独立，依赖 Phase 1 或原始数据）
  Phase 3: portfolio_risk, market_breadth, asset_readiness（依赖 Phase 2）
  Phase 4: ai_market_context（最终聚合，依赖 Phase 3）
  Phase 5: pipeline_latency（监控，只读）
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger


# 默认每 5 分钟执行一次全链路
DEFAULT_INTERVAL_SECONDS = int(
    os.environ.get("LOGIC_PIPELINE_INTERVAL_SECONDS", "300")
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_phase(phase_name: str, tasks: list[tuple[str, callable]]) -> dict[str, str]:
    """执行一个阶段内的所有任务，返回 {module_name: status}。"""
    results = {}
    for module_name, task_fn in tasks:
        started = time.monotonic()
        try:
            task_fn()
            elapsed = time.monotonic() - started
            logger.info(
                "逻辑管道 [{}] {} 完成 ({:.1f}s)",
                phase_name, module_name, elapsed,
            )
            results[module_name] = "success"
        except Exception as exc:
            elapsed = time.monotonic() - started
            logger.error(
                "逻辑管道 [{}] {} 失败 ({:.1f}s): {}",
                phase_name, module_name, elapsed, exc,
            )
            results[module_name] = f"error: {type(exc).__name__}"
    return results


def run_full_pipeline() -> dict[str, object]:
    """执行逻辑层全链路，返回各阶段结果摘要。"""
    pipeline_start = _utc_now()
    all_results: dict[str, str] = {}

    # === Phase 1: 技术指标 ===
    def _technical_indicators():
        from logic_layer.technical_indicators.service import TechnicalIndicatorService
        svc = TechnicalIndicatorService()
        try:
            svc.refresh_all(None, None, None, full_refresh=False)
        finally:
            svc.close()

    results = _run_phase("Phase1", [
        ("technical_indicators", _technical_indicators),
    ])
    all_results.update(results)

    # === Phase 2: 独立模块（互不依赖） ===
    def _feature_standardization():
        from logic_layer.feature_standardization.service import (
            FeatureStandardizationService,
        )
        svc = FeatureStandardizationService()
        try:
            svc.run_standardization(timeframe="1h", save=True)
        finally:
            svc.close()

    def _cross_asset_analysis():
        from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService
        svc = CrossAssetAnalysisService()
        try:
            svc.run_all()
        finally:
            svc.close()

    def _exchange_comparison():
        from logic_layer.exchange_comparison.service import ExchangeComparisonService
        from logic_layer.exchange_comparison.models import ExchangeComparisonConfig
        svc = ExchangeComparisonService()
        try:
            svc.build_latest_snapshots(config=ExchangeComparisonConfig())
        finally:
            svc.close()

    def _macro_context():
        from logic_layer.macro_context.service import MacroContextService
        svc = MacroContextService()
        try:
            svc.build_latest_snapshots()
        finally:
            svc.close()

    def _news_sentiment():
        from logic_layer.news_sentiment.service import NewsSentimentService
        svc = NewsSentimentService()
        try:
            svc.run_labeling(limit=200, save=True)
        finally:
            svc.close()

    def _market_structure():
        from logic_layer.market_structure.service import MarketStructureService
        svc = MarketStructureService()
        try:
            svc.save_snapshot()
        finally:
            svc.close()

    results = _run_phase("Phase2", [
        ("feature_standardization", _feature_standardization),
        ("cross_asset_analysis", _cross_asset_analysis),
        ("exchange_comparison", _exchange_comparison),
        ("macro_context", _macro_context),
        ("news_sentiment", _news_sentiment),
        ("market_structure", _market_structure),
    ])
    all_results.update(results)

    # === Phase 3: 依赖 Phase 2 的模块 ===
    def _portfolio_risk():
        from logic_layer.portfolio_risk.service import PortfolioRiskService
        svc = PortfolioRiskService()
        try:
            svc.compute_risk(portfolio_name="default")
        finally:
            svc.close()

    def _market_breadth():
        from logic_layer.market_breadth.service import MarketBreadthService
        svc = MarketBreadthService()
        try:
            bundle = svc.build_latest_context_bundle()
            svc.save_snapshot(bundle)
        finally:
            svc.close()

    def _asset_readiness():
        from logic_layer.asset_readiness.service import AssetReadinessService
        svc = AssetReadinessService()
        try:
            bundle = svc.build_latest_context_bundle()
            svc.save_snapshot(bundle)
        finally:
            svc.close()

    results = _run_phase("Phase3", [
        ("portfolio_risk", _portfolio_risk),
        ("market_breadth", _market_breadth),
        ("asset_readiness", _asset_readiness),
    ])
    all_results.update(results)

    # === Phase 4: 最终 AI 上下文聚合 ===
    def _ai_market_context():
        from logic_layer.ai_market_context.service import AIMarketContextService
        svc = AIMarketContextService()
        try:
            svc.build_latest_snapshots(
                entity_keys=["BTC", "ETH", "SOL", "SUI",
                             "DOGE", "XRP", "AVAX", "LINK",
                             "ADA", "DOT", "POL", "UNI",
                             "ARB", "OP", "NEAR", "ATOM",
                             "APT", "TIA"],
                persist=True,
            )
        finally:
            svc.close()

    results = _run_phase("Phase4", [
        ("ai_market_context", _ai_market_context),
    ])
    all_results.update(results)

    # === Phase 5: 管道延迟监控 ===
    def _pipeline_latency():
        from logic_layer.pipeline_latency.service import PipelineLatencyService
        svc = PipelineLatencyService()
        try:
            svc.measure_all()
        finally:
            svc.close()

    results = _run_phase("Phase5", [
        ("pipeline_latency", _pipeline_latency),
    ])
    all_results.update(results)

    pipeline_end = _utc_now()
    success_count = sum(1 for v in all_results.values() if v == "success")
    total_count = len(all_results)

    logger.info(
        "逻辑管道全链路完成: {}/{} 成功, 耗时 {:.1f}s",
        success_count, total_count,
        (pipeline_end - pipeline_start).total_seconds(),
    )

    return {
        "started_at": pipeline_start.isoformat(),
        "finished_at": pipeline_end.isoformat(),
        "success_count": success_count,
        "total_count": total_count,
        "results": all_results,
    }


def build_scheduler(interval_seconds: int | None = None) -> BlockingScheduler:
    """构建定时调度器。"""
    interval = max(60, interval_seconds or DEFAULT_INTERVAL_SECONDS)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_full_pipeline,
        trigger="interval",
        seconds=interval,
        id="logic_pipeline",
        name="逻辑层全链路定时编排",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=max(120, interval),
        next_run_time=datetime.now(),  # 立即执行第一次
    )
    return scheduler
