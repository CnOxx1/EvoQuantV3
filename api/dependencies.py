"""FastAPI 依赖注入：数据库连接和服务实例（延迟加载）。

使用 DatabaseRouter 路由到拆分后的三个域数据库（exchange_data / market_data / analytics），
而非旧的单一 crypto_data.db。
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def get_router():
    """单例数据库路由器。"""
    from database.router import DatabaseRouter
    return DatabaseRouter()


@lru_cache(maxsize=1)
def get_ai_market_context_service():
    """单例 AI 市场上下文服务（不传 db，让服务自行使用 DatabaseRouter）。"""
    from logic_layer.ai_market_context.service import AIMarketContextService
    return AIMarketContextService()


@lru_cache(maxsize=1)
def get_pipeline_latency_service():
    """单例管道延迟服务。"""
    from logic_layer.pipeline_latency.service import PipelineLatencyService
    return PipelineLatencyService()


@lru_cache(maxsize=1)
def get_time_slice_service():
    """单例时间切片服务。"""
    from logic_layer.time_slice.service import TimeSliceService
    return TimeSliceService()


@lru_cache(maxsize=1)
def get_analytics_db():
    """单例 analytics 数据库连接。"""
    from database.router import DatabaseRouter
    return DatabaseRouter().get_analytics_db()


@lru_cache(maxsize=1)
def get_exchange_db():
    """单例 exchange_data 数据库连接。"""
    from database.router import DatabaseRouter
    return DatabaseRouter().get_exchange_db()


@lru_cache(maxsize=1)
def get_market_db():
    """单例 market_data 数据库连接。"""
    from database.router import DatabaseRouter
    return DatabaseRouter().get_market_db()


@lru_cache(maxsize=1)
def get_technical_service():
    """单例技术指标服务。"""
    from logic_layer.technical_indicators.service import TechnicalIndicatorService
    return TechnicalIndicatorService()


@lru_cache(maxsize=1)
def get_portfolio_risk_service():
    """单例组合风险服务。"""
    from logic_layer.portfolio_risk.service import PortfolioRiskService
    return PortfolioRiskService()


@lru_cache(maxsize=1)
def get_feature_standardization_service():
    """单例特征标准化服务。"""
    from logic_layer.feature_standardization.service import FeatureStandardizationService
    return FeatureStandardizationService()


@lru_cache(maxsize=1)
def get_macro_context_service():
    """单例宏观上下文服务。"""
    from logic_layer.macro_context.service import MacroContextService
    return MacroContextService()


@lru_cache(maxsize=1)
def get_cross_asset_service():
    """单例跨资产分析服务。"""
    from logic_layer.cross_asset_analysis.service import CrossAssetAnalysisService
    return CrossAssetAnalysisService()


@lru_cache(maxsize=1)
def get_news_sentiment_service():
    """单例新闻情感服务。"""
    from logic_layer.news_sentiment.service import NewsSentimentService
    return NewsSentimentService()


@lru_cache(maxsize=1)
def get_market_breadth_service():
    """单例市场广度服务。"""
    from logic_layer.market_breadth.service import MarketBreadthService
    return MarketBreadthService()


@lru_cache(maxsize=1)
def get_exchange_comparison_service():
    """单例交易所对比服务。"""
    from logic_layer.exchange_comparison.service import ExchangeComparisonService
    return ExchangeComparisonService()


# v4.4.0: context 端点服务单例化 — 消除逐请求 Service() 实例化开销
@lru_cache(maxsize=1)
def get_liquidity_regime_service():
    """单例流动性 regime 服务。"""
    from logic_layer.liquidity_regime.service import LiquidityRegimeService
    svc = LiquidityRegimeService()
    svc.init_storage()
    return svc


@lru_cache(maxsize=1)
def get_liquidation_cascade_service():
    """单例清算级联服务。"""
    from logic_layer.liquidation_cascade.service import LiquidationCascadeService
    return LiquidationCascadeService()


@lru_cache(maxsize=1)
def get_holder_behavior_service():
    """单例持有者行为服务。"""
    from logic_layer.holder_behavior_analysis.service import HolderBehaviorService
    return HolderBehaviorService()


@lru_cache(maxsize=1)
def get_miner_pressure_service():
    """单例矿工压力服务。"""
    from logic_layer.miner_pressure.service import MinerPressureService
    return MinerPressureService()


@lru_cache(maxsize=1)
def get_flow_decomposition_service():
    """单例资金流分解服务。"""
    from logic_layer.flow_decomposition.service import FlowDecompositionService
    return FlowDecompositionService()


@lru_cache(maxsize=1)
def get_temporal_pattern_service():
    """单例时间模式服务。"""
    from logic_layer.temporal_pattern.service import TemporalPatternService
    return TemporalPatternService()
