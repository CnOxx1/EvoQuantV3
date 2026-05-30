"""特征注册表：定义哪些特征需要标准化、使用哪些方法、归属哪个复合维度。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    """单个特征的标准化配置。"""

    name: str
    source_column: str
    methods: tuple[str, ...]
    composite_group: str | None = None
    invert: bool = False


# 滚动窗口大小（1h bars）
MIN_BARS_7D = 7 * 24  # 168
MIN_BARS_30D = 30 * 24  # 720

# 置信度阈值
CONFIDENCE_THRESHOLD_HIGH = 0.8
CONFIDENCE_THRESHOLD_MEDIUM = 0.5

# 核心特征注册表
FEATURE_REGISTRY: list[FeatureSpec] = [
    # --- Momentum ---
    FeatureSpec("rsi_14", "rsi_14", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("rsi_28", "rsi_28", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("macd_histogram", "macd_histogram", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("roc_12", "roc_12", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("cci_20", "cci_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("williams_r_14", "williams_r_14", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum", invert=True),
    FeatureSpec("stoch_rsi_k_14", "stoch_rsi_k_14", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    FeatureSpec("tsi_line", "tsi_line", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "momentum"),
    # --- Volatility ---
    FeatureSpec("atr_pct_14", "atr_pct_14", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "volatility"),
    FeatureSpec("bb_width", "bb_width", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "volatility"),
    FeatureSpec("historical_volatility_20", "historical_volatility_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "volatility"),
    FeatureSpec("keltner_width_20", "keltner_width_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "volatility"),
    FeatureSpec("chaikin_volatility_10", "chaikin_volatility_10", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "volatility"),
    # --- Leverage ---
    FeatureSpec("funding_rate_mean", "funding_rate_mean", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "leverage"),
    FeatureSpec("funding_rate_std", "funding_rate_std", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "leverage"),
    # --- Flow ---
    FeatureSpec("obv_slope_20", "obv_slope_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "flow"),
    FeatureSpec("cmf_20", "cmf_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "flow"),
    FeatureSpec("volume_zscore_20", "volume_zscore_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "flow"),
    FeatureSpec("force_index_13", "force_index_13", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "flow"),
    FeatureSpec("pvo_line", "pvo_line", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), "flow"),
    # --- Standalone (no composite) ---
    FeatureSpec("adx_14", "adx_14", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), None),
    FeatureSpec("linear_reg_r2_20", "linear_reg_r2_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), None),
    FeatureSpec("sharpe_like_20", "sharpe_like_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), None),
    FeatureSpec("sortino_like_20", "sortino_like_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), None),
    FeatureSpec("return_skew_20", "return_skew_20", ("zscore_7d", "zscore_30d", "percentile_30d", "cross_rank"), None),
    FeatureSpec("orderbook_depth_imbalance_mean", "orderbook_depth_imbalance_mean", ("zscore_7d", "zscore_30d", "cross_rank"), None),
    FeatureSpec("orderbook_spread_bps_mean", "orderbook_spread_bps_mean", ("zscore_7d", "zscore_30d", "cross_rank"), None),
]

# 复合维度定义（自动从 FEATURE_REGISTRY 生成）
COMPOSITE_DEFINITIONS: dict[str, list[str]] = {}
for _spec in FEATURE_REGISTRY:
    if _spec.composite_group:
        COMPOSITE_DEFINITIONS.setdefault(_spec.composite_group, []).append(_spec.name)
