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
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from core.feature_flags import feature_flags
from config.symbols import TARGET_ASSET_CODES


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

# v4.1.0: 模块依赖映射（用于上游失败快跳）
_MODULE_DEPENDENCIES: dict[str, set[str]] = {
    "feature_standardization": {"technical_indicators"},
    "cross_asset_analysis": {"technical_indicators"},
    "portfolio_risk": {"cross_asset_analysis"},
    # Audit is best-effort (paper trail); do not hard-block readiness if audit fails.
    "asset_readiness": {"feature_standardization", "cross_asset_analysis"},
    "ai_market_context": {"portfolio_risk", "market_breadth", "asset_readiness"},
    "pipeline_latency": {"ai_market_context"},
}


def _has_failed_dependency(module_name: str, failed_modules: set[str]) -> bool:
    """检查模块的上游依赖是否包含失败模块。"""
    deps = _MODULE_DEPENDENCIES.get(module_name, set())
    return bool(deps & failed_modules)


def _is_source_unavailable_error(error: Exception) -> bool:
    """判断异常是否表示可选上游数据尚未采集或初始化。"""
    message = str(error).lower()
    return "no such table" in message or (
        "relation" in message and "does not exist" in message
    )


# Prometheus 管道阶段计时（优雅降级）
try:
    from monitoring.metrics import PIPELINE_PHASE_DURATION, PIPELINE_TOTAL_DURATION
    _METRICS_AVAILABLE = True
except ImportError:
    _METRICS_AVAILABLE = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _run_phase(phase_name: str, tasks: list[tuple[str, callable]], failed_upstream: set[str] | None = None) -> dict[str, str]:
    """执行一个阶段内的所有任务（串行），返回 {module_name: status}。

    v4.1.0: 支持 failed_upstream 跳过依赖已失败的模块。
    """
    results = {}
    for module_name, task_fn in tasks:
        # 特性开关检查
        if not feature_flags.is_enabled(module_name):
            logger.debug("逻辑管道 [{}] {} 已被特性开关禁用，跳过", phase_name, module_name)
            results[module_name] = "skipped:disabled"
            continue
        # v4.1.0: 上游失败快跳
        if failed_upstream and _has_failed_dependency(module_name, failed_upstream):
            logger.info("逻辑管道 [{}] {} 跳过（上游依赖失败）", phase_name, module_name)
            results[module_name] = "skipped:upstream_failure"
            continue
        started = time.monotonic()
        try:
            task_fn()
            elapsed = time.monotonic() - started
            logger.info(
                "逻辑管道 [{}] {} 完成 ({:.1f}s)",
                phase_name, module_name, elapsed,
            )
            if _METRICS_AVAILABLE:
                PIPELINE_PHASE_DURATION.labels(phase=phase_name, module=module_name, status="success").observe(elapsed)
            results[module_name] = "success"
        except Exception as exc:
            elapsed = time.monotonic() - started
            if _is_source_unavailable_error(exc):
                logger.info(
                    "逻辑管道 [{}] {} 跳过 ({:.1f}s)：输入源尚未初始化 ({})",
                    phase_name, module_name, elapsed, exc,
                )
                if _METRICS_AVAILABLE:
                    PIPELINE_PHASE_DURATION.labels(
                        phase=phase_name, module=module_name, status="skipped"
                    ).observe(elapsed)
                results[module_name] = "skipped:source_unavailable"
                continue
            logger.error(
                "逻辑管道 [{}] {} 失败 ({:.1f}s): {}",
                phase_name, module_name, elapsed, exc,
            )
            if _METRICS_AVAILABLE:
                PIPELINE_PHASE_DURATION.labels(phase=phase_name, module=module_name, status="error").observe(elapsed)
            results[module_name] = f"error: {type(exc).__name__}"
    return results


