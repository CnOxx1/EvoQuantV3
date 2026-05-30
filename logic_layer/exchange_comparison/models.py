from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Optional

from pydantic import BaseModel, Field


class ExchangeComparisonConfig(BaseModel):
    """交易所横向对比的可调参数。"""

    snapshot_lookback_seconds: int = Field(
        default=1800,
        ge=30,
        description="读取候选 orderbook 快照的回看窗口。",
    )
    compare_window_seconds: int = Field(
        default=5,
        ge=1,
        description="不同交易所 ticker 快照允许的最大时间差。",
    )
    orderbook_window_seconds: int = Field(
        default=5,
        ge=1,
        description="orderbook 相对 ticker 的最近邻对齐窗口。",
    )
    funding_window_seconds: int = Field(
        default=1800,
        ge=60,
        description="funding 相对 ticker 的最近邻对齐窗口。",
    )
    max_ticker_age_seconds: int = Field(
        default=30,
        ge=1,
        description="超过该时长的 ticker 视为陈旧数据。",
    )
    max_orderbook_age_seconds: int = Field(
        default=15,
        ge=1,
        description="超过该时长的 orderbook 视为陈旧数据。",
    )
    max_funding_age_seconds: int = Field(
        default=21600,
        ge=60,
        description="超过该时长的 funding 视为陈旧数据。",
    )
    max_indicator_age_seconds: int = Field(
        default=21600,
        ge=60,
        description="超过该时长的技术背景特征视为陈旧数据。",
    )
    market_type: str = Field(
        default="spot",
        description="优先读取的 market_info 市场类型。",
    )
    include_funding_context: bool = Field(
        default=True,
        description="是否合并 funding 上下文特征。",
    )
    include_indicator_context: bool = Field(
        default=True,
        description="是否合并 technical_indicators 背景特征。",
    )
    indicator_timeframe: str = Field(
        default="1h",
        description="读取技术指标背景特征时使用的周期。",
    )
    default_taker_fee_rate: float = Field(
        default=0.001,
        ge=0,
        description="market_info 缺失时使用的默认 taker fee。",
    )
    target_notional: float = Field(
        default=10000.0,
        gt=0,
        description="滑点和可执行性估算的目标名义成交额。",
    )
    min_actionable_net_spread_bps: float = Field(
        default=2.0,
        ge=0,
        description="净价差达到该阈值后才认为具备可执行性。",
    )
    divergence_alert_bps: float = Field(
        default=15.0,
        ge=0,
        description="中间价偏离超过该阈值时记为 price_divergence。",
    )
    anomaly_alert_bps: float = Field(
        default=35.0,
        ge=0,
        description="用于 anomaly_score 的中间价偏离参考阈值。",
    )
    funding_divergence_alert_bps: float = Field(
        default=5.0,
        ge=0,
        description="资金费率偏离超过该阈值时认为存在 funding divergence。",
    )
    liquidity_buffer_ratio: float = Field(
        default=1.25,
        ge=0.1,
        description="最优方向两条腿都至少达到该倍数深度才认为流动性充足。",
    )
    low_liquidity_depth_ratio: float = Field(
        default=0.75,
        ge=0.1,
        description="低于该倍数深度时倾向输出 liquidity_warning。",
    )
    max_slippage_bps: float = Field(
        default=25.0,
        ge=0,
        description="经验滑点估算的软上限，用于执行过滤。",
    )
    trend_adx_threshold: float = Field(
        default=25.0,
        ge=0,
        description="技术背景中判断趋势市场的 ADX 阈值。",
    )
    high_volatility_atr_pct: float = Field(
        default=2.5,
        ge=0,
        description="技术背景中判断高波动环境的 ATR% 阈值。",
    )
    extreme_price_zscore: float = Field(
        default=2.0,
        ge=0,
        description="技术背景中判断价格偏离极端的 zscore 阈值。",
    )


