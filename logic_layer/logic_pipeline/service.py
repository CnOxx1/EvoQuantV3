"""逻辑层全链路定时编排服务。

按依赖顺序执行逻辑层全部模块，生成 AI 可消费的完整市场上下文。

支持两种执行模式：
  1. 经典模式（默认）：固定 5 阶段串行/并行混合
  2. DAG 模式：基于依赖图自动分层并行（设置 LOGIC_PIPELINE_USE_DAG=1 启用）

执行顺序（经典模式）：
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger


# 默认每 5 分钟执行一次全链路
DEFAULT_INTERVAL_SECONDS = int(
    os.environ.get("LOGIC_PIPELINE_INTERVAL_SECONDS", "300")
)

# Phase 2 并行线程数
PHASE2_MAX_WORKERS = int(os.environ.get("LOGIC_PIPELINE_PHASE2_WORKERS", "4"))

# Phase 2 单模块超时（秒），超时后标记为 timeout 但不影响其他模块
PHASE2_TASK_TIMEOUT = int(os.environ.get("LOGIC_PIPELINE_PHASE2_TIMEOUT", "300"))

# 是否启用 DAG 模式
USE_DAG = os.environ.get("LOGIC_PIPELINE_USE_DAG", "0") == "1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_phase(phase_name: str, tasks: list[tuple[str, callable]]) -> dict[str, str]:
    """执行一个阶段内的所有任务（串行），返回 {module_name: status}。"""
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


def _run_phase_parallel(
    phase_name: str,
    tasks: list[tuple[str, callable]],
    max_workers: int = PHASE2_MAX_WORKERS,
    timeout: int = PHASE2_TASK_TIMEOUT,
) -> dict[str, str]:
    """并行执行一个阶段内的所有任务，返回 {module_name: status}。

    单个模块失败或超时不影响其他模块。
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {}
        for module_name, task_fn in tasks:
            future = executor.submit(_execute_task, phase_name, module_name, task_fn)
            future_to_name[future] = module_name
        try:
            for future in as_completed(future_to_name, timeout=timeout):
                module_name = future_to_name[future]
                results[module_name] = future.result()
        except TimeoutError:
            pass
    # 标记未完成的 future（整体超时场景）
    for future, module_name in future_to_name.items():
        if module_name not in results:
            results[module_name] = "error: TimeoutError"
            logger.error(
                "逻辑管道 [{}] {} 超时 (>{}s)",
                phase_name, module_name, timeout,
            )
    return results


def _execute_task(phase_name: str, module_name: str, task_fn: callable) -> str:
    """执行单个任务并返回状态字符串。"""
    started = time.monotonic()
    try:
        task_fn()
        elapsed = time.monotonic() - started
        logger.info(
            "逻辑管道 [{}] {} 完成 ({:.1f}s)",
            phase_name, module_name, elapsed,
        )
        return "success"
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.error(
            "逻辑管道 [{}] {} 失败 ({:.1f}s): {}",
            phase_name, module_name, elapsed, exc,
        )
        return f"error: {type(exc).__name__}"


def run_full_pipeline() -> dict[str, object]:
    """执行逻辑层全链路，返回各阶段结果摘要。"""
    pipeline_start = _utc_now()

    if USE_DAG:
        all_results = _run_dag_pipeline()
    else:
        all_results = _run_classic_pipeline()

    pipeline_end = _utc_now()
    success_count = sum(1 for v in all_results.values() if v == "success")
    total_count = len(all_results)

    logger.info(
        "逻辑管道全链路完成: {}/{} 成功, 耗时 {:.1f}s{}",
        success_count, total_count,
        (pipeline_end - pipeline_start).total_seconds(),
        " [DAG模式]" if USE_DAG else "",
    )

    # 管道完成后按模块粒度清空 API 缓存
    _invalidate_api_cache_by_modules(
        [k for k, v in all_results.items() if v == "success"]
    )

    return {
        "started_at": pipeline_start.isoformat(),
        "finished_at": pipeline_end.isoformat(),
        "success_count": success_count,
        "total_count": total_count,
        "mode": "dag" if USE_DAG else "classic",
        "results": all_results,
    }