def _run_phase_parallel(
    phase_name: str,
    tasks: list[tuple[str, callable]],
    max_workers: int = PHASE2_MAX_WORKERS,
    timeout: int = PHASE2_TASK_TIMEOUT,
) -> dict[str, str]:
    """并行执行一个阶段内的所有任务，返回 {module_name: status}。

    优化 #12: 使用 wait(FIRST_EXCEPTION) 快速失败检测，
    避免 as_completed + 二次遍历的开销。
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_name = {}
        for module_name, task_fn in tasks:
            future = executor.submit(_execute_task, phase_name, module_name, task_fn)
            future_to_name[future] = module_name

        done, not_done = wait(future_to_name.keys(), timeout=timeout, return_when=FIRST_EXCEPTION)

        for future in done:
            module_name = future_to_name[future]
            try:
                results[module_name] = future.result()
            except Exception as exc:
                results[module_name] = f"error: {type(exc).__name__}"

        # 等待剩余任务（带剩余超时）
        if not_done:
            remaining_done, still_pending = wait(not_done, timeout=max(1, timeout // 2))
            for future in remaining_done:
                module_name = future_to_name[future]
                try:
                    results[module_name] = future.result()
                except Exception as exc:
                    results[module_name] = f"error: {type(exc).__name__}"
            for future in still_pending:
                module_name = future_to_name[future]
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
        if _METRICS_AVAILABLE:
            PIPELINE_PHASE_DURATION.labels(phase=phase_name, module=module_name, status="success").observe(elapsed)
        return "success"
    except Exception as exc:
        elapsed = time.monotonic() - started
        if _is_source_unavailable_error(exc):
            logger.info(
                "逻辑管道 [{}] {} 跳过 ({:.1f}s)：输入源尚未初始化 ({})",
                phase_name, module_name, elapsed, exc,
            )
            if _METRICS_AVAILABLE:
                PIPELINE_PHASE_DURATION.labels(
                    phase=phase_name, module=module_name, status="skipped"
                ).observe(elapsed)
            return "skipped:source_unavailable"
        logger.error(
            "逻辑管道 [{}] {} 失败 ({:.1f}s): {}",
            phase_name, module_name, elapsed, exc,
        )
        if _METRICS_AVAILABLE:
            PIPELINE_PHASE_DURATION.labels(phase=phase_name, module=module_name, status="error").observe(elapsed)
        return f"error: {type(exc).__name__}"


def run_full_pipeline() -> dict[str, object]:
    """执行逻辑层全链路，返回各阶段结果摘要。"""
    pipeline_start = _utc_now()

    if USE_DAG:
        all_results = _run_dag_pipeline()
    else:
        all_results = _run_classic_pipeline()

    pipeline_end = _utc_now()
    total_elapsed = (pipeline_end - pipeline_start).total_seconds()
    success_count = sum(1 for v in all_results.values() if v == "success")
    total_count = len(all_results)

    if _METRICS_AVAILABLE:
        PIPELINE_TOTAL_DURATION.observe(total_elapsed)

    logger.info(
        "逻辑管道全链路完成: {}/{} 成功, 耗时 {:.1f}s{}",
        success_count, total_count,
        total_elapsed,
        " [DAG模式]" if USE_DAG else "",
    )

    # 管道完成后按模块粒度清空 API 缓存
    _invalidate_api_cache_by_modules(
        [k for k, v in all_results.items() if v == "success"]
    )

    # WebSocket 广播管道完成事件
    _broadcast_pipeline_complete(total_elapsed, success_count, total_count)

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
        ModuleNode("holder_behavior_analysis", _make_holder_behavior_analysis()),
        ModuleNode("liquidity_regime", _make_liquidity_regime()),
        ModuleNode("event_probability", _make_event_probability()),
        ModuleNode("miner_pressure", _make_miner_pressure()),
        ModuleNode("market_sentiment_composite", _make_market_sentiment_composite()),
        ModuleNode("stablecoin_pulse", _make_stablecoin_pulse(),
                   depends_on=["technical_indicators"]),
        ModuleNode("unlock_impact", _make_unlock_impact(),
                   depends_on=["technical_indicators"]),
        ModuleNode("depth_regime", _make_depth_regime(),
                   depends_on=["technical_indicators"]),
        ModuleNode("smart_money_conviction", _make_smart_money_conviction(),
                   depends_on=["technical_indicators"]),
        ModuleNode("defi_stress", _make_defi_stress(),
                   depends_on=["technical_indicators"]),
        ModuleNode("retail_fomo_index", _make_retail_fomo_index()),
        ModuleNode("portfolio_risk", _make_portfolio_risk(),
                   depends_on=["cross_asset_analysis"]),
        ModuleNode("market_breadth", _make_market_breadth()),
        ModuleNode("data_quality_audit", _make_data_quality_audit()),
        ModuleNode("asset_readiness", _make_asset_readiness(),
                   depends_on=["feature_standardization", "cross_asset_analysis"]),
        ModuleNode("ai_market_context", _make_ai_market_context(),
                   depends_on=["portfolio_risk", "market_breadth", "asset_readiness"]),
        ModuleNode("pipeline_latency", _make_pipeline_latency(),
                   depends_on=["ai_market_context"]),
    ]
    return run_dag(nodes)


def _run_classic_pipeline() -> dict[str, str]:
    """经典模式：固定 5 阶段串行/并行混合。

    v4.1.0: 跟踪失败模块集合，下游阶段自动跳过依赖失败的模块。
    """
    all_results: dict[str, str] = {}
    failed_modules: set[str] = set()

    # === Phase 1: 技术指标 ===
    results = _run_phase("Phase1", [
        ("technical_indicators", _make_technical_indicators()),
    ])
    all_results.update(results)
    failed_modules.update(k for k, v in results.items() if "error" in v)

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
        ("holder_behavior_analysis", _make_holder_behavior_analysis()),
        ("liquidity_regime", _make_liquidity_regime()),
        ("event_probability", _make_event_probability()),
        ("miner_pressure", _make_miner_pressure()),
        ("market_sentiment_composite", _make_market_sentiment_composite()),
        ("stablecoin_pulse", _make_stablecoin_pulse()),
        ("unlock_impact", _make_unlock_impact()),
        ("depth_regime", _make_depth_regime()),
        ("smart_money_conviction", _make_smart_money_conviction()),
        ("defi_stress", _make_defi_stress()),
        ("retail_fomo_index", _make_retail_fomo_index()),
    ])
    all_results.update(results)
    failed_modules.update(k for k, v in results.items() if "error" in v)

    # === Phase 3: 依赖 Phase 2 的模块 ===
    results = _run_phase("Phase3", [
        ("data_quality_audit", _make_data_quality_audit()),
        ("portfolio_risk", _make_portfolio_risk()),
        ("market_breadth", _make_market_breadth()),
        ("asset_readiness", _make_asset_readiness()),
    ], failed_upstream=failed_modules)
    all_results.update(results)
    failed_modules.update(k for k, v in results.items() if "error" in v)

    # === Phase 4: 最终 AI 上下文聚合 ===
    results = _run_phase("Phase4", [
        ("ai_market_context", _make_ai_market_context()),
    ], failed_upstream=failed_modules)
    all_results.update(results)
    failed_modules.update(k for k, v in results.items() if "error" in v)

    # === Phase 5: 管道延迟监控 ===
    results = _run_phase("Phase5", [
        ("pipeline_latency", _make_pipeline_latency()),
    ], failed_upstream=failed_modules)
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


def _make_data_quality_audit() -> callable:
    """Persist market-world audit snapshot for paper-grade daily panels."""
    def _run():
        from data_layer.data_quality.audit import DataLayerAuditService
        DataLayerAuditService().save_market_world_audit_snapshot()
    return _run


def _make_asset_readiness() -> callable:
    def _run():
        from logic_layer.asset_readiness.service import AssetReadinessService
        svc = AssetReadinessService()
        try:
            bundle = svc.build_latest_context_bundle()
            # Ensure dated snapshot_time field exists for PIT replay consumers.
            if isinstance(bundle, dict) and "snapshot_time" not in bundle:
                bundle["snapshot_time"] = bundle.get("generated_at") or bundle.get("as_of")
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
                entity_keys=TARGET_ASSET_CODES,
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
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_cross_venue_arbitrage() -> callable:
    def _run():
        from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService
        svc = CrossVenueArbService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_onchain_lead_lag() -> callable:
    def _run():
        from logic_layer.onchain_lead_lag.service import OnchainLeadLagService
        svc = OnchainLeadLagService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_holder_behavior_analysis() -> callable:
    def _run():
        from logic_layer.holder_behavior_analysis.service import HolderBehaviorService
        svc = HolderBehaviorService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_liquidity_regime() -> callable:
    def _run():
        from logic_layer.liquidity_regime.service import LiquidityRegimeService
        svc = LiquidityRegimeService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_event_probability() -> callable:
    def _run():
        from logic_layer.event_probability.service import EventProbabilityService
        svc = EventProbabilityService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_miner_pressure() -> callable:
    def _run():
        from logic_layer.miner_pressure.service import MinerPressureService
        svc = MinerPressureService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_market_sentiment_composite() -> callable:
    def _run():
        from logic_layer.market_sentiment_composite.service import MarketSentimentCompositeService
        svc = MarketSentimentCompositeService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_stablecoin_pulse() -> callable:
    def _run():
        from logic_layer.stablecoin_pulse.service import StablecoinPulseService
        svc = StablecoinPulseService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_unlock_impact() -> callable:
    def _run():
        from logic_layer.unlock_impact.service import UnlockImpactService
        svc = UnlockImpactService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_depth_regime() -> callable:
    def _run():
        from logic_layer.depth_regime.service import DepthRegimeService
        svc = DepthRegimeService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_smart_money_conviction() -> callable:
    def _run():
        from logic_layer.smart_money_conviction.service import SmartMoneyConvictionService
        svc = SmartMoneyConvictionService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_defi_stress() -> callable:
    def _run():
        from logic_layer.defi_stress.service import DefiStressService
        svc = DefiStressService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _make_retail_fomo_index() -> callable:
    def _run():
        from logic_layer.retail_fomo_index.service import RetailFomoIndexService
        svc = RetailFomoIndexService()
        try:
            svc.init_storage()
            svc.run_all()
        finally:
            svc.close()
    return _run


def _invalidate_api_cache_by_modules(completed_modules: list[str]) -> None:
    """按模块粒度清空相关 API 缓存（事件驱动失效）。

    使用 cache_deps DAG 精准计算需失效的下游模块缓存，
    每个模块映射到一组缓存前缀，只清空受影响的缓存条目。
    如果超过 50% 模块完成，则全量清空。
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
        "holder_behavior_analysis": ["holder_behavior:"],
        "liquidity_regime": ["liquidity_regime:"],
        "event_probability": ["event_probability:"],
        "miner_pressure": ["miner_pressure:"],
        "market_sentiment_composite": ["sentiment_composite:"],
        "stablecoin_pulse": ["stablecoin_pulse:"],
        "unlock_impact": ["unlock_impact:"],
        "depth_regime": ["depth_regime:"],
        "smart_money_conviction": ["smart_money_conviction:"],
        "defi_stress": ["defi_stress:"],
        "retail_fomo_index": ["retail_fomo:"],
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

        # query_cache 同样按前缀清空（v3.4.0 已支持 invalidate_prefix）
        for module in completed_modules:
            prefixes = MODULE_CACHE_PREFIXES.get(module, [])
            for prefix in prefixes:
                query_cache.invalidate_prefix(prefix)

        if total_cleared:
            logger.info(
                "已按模块清空 API 缓存 ({} 条, 模块: {})",
                total_cleared, ", ".join(completed_modules[:5]),
            )
    except Exception as exc:
        logger.debug("API 缓存清空跳过（API 未启动或导入失败）: {}", exc)


def _broadcast_pipeline_complete(
    elapsed: float, success_count: int, total_count: int
) -> None:
    """通过 WebSocket 广播管道完成事件。"""
    try:
        from api.websocket_manager import ws_manager

        ws_manager.broadcast_sync("pipeline", {
            "event": "pipeline_complete",
            "duration_seconds": round(elapsed, 2),
            "modules_succeeded": success_count,
            "modules_total": total_count,
            "timestamp": _utc_now().isoformat(),
        })
    except Exception as exc:
        logger.debug("WebSocket 广播跳过（API 未启动或导入失败）: {}", exc)


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