class ExchangeComparisonSnapshot(BaseModel):
    """跨交易所对比结果行。"""

    TABLE_COLUMNS: ClassVar[list[str]] = [
        "symbol",
        "exchange_a",
        "exchange_b",
        "compare_window_seconds",
        "timestamp",
        "ticker_timestamp_a",
        "ticker_timestamp_b",
        "orderbook_timestamp_a",
        "orderbook_timestamp_b",
        "funding_timestamp_a",
        "funding_timestamp_b",
        "last_price_a",
        "last_price_b",
        "mid_price_a",
        "mid_price_b",
        "bid_a",
        "ask_a",
        "bid_b",
        "ask_b",
        "spread_bps_a",
        "spread_bps_b",
        "quote_volume_24h_a",
        "quote_volume_24h_b",
        "bid_depth_notional_a",
        "bid_depth_notional_b",
        "ask_depth_notional_a",
        "ask_depth_notional_b",
        "depth_imbalance_a",
        "depth_imbalance_b",
        "funding_rate_a",
        "funding_rate_b",
        "mark_price_a",
        "mark_price_b",
        "index_price_a",
        "index_price_b",
        "last_diff_abs",
        "last_diff_bps",
        "mid_diff_abs",
        "mid_diff_bps",
        "bid_diff_bps",
        "ask_diff_bps",
        "funding_rate_diff_abs",
        "funding_rate_diff_bps",
        "mark_price_diff_bps",
        "index_price_diff_bps",
        "cross_spread_ab_bps",
        "cross_spread_ba_bps",
        "estimated_fee_bps",
        "estimated_slippage_ab_bps",
        "estimated_slippage_ba_bps",
        "estimated_slippage_bps",
        "net_cross_spread_ab_bps",
        "net_cross_spread_ba_bps",
        "net_cross_spread_max_bps",
        "quote_volume_ratio",
        "bid_depth_ratio",
        "ask_depth_ratio",
        "total_depth_ratio",
        "spread_bps_gap",
        "depth_imbalance_gap",
        "inter_exchange_ticker_gap_ms",
        "inter_exchange_funding_gap_ms",
        "context_timeframe",
        "context_open_time",
        "context_age_seconds",
        "context_close",
        "context_rsi_14",
        "context_macd_hist",
        "context_atr_pct_14",
        "context_volatility_20",
        "context_adx_14",
        "context_bb_width",
        "context_price_zscore_20",
        "context_volume_ratio_20",
        "context_cross_exchange_last_price_range_bps",
        "context_funding_basis_bps_mean",
        "context_orderbook_total_depth_notional",
        "best_buy_exchange",
        "best_sell_exchange",
        "opportunity_type",
        "signal_label",
        "signal_strength",
        "is_actionable",
        "anomaly_score",
        "execution_preference_score",
        "market_regime_label",
        "funding_regime_label",
        "context_completeness_score",
        "data_quality_flag",
        "raw_context_json",
    ]

    symbol: str
    exchange_a: str
    exchange_b: str
    compare_window_seconds: int
    timestamp: datetime
    ticker_timestamp_a: Optional[datetime] = None
    ticker_timestamp_b: Optional[datetime] = None
    orderbook_timestamp_a: Optional[datetime] = None
    orderbook_timestamp_b: Optional[datetime] = None
    funding_timestamp_a: Optional[datetime] = None
    funding_timestamp_b: Optional[datetime] = None
    last_price_a: Optional[float] = None
    last_price_b: Optional[float] = None
    mid_price_a: Optional[float] = None
    mid_price_b: Optional[float] = None
    bid_a: Optional[float] = None
    ask_a: Optional[float] = None
    bid_b: Optional[float] = None
    ask_b: Optional[float] = None
    spread_bps_a: Optional[float] = None
    spread_bps_b: Optional[float] = None
    quote_volume_24h_a: Optional[float] = None
    quote_volume_24h_b: Optional[float] = None
    bid_depth_notional_a: Optional[float] = None
    bid_depth_notional_b: Optional[float] = None
    ask_depth_notional_a: Optional[float] = None
    ask_depth_notional_b: Optional[float] = None
    depth_imbalance_a: Optional[float] = None
    depth_imbalance_b: Optional[float] = None
    funding_rate_a: Optional[float] = None
    funding_rate_b: Optional[float] = None
    mark_price_a: Optional[float] = None
    mark_price_b: Optional[float] = None
    index_price_a: Optional[float] = None
    index_price_b: Optional[float] = None
    last_diff_abs: Optional[float] = None
    last_diff_bps: Optional[float] = None
    mid_diff_abs: Optional[float] = None
    mid_diff_bps: Optional[float] = None
    bid_diff_bps: Optional[float] = None
    ask_diff_bps: Optional[float] = None
    funding_rate_diff_abs: Optional[float] = None
    funding_rate_diff_bps: Optional[float] = None
    mark_price_diff_bps: Optional[float] = None
    index_price_diff_bps: Optional[float] = None
    cross_spread_ab_bps: Optional[float] = None
    cross_spread_ba_bps: Optional[float] = None
    estimated_fee_bps: Optional[float] = None
    estimated_slippage_ab_bps: Optional[float] = None
    estimated_slippage_ba_bps: Optional[float] = None
    estimated_slippage_bps: Optional[float] = None
    net_cross_spread_ab_bps: Optional[float] = None
    net_cross_spread_ba_bps: Optional[float] = None
    net_cross_spread_max_bps: Optional[float] = None
    quote_volume_ratio: Optional[float] = None
    bid_depth_ratio: Optional[float] = None
    ask_depth_ratio: Optional[float] = None
    total_depth_ratio: Optional[float] = None
    spread_bps_gap: Optional[float] = None
    depth_imbalance_gap: Optional[float] = None
    inter_exchange_ticker_gap_ms: Optional[float] = None
    inter_exchange_funding_gap_ms: Optional[float] = None
    context_timeframe: Optional[str] = None
    context_open_time: Optional[datetime] = None
    context_age_seconds: Optional[float] = None
    context_close: Optional[float] = None
    context_rsi_14: Optional[float] = None
    context_macd_hist: Optional[float] = None
    context_atr_pct_14: Optional[float] = None
    context_volatility_20: Optional[float] = None
    context_adx_14: Optional[float] = None
    context_bb_width: Optional[float] = None
    context_price_zscore_20: Optional[float] = None
    context_volume_ratio_20: Optional[float] = None
    context_cross_exchange_last_price_range_bps: Optional[float] = None
    context_funding_basis_bps_mean: Optional[float] = None
    context_orderbook_total_depth_notional: Optional[float] = None
    best_buy_exchange: Optional[str] = None
    best_sell_exchange: Optional[str] = None
    opportunity_type: str = "none"
    signal_label: str = "normal"
    signal_strength: float = 0.0
    is_actionable: bool = False
    anomaly_score: float = 0.0
    execution_preference_score: float = 0.0
    market_regime_label: str = "unknown"
    funding_regime_label: str = "not_applicable"
    context_completeness_score: float = 0.0
    data_quality_flag: str = "ok"
    raw_context_json: Optional[str] = None