def _run_dag_pipeline() -> dict[str, str]:
    """DAG 模式：基于依赖图自动分层并行执行。"""
    from logic_layer.logic_pipeline.dag_scheduler import ModuleNode, run_dag

    nodes = [
        ModuleNode("technical_indicators", _make_technical_indicators()),
        ModuleNode("feature_standardization", _make_feature_standardization(),
                   depends_on=["technical_indicators"]),
        ModuleNode("cross_asset_analysis", _make_cross_asset_analysis(),
                   depends_on=["technical_indicators"]),
        ModuleNode("exchange_comparison", _make_exchange_comparison()),
        ModuleNode("macro_context", _make_macro_context()),
        ModuleNode("news_sentiment", _make_news_sentiment()),
        ModuleNode("market_structure", _make_market_structure()),
        ModuleNode("liquidation_cascade", _make_liquidation_cascade(),
                   depends_on=["technical_indicators"]),
        ModuleNode("cross_venue_arbitrage", _make_cross_venue_arbitrage()),
        ModuleNode("onchain_lead_lag", _make_onchain_lead_lag(),
                   depends_on=["technical_indicators"]),
        ModuleNode("portfolio_risk", _make_portfolio_risk(),
                   depends_on=["cross_asset_analysis"]),
        ModuleNode("market_breadth", _make_market_breadth()),
        ModuleNode("asset_readiness", _make_asset_readiness(),
                   depends_on=["feature_standardization", "cross_asset_analysis"]),
        ModuleNode("ai_market_context", _make_ai_market_context(),
                   depends_on=["portfolio_risk", "market_breadth", "asset_readiness"]),
        ModuleNode("pipeline_latency", _make_pipeline_latency(),
                   depends_on=["ai_market_context"]),
    ]
    return run_dag(nodes)


def _run_classic_pipeline() -> dict[str, str]:
    """经典模式：固定 5 阶段串行/并行混合。"""
    all_results: dict[str, str] = {}

    # === Phase 1: 技术指标 ===
    results = _run_phase("Phase1", [
        ("technical_indicators", _make_technical_indicators()),
    ])
    all_results.update(results)

    # === Phase 2: 独立模块（互不依赖） ===
    results = _run_phase_parallel("Phase2", [
        ("feature_standardization", _make_feature_standardization()),
        ("cross_asset_analysis", _make_cross_asset_analysis()),
        ("exchange_comparison", _make_exchange_comparison()),
        ("macro_context", _make_macro_context()),
        ("news_sentiment", _make_news_sentiment()),
        ("market_structure", _make_market_structure()),
        ("liquidation_cascade", _make_liquidation_cascade()),
        ("cross_venue_arbitrage", _make_cross_venue_arbitrage()),
        ("onchain_lead_lag", _make_onchain_lead_lag()),
    ])
    all_results.update(results)

    # === Phase 3: 依赖 Phase 2 的模块 ===
    results = _run_phase("Phase3", [
        ("portfolio_risk", _make_portfolio_risk()),
        ("market_breadth", _make_market_breadth()),
        ("asset_readiness", _make_asset_readiness()),
    ])
    all_results.update(results)

    # === Phase 4: 最终 AI 上下文聚合 ===
    results = _run_phase("Phase4", [
        ("ai_market_context", _make_ai_market_context()),
    ])
    all_results.update(results)

    # === Phase 5: 管道延迟监控 ===
    results = _run_phase("Phase5", [
        ("pipeline_latency", _make_pipeline_latency()),
    ])
    all_results.update(results)

    return all_results


# ------------------------------------------------------------------
# 模块工厂函数（延迟导入，避免循环依赖）
# ------------------------------------------------------------------

def _make_technical_indicators() -> callable:
    def _run():
        from logic_layer.technical_indicators.service import TechnicalIndicatorService
        svc = TechnicalIndicatorService()
        try:
            svc.refresh_all(None, None, None, full_refresh=False)
        finally:
            svc.close()
    return _run


def _make_feature_standardization() -> callable:
    def _run():
        from logic_layer.feature_standardization.service import (
            FeatureStandardizationService,
        )
        svc = FeatureStandardizationService()
        try:
            svc.run_standardization(timeframe="1h", save=True)
        finally:
            svc.close()
    return _run


def _make_cross_asset_analysis() -> callable:
    def _run():
        from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService
        svc = CrossAssetAnalysisService()
        try:
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_exchange_comparison() -> callable:
    def _run():
        from logic_layer.exchange_comparison.service import ExchangeComparisonService
        from logic_layer.exchange_comparison.models import ExchangeComparisonConfig
        svc = ExchangeComparisonService()
        try:
            svc.build_latest_snapshots(config=ExchangeComparisonConfig())
        finally:
            svc.close()
    return _run


def _make_macro_context() -> callable:
    def _run():
        from logic_layer.macro_context.service import MacroContextService
        svc = MacroContextService()
        try:
            svc.build_latest_snapshots()
        finally:
            svc.close()
    return _run


