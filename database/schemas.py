"""数据库域拆分：表名常量与方法名映射。

三个域：
- EXCHANGE_DATA: 高频交易所数据（ticker 5s, orderbook 3s, klines 60s）
- MARKET_DATA: 中低频市场数据（macro, onchain, tokenomics, options, alternative, news, events）
- ANALYTICS: 逻辑层输出（技术指标、跨所对比、市场结构、AI 上下文等）
"""

# ---------------------------------------------------------------------------
# 域 → 表创建方法名（对应 DBManager 上的 _create_xxx_table 方法）
# ---------------------------------------------------------------------------

EXCHANGE_DATA_INIT_METHODS: list[str] = [
    "_create_market_info_table",
    "_create_klines_table",
    "_create_tickers_table",
    "_create_latest_tickers_table",
    "_create_funding_rates_table",
    "_create_latest_funding_rates_table",
    "_create_orderbook_snapshots_table",
    "_create_latest_orderbook_snapshots_table",
    "_create_trade_flow_bars_table",
    "_create_latest_trade_flow_bars_table",
    "_create_open_interest_snapshots_table",
    "_create_latest_open_interest_snapshots_table",
    "_create_liquidation_bars_table",
    "_create_latest_liquidation_bars_table",
    "_create_positioning_snapshots_table",
    "_create_latest_positioning_snapshots_table",
    "_create_basis_snapshots_table",
    "_create_latest_basis_snapshots_table",
]

MARKET_DATA_INIT_METHODS: list[str] = [
    "_create_macro_factor_catalog_table",
    "_create_macro_timeseries_table",
    "_create_latest_macro_timeseries_table",
    "_create_onchain_factor_catalog_table",
    "_create_onchain_timeseries_table",
    "_create_latest_onchain_timeseries_table",
    "_create_tokenomics_factor_catalog_table",
    "_create_tokenomics_timeseries_table",
    "_create_latest_tokenomics_timeseries_table",
    "_create_options_factor_catalog_table",
    "_create_options_timeseries_table",
    "_create_latest_options_timeseries_table",
    "_create_token_unlock_events_table",
    "_create_alternative_factor_catalog_table",
    "_create_alternative_timeseries_table",
    "_create_latest_alternative_timeseries_table",
    "_create_news_articles_table",
    "_create_event_calendar_events_table",
]

ANALYTICS_INIT_METHODS: list[str] = [
    "_create_collection_runs_table",
    "_create_merged_klines_table",
    "_create_technical_indicators_table",
    "_create_exchange_comparison_snapshots_table",
    "_create_macro_context_snapshots_table",
    "_create_ai_market_context_snapshots_table",
    "_create_market_breadth_snapshots_table",
    "_create_market_structure_snapshots_table",
    "_create_asset_readiness_snapshots_table",
    "_create_data_quality_audit_snapshots_table",
    "_create_cross_asset_analysis_tables",
    "_create_portfolio_risk_tables",
    "_create_feature_standardization_tables",
]

# ---------------------------------------------------------------------------
# 域 → 物理表名列表（用于 ATTACH + VIEW 创建）
# ---------------------------------------------------------------------------

EXCHANGE_DATA_TABLE_NAMES: list[str] = [
    "market_info",
    "klines",
    "tickers",
    "latest_tickers",
    "funding_rates",
    "latest_funding_rates",
    "orderbook_snapshots",
    "latest_orderbook_snapshots",
    "trade_flow_bars",
    "latest_trade_flow_bars",
    "open_interest_snapshots",
    "latest_open_interest_snapshots",
    "liquidation_bars",
    "latest_liquidation_bars",
    "positioning_snapshots",
    "latest_positioning_snapshots",
    "basis_snapshots",
    "latest_basis_snapshots",
]

MARKET_DATA_TABLE_NAMES: list[str] = [
    "macro_factor_catalog",
    "macro_timeseries",
    "latest_macro_timeseries",
    "onchain_factor_catalog",
    "onchain_timeseries",
    "latest_onchain_timeseries",
    "tokenomics_factor_catalog",
    "tokenomics_timeseries",
    "latest_tokenomics_timeseries",
    "options_factor_catalog",
    "options_timeseries",
    "latest_options_timeseries",
    "token_unlock_events",
    "alternative_factor_catalog",
    "alternative_timeseries",
    "latest_alternative_timeseries",
    "news_articles",
    "event_calendar_events",
]