def _make_news_sentiment() -> callable:
    def _run():
        from logic_layer.news_sentiment.service import NewsSentimentService
        svc = NewsSentimentService()
        try:
            svc.run_labeling(limit=200, save=True)
        finally:
            svc.close()
    return _run


def _make_market_structure() -> callable:
    def _run():
        from logic_layer.market_structure.service import MarketStructureService
        svc = MarketStructureService()
        try:
            svc.save_snapshot()
        finally:
            svc.close()
    return _run


def _make_portfolio_risk() -> callable:
    def _run():
        from logic_layer.portfolio_risk.service import PortfolioRiskService
        svc = PortfolioRiskService()
        try:
            svc.compute_risk(portfolio_name="default")
        finally:
            svc.close()
    return _run


def _make_market_breadth() -> callable:
    def _run():
        from logic_layer.market_breadth.service import MarketBreadthService
        svc = MarketBreadthService()
        try:
            bundle = svc.build_latest_context_bundle()
            svc.save_snapshot(bundle)
        finally:
            svc.close()
    return _run


def _make_asset_readiness() -> callable:
    def _run():
        from logic_layer.asset_readiness.service import AssetReadinessService
        svc = AssetReadinessService()
        try:
            bundle = svc.build_latest_context_bundle()
            svc.save_snapshot(bundle)
        finally:
            svc.close()
    return _run


def _make_ai_market_context() -> callable:
    def _run():
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
    return _run


def _make_pipeline_latency() -> callable:
    def _run():
        from logic_layer.pipeline_latency.service import PipelineLatencyService
        svc = PipelineLatencyService()
        try:
            svc.measure_all()
        finally:
            svc.close()
    return _run


def _make_liquidation_cascade() -> callable:
    def _run():
        from logic_layer.liquidation_cascade.service import LiquidationCascadeService
        svc = LiquidationCascadeService()
        try:
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_cross_venue_arbitrage() -> callable:
    def _run():
        from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService
        svc = CrossVenueArbService()
        try:
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_onchain_lead_lag() -> callable:
    def _run():
        from logic_layer.onchain_lead_lag.service import OnchainLeadLagService
        svc = OnchainLeadLagService()
        try:
            svc.run_all()
        finally:
            svc.close()
    return _run


def _invalidate_api_cache_by_modules(completed_modules: list[str]) -> None:
    """按模块粒度清空相关 API 缓存（事件驱动失效）。

    每个模块映射到一组缓存前缀，只清空受影响的缓存条目，
    而非全量清空。如果超过 50% 模块完成，则全量清空。
    """
    # 模块 → 缓存前缀映射
    MODULE_CACHE_PREFIXES: dict[str, list[str]] = {
        "technical_indicators": ["tech:", "tech_deep:"],
        "feature_standardization": ["features:"],
        "cross_asset_analysis": ["cross:"],
        "exchange_comparison": ["exchange:"],
        "macro_context": ["macro:"],
        "news_sentiment": ["sentiment:", "news:"],
        "market_structure": ["microstructure:"],
        "portfolio_risk": ["risk:", "portfolio:"],
        "market_breadth": ["breadth:"],
        "asset_readiness": ["readiness:"],
        "ai_market_context": ["bundle:", "ai_context:"],
        "pipeline_latency": ["health:"],
        "liquidation_cascade": ["liquidation_cascade:"],
        "cross_venue_arbitrage": ["cross_venue_arb:"],
        "onchain_lead_lag": ["onchain_lead_lag:"],
    }

    try:
        from api.cache import cache
        from api.query_cache import query_cache

        # 超过半数模块完成 → 全量清空更高效
        if len(completed_modules) > 6:
            cleared = cache.invalidate_all()
            query_cache.invalidate_all()
            if cleared:
                logger.info("已全量清空 API 缓存 ({} 条)", cleared)
            return

        # 按模块粒度清空
        total_cleared = 0
        for module in completed_modules:
            prefixes = MODULE_CACHE_PREFIXES.get(module, [])
            for prefix in prefixes:
                total_cleared += cache.invalidate_prefix(prefix)

        # query_cache 不支持前缀清空，全量清空
        if completed_modules:
            query_cache.invalidate_all()

        if total_cleared:
            logger.info(
                "已按模块清空 API 缓存 ({} 条, 模块: {})",
                total_cleared, ", ".join(completed_modules[:5]),
            )
    except Exception as exc:
        logger.debug("API 缓存清空跳过（API 未启动或导入失败）: {}", exc)


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
