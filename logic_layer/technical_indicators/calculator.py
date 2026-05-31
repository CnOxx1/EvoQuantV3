from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


class TechnicalIndicatorCalculator:
    """基于合并后的主K线序列计算技术指标。"""

    OUTPUT_COLUMNS = [
        "symbol",
        "timeframe",
        "open_time",
        "close",
        "volume",
        "sma_5",
        "sma_10",
        "sma_20",
        "sma_60",
        "ema_7",
        "ema_20",
        "ema_50",
        "macd_line",
        "macd_signal",
        "macd_hist",
        "rsi_14",
        "rsi_28",
        "bb_middle",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "atr_14",
        "true_range_pct",
        "normalized_range_14",
        "historical_volatility_20",
        "chaikin_volatility_10",
        "relative_volatility_index_14",
        "stoch_k",
        "stoch_d",
        "stoch_j",
        "stochastic_momentum_index_14_3",
        "stochastic_momentum_signal_14_3",
        "plus_di_14",
        "minus_di_14",
        "adx_14",
        "adxr_14",
        "dmi_oscillator_14",
        "obv",
        "obv_slope_20",
        "return_1",
        "return_5",
        "return_20",
        "volatility_20",
        "sma_120",
        "ema_100",
        "dema_20",
        "tema_20",
        "hma_21",
        "zlema_20",
        "vwma_20",
        "price_to_vwma_20",
        "rolling_vwap_20",
        "rolling_vwap_deviation_20",
        "roc_12",
        "momentum_10",
        "rmi_14_5",
        "cfo_20",
        "awesome_oscillator_5_34",
        "accelerator_oscillator_5_34",
        "pfe_10",
        "cci_20",
        "mfi_14",
        "williams_r_14",
        "cmf_20",
        "donchian_high_20",
        "donchian_low_20",
        "donchian_mid_20",
        "ichimoku_tenkan_9",
        "ichimoku_kijun_26",
        "ichimoku_senkou_a",
        "ichimoku_senkou_b_52",
        "ichimoku_cloud_width",
        "ichimoku_cloud_position",
        "price_to_kijun_26",
        "ppo_line",
        "ppo_signal",
        "ppo_hist",
        "price_to_sma_20",
        "price_to_sma_60",
        "price_to_ema_20",
        "price_to_ema_50",
        "macd_hist_zscore_20",
        "volume_ratio_20",
        "price_zscore_20",
        "atr_pct_14",
        "parkinson_volatility_20",
        "garman_klass_volatility_20",
        "rogers_satchell_volatility_20",
        "keltner_middle_20",
        "keltner_upper_20",
        "keltner_lower_20",
        "keltner_width_20",
        "stoch_rsi_k_14",
        "stoch_rsi_d_14",
        "aroon_up_25",
        "aroon_down_25",
        "aroon_osc_25",
        "tsi_line",
        "tsi_signal",
        "stc_10_23_50",
        "ultimate_osc",
        "adl",
        "adl_slope_20",
        "chaikin_oscillator",
        "bb_percent_b",
        "donchian_width_20",
        "donchian_position_20",
        "vhf_28",
        "linear_reg_slope_20",
        "linear_reg_r2_20",
        "regression_distance_20",
        "ema_20_slope_5",
        "sma_20_slope_5",
        "rolling_drawdown_20",
        "cmo_14",
        "force_index_13",
        "supertrend_10_3",
        "supertrend_direction_10_3",
        "psar",
        "psar_trend",
        "trix_30",
        "dpo_20",
        "vortex_plus_14",
        "vortex_minus_14",
        "kama_10_2_30",
        "mass_index_25",
        "efficiency_ratio_10",
        "choppiness_index_14",
        "ulcer_index_14",
        "fisher_transform_9",
        "fisher_trigger_9",
        "coppock_curve_11_14_10",
        "coppock_signal_10",
        "kst_line",
        "kst_signal",
        "qstick_10",
        "demarker_14",
        "rvi_10",
        "rvi_signal_4",
        "squeeze_on_20",
        "squeeze_off_20",
        "price_percent_rank_20",
        "volume_percent_rank_20",
        "atr_percent_rank_20",
        "range_percent_rank_20",
        "volume_zscore_20",
        "balance_of_power",
        "candle_body_pct",
        "upper_shadow_pct",
        "lower_shadow_pct",
        "body_to_range_ratio",
        "close_location_value",
        "intrabar_trend_efficiency",
        "price_volume_trend",
        "nvi",
        "pvi",
        "kvo_line",
        "kvo_signal",
        "ease_of_movement_14",
        "volume_oscillator_5_20",
        "volume_price_correlation_20",
        "pvo_line",
        "pvo_signal",
        "pvo_hist",
        "downside_deviation_20",
        "upside_deviation_20",
        "sharpe_like_20",
        "sortino_like_20",
        "calmar_like_20",
        "gain_to_pain_ratio_20",
        "median_return_20",
        "mad_return_20",
        "return_iqr_20",
        "tail_ratio_20",
        "positive_return_ratio_20",
        "return_autocorr_20",
        "volume_autocorr_20",
        "return_skew_20",
        "return_kurtosis_20",
        "bull_power_13",
        "bear_power_13",
        # --- Batch 3: Crossover signals ---
        "ema_cross_7_20",
        "ema_cross_20_50",
        "sma_cross_10_60",
        "macd_cross_signal",
        "price_above_ema_count",
        "ma_alignment_score",
        "ichimoku_signal",
        "trend_consistency_20",
        # --- Batch 3: Pivot points ---
        "pivot_classic",
        "pivot_r1",
        "pivot_s1",
        "pivot_r2",
        "pivot_s2",
        "distance_to_pivot_pct",
        # --- Batch 3: Candle patterns ---
        "pattern_doji",
        "pattern_hammer",
        "pattern_engulfing",
        "pattern_morning_evening_star",
        "pattern_three_soldiers_crows",
        "pattern_pin_bar",
        "pattern_inside_bar",
        "pattern_outside_bar",
        # --- Batch 3: Adaptive / Ehlers ---
        "ehlers_fisher_transform_13",
        "ehlers_instantaneous_trendline",
        "ehlers_cyber_cycle",
        "ehlers_dominant_cycle_period",
        "adaptive_rsi_14",
        "fractal_dimension_20",
        "hurst_exponent_20",
        "entropy_20",
        # --- Batch 3: Microstructure stats ---
        "realized_volatility_10",
        "yang_zhang_volatility_20",
        "intraday_intensity_20",
        "volume_weighted_rsi_14",
        "relative_volume_5",
        "tick_intensity",
        "amihud_illiquidity_20",
        "kyle_lambda_20",
        "return_dispersion_20",
        "overnight_gap_pct",
    ]

    def calculate(self, merged_klines: pd.DataFrame) -> pd.DataFrame:
        if merged_klines.empty:
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)

        frame = merged_klines.copy()
        frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True, errors="coerce")
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["symbol", "timeframe", "open_time", "open", "high", "low", "close", "volume"])
        frame = frame.sort_values(["symbol", "timeframe", "open_time"])

        result_frames: list[pd.DataFrame] = []
        for (_, _), group in frame.groupby(["symbol", "timeframe"], sort=True):
            result_frames.append(self._calculate_group(group))

        if not result_frames:
            return pd.DataFrame(columns=self.OUTPUT_COLUMNS)

        result = pd.concat(result_frames, ignore_index=True)
        result = result[self.OUTPUT_COLUMNS]
        logger.info(f"已计算 {len(result)} 条技术指标")
        return result

    def _calculate_group(self, group: pd.DataFrame) -> pd.DataFrame:
        frame = group.copy().sort_values("open_time").reset_index(drop=True)
        base = frame[["symbol", "timeframe", "open_time", "close", "volume"]].copy()

        open_price = frame["open"]
        close = frame["close"]
        high = frame["high"]
        low = frame["low"]
        volume = frame["volume"]
        previous_close = close.shift(1)
        typical_price = (high + low + close) / 3
        median_price = (high + low) / 2
        candle_range = high - low
        candle_body = close - open_price
        candle_body_abs = candle_body.abs()
        candle_high_reference = pd.concat([open_price, close], axis=1).max(axis=1)
        candle_low_reference = pd.concat([open_price, close], axis=1).min(axis=1)
        upper_shadow = high - candle_high_reference
        lower_shadow = candle_low_reference - low
        volume_sum_20 = volume.rolling(20).sum()
        volume_mean_20 = volume.rolling(20).mean()
        volume_std_20 = volume.rolling(20).std(ddof=0)

        sma_5 = close.rolling(5).mean()
        sma_10 = close.rolling(10).mean()
        sma_20 = close.rolling(20).mean()
        sma_60 = close.rolling(60).mean()
        sma_120 = close.rolling(120).mean()

        ema_7 = close.ewm(span=7, adjust=False).mean()
        ema_20 = close.ewm(span=20, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()
        ema_100 = close.ewm(span=100, adjust=False).mean()
        ema_13 = close.ewm(span=13, adjust=False).mean()
        ema_20_of_ema_20 = ema_20.ewm(span=20, adjust=False).mean()
        ema_20_of_ema_20_of_ema_20 = ema_20_of_ema_20.ewm(span=20, adjust=False).mean()
        dema_20 = (2 * ema_20) - ema_20_of_ema_20
        tema_20 = (3 * ema_20) - (3 * ema_20_of_ema_20) + ema_20_of_ema_20_of_ema_20
        zlema_lag = 9
        zero_lag_input = close + (close - close.shift(zlema_lag))
        zlema_20 = zero_lag_input.ewm(span=20, adjust=False).mean()
        hma_21 = self._weighted_moving_average(
            (2 * self._weighted_moving_average(close, 10)) -
            self._weighted_moving_average(close, 21),
            period=4,
        )
        price_to_sma_20 = (close / sma_20.replace(0, np.nan)) - 1
        price_to_sma_60 = (close / sma_60.replace(0, np.nan)) - 1
        price_to_ema_20 = (close / ema_20.replace(0, np.nan)) - 1
        price_to_ema_50 = (close / ema_50.replace(0, np.nan)) - 1

        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal
        macd_hist_zscore_20 = (
            (macd_hist - macd_hist.rolling(20).mean()) /
            macd_hist.rolling(20).std(ddof=0).replace(0, np.nan)
        )
        ppo_line = ((ema_fast - ema_slow) / ema_slow.replace(0, np.nan)) * 100
        ppo_signal = ppo_line.ewm(span=9, adjust=False).mean()
        ppo_hist = ppo_line - ppo_signal
        stc_10_23_50 = self._schaff_trend_cycle(
            close,
            cycle_period=10,
            fast_period=23,
            slow_period=50,
        )

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_14 = 100 - (100 / (1 + rs))
        avg_gain_28 = gain.ewm(alpha=1 / 28, adjust=False, min_periods=28).mean()
        avg_loss_28 = loss.ewm(alpha=1 / 28, adjust=False, min_periods=28).mean()
        rs_28 = avg_gain_28 / avg_loss_28.replace(0, np.nan)
        rsi_28 = 100 - (100 / (1 + rs_28))
        momentum_5 = close.diff(5)
        rmi_gain = momentum_5.clip(lower=0)
        rmi_loss = -momentum_5.clip(upper=0)
        rmi_avg_gain = rmi_gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rmi_avg_loss = rmi_loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rmi_rs = rmi_avg_gain / rmi_avg_loss.replace(0, np.nan)
        rmi_14_5 = 100 - (100 / (1 + rmi_rs))
        rsi_min_14 = rsi_14.rolling(14).min()
        rsi_max_14 = rsi_14.rolling(14).max()
        stoch_rsi = ((rsi_14 - rsi_min_14) / (rsi_max_14 - rsi_min_14).replace(0, np.nan)) * 100
        stoch_rsi_k_14 = stoch_rsi.rolling(3).mean()
        stoch_rsi_d_14 = stoch_rsi_k_14.rolling(3).mean()

        roc_12 = close.pct_change(12, fill_method=None) * 100
        momentum_10 = close - close.shift(10)
        cfo_20 = close.rolling(20).apply(self._chande_forecast_oscillator, raw=True)
        efficiency_ratio_10 = close.diff(10).abs() / close.diff().abs().rolling(10).sum().replace(0, np.nan)
        triple_ema = close.ewm(span=30, adjust=False).mean()
        triple_ema = triple_ema.ewm(span=30, adjust=False).mean()
        triple_ema = triple_ema.ewm(span=30, adjust=False).mean()
        trix_30 = triple_ema.pct_change(fill_method=None) * 100
        dpo_20 = close.shift(11) - close.rolling(20).mean()
        roc_11 = close.pct_change(11, fill_method=None) * 100
        roc_14 = close.pct_change(14, fill_method=None) * 100
        coppock_curve_11_14_10 = self._weighted_moving_average(roc_11 + roc_14, period=10)
        coppock_signal_10 = coppock_curve_11_14_10.rolling(10).mean()
        kst_roc_10 = close.pct_change(10, fill_method=None) * 100
        kst_roc_15 = close.pct_change(15, fill_method=None) * 100
        kst_roc_20 = close.pct_change(20, fill_method=None) * 100
        kst_roc_30 = close.pct_change(30, fill_method=None) * 100
        kst_line = (
            kst_roc_10.rolling(10).mean() +
            (2 * kst_roc_15.rolling(10).mean()) +
            (3 * kst_roc_20.rolling(10).mean()) +
            (4 * kst_roc_30.rolling(15).mean())
        )
        kst_signal = kst_line.rolling(9).mean()
        awesome_oscillator_5_34 = median_price.rolling(5).mean() - median_price.rolling(34).mean()
        accelerator_oscillator_5_34 = awesome_oscillator_5_34 - awesome_oscillator_5_34.rolling(5).mean()
        pfe_straight_line = np.sqrt(close.diff(10).pow(2) + (10 ** 2))
        pfe_path = np.sqrt(close.diff().pow(2) + 1).rolling(10).sum()
        pfe_10 = np.sign(close.diff(10)) * 100 * pfe_straight_line / pfe_path.replace(0, np.nan)
        qstick_10 = candle_body.rolling(10).mean()
        ema_25_delta = delta.ewm(span=25, adjust=False).mean()
        ema_13_ema_25_delta = ema_25_delta.ewm(span=13, adjust=False).mean()
        ema_25_abs_delta = delta.abs().ewm(span=25, adjust=False).mean()
        ema_13_ema_25_abs_delta = ema_25_abs_delta.ewm(span=13, adjust=False).mean()
        tsi_line = (ema_13_ema_25_delta / ema_13_ema_25_abs_delta.replace(0, np.nan)) * 100
        tsi_signal = tsi_line.ewm(span=7, adjust=False).mean()

        lowest_low_9 = low.rolling(9).min()
        highest_high_9 = high.rolling(9).max()
        rsv = ((close - lowest_low_9) / (highest_high_9 - lowest_low_9).replace(0, np.nan)) * 100
        stoch_k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
        stoch_d = stoch_k.ewm(alpha=1 / 3, adjust=False).mean()
        stoch_j = 3 * stoch_k - 2 * stoch_d

        highest_high_14 = high.rolling(14).max()
        lowest_low_14 = low.rolling(14).min()
        midpoint_14 = (highest_high_14 + lowest_low_14) / 2
        high_low_span_14 = highest_high_14 - lowest_low_14
        smi_distance = close - midpoint_14
        smi_distance_smoothed = smi_distance.ewm(span=3, adjust=False).mean().ewm(span=3, adjust=False).mean()
        smi_span_smoothed = high_low_span_14.ewm(span=3, adjust=False).mean().ewm(span=3, adjust=False).mean()
        stochastic_momentum_index_14_3 = (
            100 * smi_distance_smoothed / (0.5 * smi_span_smoothed).replace(0, np.nan)
        )
        stochastic_momentum_signal_14_3 = stochastic_momentum_index_14_3.ewm(
            span=3,
            adjust=False,
        ).mean()

        true_range = pd.concat([
            candle_range,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ], axis=1).max(axis=1)
        true_range_pct = true_range / previous_close.replace(0, np.nan)
        atr_14 = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        atr_10 = true_range.ewm(alpha=1 / 10, adjust=False, min_periods=10).mean()
        atr_pct_14 = atr_14 / close.replace(0, np.nan)
        tr_sum_14 = true_range.rolling(14).sum()

        log_return_1 = np.log(close / previous_close.replace(0, np.nan))
        log_high_low = np.log(high / low.replace(0, np.nan))
        log_close_open = np.log(close / open_price.replace(0, np.nan))
        parkinson_volatility_20 = (
            (log_high_low.pow(2) / (4 * np.log(2))).rolling(20).mean()
        ).clip(lower=0).pow(0.5)
        garman_klass_component = 0.5 * log_high_low.pow(2) - (((2 * np.log(2)) - 1) * log_close_open.pow(2))
        garman_klass_volatility_20 = garman_klass_component.rolling(20).mean().clip(lower=0).pow(0.5)
        rogers_satchell_component = (
            np.log(high / close.replace(0, np.nan)) * np.log(high / open_price.replace(0, np.nan)) +
            np.log(low / close.replace(0, np.nan)) * np.log(low / open_price.replace(0, np.nan))
        )
        rogers_satchell_volatility_20 = rogers_satchell_component.rolling(20).mean().clip(lower=0).pow(0.5)
        historical_volatility_20 = log_return_1.rolling(20).std(ddof=0) * np.sqrt(20)
        range_ema_10 = candle_range.ewm(span=10, adjust=False, min_periods=10).mean()
        chaikin_volatility_10 = range_ema_10.pct_change(10, fill_method=None) * 100
        up_volatility = delta.clip(lower=0).rolling(14).std(ddof=0)
        down_volatility = (-delta.clip(upper=0)).rolling(14).std(ddof=0)
        relative_volatility_index_14 = 100 * up_volatility / (up_volatility + down_volatility).replace(0, np.nan)
        high_low_range_14 = (high.rolling(14).max() - low.rolling(14).min()).replace(0, np.nan)
        normalized_range_14 = high_low_range_14 / close.rolling(14).mean().replace(0, np.nan)
        choppiness_index_14 = 100 * np.log10(tr_sum_14 / high_low_range_14) / np.log10(14)

        bb_middle = sma_20
        rolling_std = close.rolling(20).std(ddof=0)
        bb_upper = bb_middle + 2 * rolling_std
        bb_lower = bb_middle - 2 * rolling_std
        bb_width = (bb_upper - bb_lower) / bb_middle.replace(0, np.nan)
        bb_percent_b = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

        keltner_middle_20 = ema_20
        keltner_upper_20 = ema_20 + 2 * atr_14
        keltner_lower_20 = ema_20 - 2 * atr_14
        keltner_width_20 = (keltner_upper_20 - keltner_lower_20) / keltner_middle_20.replace(0, np.nan)
        squeeze_valid = (
            bb_lower.notna() &
            bb_upper.notna() &
            keltner_lower_20.notna() &
            keltner_upper_20.notna()
        )
        squeeze_on_mask = (bb_lower > keltner_lower_20) & (bb_upper < keltner_upper_20)
        squeeze_off_mask = (bb_lower < keltner_lower_20) & (bb_upper > keltner_upper_20)
        squeeze_on_20 = pd.Series(np.where(squeeze_valid, squeeze_on_mask.astype(float), np.nan), index=frame.index)
        squeeze_off_20 = pd.Series(np.where(squeeze_valid, squeeze_off_mask.astype(float), np.nan), index=frame.index)

        donchian_high_20 = high.rolling(20).max()
        donchian_low_20 = low.rolling(20).min()
        donchian_mid_20 = (donchian_high_20 + donchian_low_20) / 2
        donchian_range_20 = donchian_high_20 - donchian_low_20
        donchian_width_20 = donchian_range_20 / donchian_mid_20.replace(0, np.nan)
        donchian_position_20 = (close - donchian_low_20) / donchian_range_20.replace(0, np.nan)
        vhf_28 = (
            (close.rolling(28).max() - close.rolling(28).min()) /
            close.diff().abs().rolling(28).sum().replace(0, np.nan)
        )

        ema_20_slope_5 = ema_20.pct_change(5, fill_method=None) * 100
        sma_20_slope_5 = sma_20.pct_change(5, fill_method=None) * 100
        supertrend_10_3, supertrend_direction_10_3 = self._supertrend(high, low, close, atr_10, multiplier=3.0)
        psar, psar_trend = self._parabolic_sar(high, low, close)
        up_move = high.diff()
        down_move = low.shift(1) - low
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        plus_dm_smoothed = plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        minus_dm_smoothed = minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        plus_di_14 = 100 * plus_dm_smoothed / atr_14.replace(0, np.nan)
        minus_di_14 = 100 * minus_dm_smoothed / atr_14.replace(0, np.nan)
        dx = ((plus_di_14 - minus_di_14).abs() / (plus_di_14 + minus_di_14).replace(0, np.nan)) * 100
        adx_14 = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        adxr_14 = (adx_14 + adx_14.shift(14)) / 2
        dmi_oscillator_14 = plus_di_14 - minus_di_14
        vortex_plus_move = (high - low.shift(1)).abs()
        vortex_minus_move = (low - high.shift(1)).abs()
        vortex_plus_14 = vortex_plus_move.rolling(14).sum() / tr_sum_14.replace(0, np.nan)
        vortex_minus_14 = vortex_minus_move.rolling(14).sum() / tr_sum_14.replace(0, np.nan)
        linear_reg_slope_raw_20 = close.rolling(20).apply(self._linear_regression_slope, raw=True)
        linear_reg_slope_20 = (linear_reg_slope_raw_20 / close.rolling(20).mean().replace(0, np.nan)) * 100
        linear_reg_r2_20 = close.rolling(20).apply(self._linear_regression_r2, raw=True)
        regression_distance_20 = close.rolling(20).apply(self._linear_regression_last_distance, raw=True)

        ichimoku_tenkan_9 = (high.rolling(9).max() + low.rolling(9).min()) / 2
        ichimoku_kijun_26 = (high.rolling(26).max() + low.rolling(26).min()) / 2
        ichimoku_senkou_a = (ichimoku_tenkan_9 + ichimoku_kijun_26) / 2
        ichimoku_senkou_b_52 = (high.rolling(52).max() + low.rolling(52).min()) / 2
        cloud_top = pd.concat([ichimoku_senkou_a, ichimoku_senkou_b_52], axis=1).max(axis=1)
        cloud_bottom = pd.concat([ichimoku_senkou_a, ichimoku_senkou_b_52], axis=1).min(axis=1)
        cloud_range = cloud_top - cloud_bottom
        ichimoku_cloud_width = cloud_range / close.replace(0, np.nan)
        ichimoku_cloud_position = (close - cloud_bottom) / cloud_range.replace(0, np.nan)
        price_to_kijun_26 = (close / ichimoku_kijun_26.replace(0, np.nan)) - 1
        aroon_up_25 = high.rolling(25).apply(self._aroon_up, raw=True)
        aroon_down_25 = low.rolling(25).apply(self._aroon_down, raw=True)
        aroon_osc_25 = aroon_up_25 - aroon_down_25
        kama_10_2_30 = self._kama(close, er_period=10, fast_period=2, slow_period=30)
        bull_power_13 = high - ema_13
        bear_power_13 = low - ema_13
        mass_index_25 = self._mass_index(high, low, ema_period=9, sum_period=25)
        fisher_transform_9, fisher_trigger_9 = self._fisher_transform(median_price, period=9)

        buying_pressure = close - pd.concat([low, previous_close], axis=1).min(axis=1)
        true_low = pd.concat([low, previous_close], axis=1).min(axis=1)
        true_high = pd.concat([high, previous_close], axis=1).max(axis=1)
        ultimate_tr = true_high - true_low
        avg7 = buying_pressure.rolling(7).sum() / ultimate_tr.rolling(7).sum().replace(0, np.nan)
        avg14 = buying_pressure.rolling(14).sum() / ultimate_tr.rolling(14).sum().replace(0, np.nan)
        avg28 = buying_pressure.rolling(28).sum() / ultimate_tr.rolling(28).sum().replace(0, np.nan)
        ultimate_osc = 100 * ((4 * avg7) + (2 * avg14) + avg28) / 7

        tp_sma_20 = typical_price.rolling(20).mean()
        mean_deviation = typical_price.rolling(20).apply(
            lambda values: (values - values.mean()).abs().mean(),
            raw=False,
        )
        cci_20 = (typical_price - tp_sma_20) / (0.015 * mean_deviation.replace(0, np.nan))
        raw_money_flow = typical_price * volume
        tp_delta = typical_price.diff()
        positive_flow = raw_money_flow.where(tp_delta > 0, 0.0)
        negative_flow = raw_money_flow.where(tp_delta < 0, 0.0).abs()
        positive_sum = positive_flow.rolling(14).sum()
        negative_sum = negative_flow.rolling(14).sum()
        money_ratio = positive_sum / negative_sum.replace(0, np.nan)
        mfi_14 = 100 - (100 / (1 + money_ratio))
        demax = (high - high.shift(1)).clip(lower=0)
        demin = (low.shift(1) - low).clip(lower=0)
        demax_sum_14 = demax.rolling(14).sum()
        demin_sum_14 = demin.rolling(14).sum()
        demarker_14 = demax_sum_14 / (demax_sum_14 + demin_sum_14).replace(0, np.nan)
        williams_r_14 = ((highest_high_14 - close) / (highest_high_14 - lowest_low_14).replace(0, np.nan)) * -100

        direction = pd.Series(np.sign(close.diff()), index=close.index)
        obv = (direction.fillna(0) * volume).cumsum()
        obv_slope_20 = obv.rolling(20).apply(self._linear_regression_slope, raw=True) / volume_mean_20.replace(0, np.nan)
        price_volume_trend = (close.pct_change(fill_method=None).fillna(0) * volume).cumsum()
        nvi, pvi = self._positive_negative_volume_index(close, volume)
        kvo_line, kvo_signal = self._klinger_volume_oscillator(high, low, close, volume)
        balance_of_power = candle_body / candle_range.replace(0, np.nan)
        volume_ema_fast = volume.ewm(span=12, adjust=False).mean()
        volume_ema_slow = volume.ewm(span=26, adjust=False).mean()
        pvo_line = ((volume_ema_fast - volume_ema_slow) / volume_ema_slow.replace(0, np.nan)) * 100
        pvo_signal = pvo_line.ewm(span=9, adjust=False).mean()
        pvo_hist = pvo_line - pvo_signal
        volume_oscillator_5_20 = (
            (volume.rolling(5).mean() - volume.rolling(20).mean()) /
            volume.rolling(20).mean().replace(0, np.nan)
        ) * 100
        vwma_20 = (close * volume).rolling(20).sum() / volume_sum_20.replace(0, np.nan)
        price_to_vwma_20 = (close / vwma_20.replace(0, np.nan)) - 1
        rolling_vwap_20 = (typical_price * volume).rolling(20).sum() / volume_sum_20.replace(0, np.nan)
        rolling_vwap_deviation_20 = (close - rolling_vwap_20) / rolling_vwap_20.replace(0, np.nan)
        money_flow_multiplier = ((close - low) - (high - close)) / candle_range.replace(0, np.nan)
        money_flow_volume = money_flow_multiplier * volume
        cmf_20 = money_flow_volume.rolling(20).sum() / volume_sum_20.replace(0, np.nan)
        adl = money_flow_volume.cumsum()
        adl_slope_20 = adl.rolling(20).apply(self._linear_regression_slope, raw=True) / volume_mean_20.replace(0, np.nan)
        chaikin_oscillator = adl.ewm(span=3, adjust=False).mean() - adl.ewm(span=10, adjust=False).mean()
        midpoint_move = ((high + low) / 2).diff()
        eom_raw = midpoint_move * candle_range / volume.replace(0, np.nan)
        ease_of_movement_14 = eom_raw.rolling(14).mean()
        force_index_13 = (delta * volume).ewm(span=13, adjust=False).mean()

        rvi_numerator = (
            candle_body +
            (2 * candle_body.shift(1)) +
            (2 * candle_body.shift(2)) +
            candle_body.shift(3)
        ) / 6
        rvi_denominator = (
            candle_range +
            (2 * candle_range.shift(1)) +
            (2 * candle_range.shift(2)) +
            candle_range.shift(3)
        ) / 6
        rvi_10 = rvi_numerator.rolling(10).mean() / rvi_denominator.rolling(10).mean().replace(0, np.nan)
        rvi_signal_4 = (rvi_10 + (2 * rvi_10.shift(1)) + (2 * rvi_10.shift(2)) + rvi_10.shift(3)) / 6

        return_1 = close.pct_change(1, fill_method=None)
        return_5 = close.pct_change(5, fill_method=None)
        return_20 = close.pct_change(20, fill_method=None)
        volatility_20 = return_1.rolling(20).std(ddof=0)
        downside_returns = return_1.where(return_1 < 0, 0.0)
        upside_returns = return_1.where(return_1 > 0, 0.0)
        downside_deviation_20 = downside_returns.pow(2).rolling(20).mean().pow(0.5)
        upside_deviation_20 = upside_returns.pow(2).rolling(20).mean().pow(0.5)
        mean_return_20 = return_1.rolling(20).mean()
        sharpe_like_20 = mean_return_20 / volatility_20.replace(0, np.nan)
        sortino_like_20 = mean_return_20 / downside_deviation_20.replace(0, np.nan)
        return_skew_20 = return_1.rolling(20).skew()
        return_kurtosis_20 = return_1.rolling(20).kurt()
        median_return_20 = return_1.rolling(20).median()
        mad_return_20 = return_1.rolling(20).apply(self._median_absolute_deviation, raw=True)
        return_iqr_20 = return_1.rolling(20).apply(self._interquartile_range, raw=True)
        tail_ratio_20 = return_1.rolling(20).apply(self._tail_ratio, raw=True)
        positive_return_ratio_20 = return_1.gt(0).rolling(20).mean()
        return_autocorr_20 = return_1.rolling(20).apply(self._lag1_autocorrelation, raw=True)
        gain_to_pain_ratio_20 = return_1.rolling(20).apply(self._gain_to_pain_ratio, raw=True)
        volume_ratio_20 = volume / volume_mean_20.replace(0, np.nan)
        volume_zscore_20 = (volume - volume_mean_20) / volume_std_20.replace(0, np.nan)
        volume_change_1 = volume.pct_change(fill_method=None)
        volume_autocorr_20 = volume_change_1.rolling(20).apply(self._lag1_autocorrelation, raw=True)
        volume_price_correlation_20 = return_1.rolling(20).corr(volume_change_1)
        price_zscore_20 = (close - bb_middle) / rolling_std.replace(0, np.nan)
        price_percent_rank_20 = close.rolling(20).apply(self._percent_rank, raw=True)
        volume_percent_rank_20 = volume.rolling(20).apply(self._percent_rank, raw=True)
        atr_percent_rank_20 = atr_14.rolling(20).apply(self._percent_rank, raw=True)
        candle_range_pct = candle_range / close.replace(0, np.nan)
        range_percent_rank_20 = candle_range_pct.rolling(20).apply(self._percent_rank, raw=True)
        rolling_max_20 = close.rolling(20).max()
        rolling_drawdown_20 = (close / rolling_max_20.replace(0, np.nan)) - 1
        max_drawdown_20 = rolling_drawdown_20.rolling(20).min().abs()
        calmar_like_20 = return_20 / max_drawdown_20.replace(0, np.nan)
        gain_sum_14 = gain.rolling(14).sum()
        loss_sum_14 = loss.rolling(14).sum()
        cmo_14 = ((gain_sum_14 - loss_sum_14) / (gain_sum_14 + loss_sum_14).replace(0, np.nan)) * 100
        rolling_max_14 = close.rolling(14).max()
        drawdown_pct_14 = ((close / rolling_max_14.replace(0, np.nan)) - 1) * 100
        ulcer_index_14 = drawdown_pct_14.pow(2).rolling(14).mean().pow(0.5)

        candle_body_pct = candle_body / open_price.replace(0, np.nan)
        upper_shadow_pct = upper_shadow / candle_range.replace(0, np.nan)
        lower_shadow_pct = lower_shadow / candle_range.replace(0, np.nan)
        body_to_range_ratio = candle_body_abs / candle_range.replace(0, np.nan)
        close_location_value = ((close - low) - (high - close)) / candle_range.replace(0, np.nan)
        intrabar_trend_efficiency = candle_body / true_range.replace(0, np.nan)

        trend_frame = pd.DataFrame({
            "sma_5": sma_5,
            "sma_10": sma_10,
            "sma_20": sma_20,
            "sma_60": sma_60,
            "sma_120": sma_120,
            "ema_7": ema_7,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "ema_100": ema_100,
            "dema_20": dema_20,
            "tema_20": tema_20,
            "hma_21": hma_21,
            "zlema_20": zlema_20,
            "macd_line": macd_line,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "ppo_line": ppo_line,
            "ppo_signal": ppo_signal,
            "ppo_hist": ppo_hist,
            "ichimoku_tenkan_9": ichimoku_tenkan_9,
            "ichimoku_kijun_26": ichimoku_kijun_26,
            "ichimoku_senkou_a": ichimoku_senkou_a,
            "ichimoku_senkou_b_52": ichimoku_senkou_b_52,
            "ichimoku_cloud_width": ichimoku_cloud_width,
            "ichimoku_cloud_position": ichimoku_cloud_position,
            "price_to_kijun_26": price_to_kijun_26,
            "price_to_sma_20": price_to_sma_20,
            "price_to_sma_60": price_to_sma_60,
            "price_to_ema_20": price_to_ema_20,
            "price_to_ema_50": price_to_ema_50,
            "macd_hist_zscore_20": macd_hist_zscore_20,
            "linear_reg_slope_20": linear_reg_slope_20,
            "linear_reg_r2_20": linear_reg_r2_20,
            "regression_distance_20": regression_distance_20,
            "ema_20_slope_5": ema_20_slope_5,
            "sma_20_slope_5": sma_20_slope_5,
            "supertrend_10_3": supertrend_10_3,
            "supertrend_direction_10_3": supertrend_direction_10_3,
            "psar": psar,
            "psar_trend": psar_trend,
            "vortex_plus_14": vortex_plus_14,
            "vortex_minus_14": vortex_minus_14,
            "kama_10_2_30": kama_10_2_30,
            "efficiency_ratio_10": efficiency_ratio_10,
            "aroon_up_25": aroon_up_25,
            "aroon_down_25": aroon_down_25,
            "aroon_osc_25": aroon_osc_25,
            "plus_di_14": plus_di_14,
            "minus_di_14": minus_di_14,
            "adx_14": adx_14,
            "adxr_14": adxr_14,
            "dmi_oscillator_14": dmi_oscillator_14,
            "vhf_28": vhf_28,
            "bull_power_13": bull_power_13,
            "bear_power_13": bear_power_13,
        }, index=frame.index)

        momentum_frame = pd.DataFrame({
            "rsi_14": rsi_14,
            "rsi_28": rsi_28,
            "stoch_rsi_k_14": stoch_rsi_k_14,
            "stoch_rsi_d_14": stoch_rsi_d_14,
            "stoch_k": stoch_k,
            "stoch_d": stoch_d,
            "stoch_j": stoch_j,
            "stochastic_momentum_index_14_3": stochastic_momentum_index_14_3,
            "stochastic_momentum_signal_14_3": stochastic_momentum_signal_14_3,
            "roc_12": roc_12,
            "momentum_10": momentum_10,
            "rmi_14_5": rmi_14_5,
            "cfo_20": cfo_20,
            "awesome_oscillator_5_34": awesome_oscillator_5_34,
            "accelerator_oscillator_5_34": accelerator_oscillator_5_34,
            "pfe_10": pfe_10,
            "cci_20": cci_20,
            "mfi_14": mfi_14,
            "williams_r_14": williams_r_14,
            "tsi_line": tsi_line,
            "tsi_signal": tsi_signal,
            "stc_10_23_50": stc_10_23_50,
            "ultimate_osc": ultimate_osc,
            "trix_30": trix_30,
            "dpo_20": dpo_20,
            "fisher_transform_9": fisher_transform_9,
            "fisher_trigger_9": fisher_trigger_9,
            "coppock_curve_11_14_10": coppock_curve_11_14_10,
            "coppock_signal_10": coppock_signal_10,
            "kst_line": kst_line,
            "kst_signal": kst_signal,
            "qstick_10": qstick_10,
            "demarker_14": demarker_14,
            "rvi_10": rvi_10,
            "rvi_signal_4": rvi_signal_4,
            "cmo_14": cmo_14,
        }, index=frame.index)

        volatility_frame = pd.DataFrame({
            "bb_middle": bb_middle,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
            "bb_percent_b": bb_percent_b,
            "atr_14": atr_14,
            "true_range_pct": true_range_pct,
            "normalized_range_14": normalized_range_14,
            "historical_volatility_20": historical_volatility_20,
            "chaikin_volatility_10": chaikin_volatility_10,
            "atr_pct_14": atr_pct_14,
            "parkinson_volatility_20": parkinson_volatility_20,
            "garman_klass_volatility_20": garman_klass_volatility_20,
            "rogers_satchell_volatility_20": rogers_satchell_volatility_20,
            "relative_volatility_index_14": relative_volatility_index_14,
            "keltner_middle_20": keltner_middle_20,
            "keltner_upper_20": keltner_upper_20,
            "keltner_lower_20": keltner_lower_20,
            "keltner_width_20": keltner_width_20,
            "donchian_high_20": donchian_high_20,
            "donchian_low_20": donchian_low_20,
            "donchian_mid_20": donchian_mid_20,
            "donchian_width_20": donchian_width_20,
            "donchian_position_20": donchian_position_20,
            "choppiness_index_14": choppiness_index_14,
            "squeeze_on_20": squeeze_on_20,
            "squeeze_off_20": squeeze_off_20,
            "mass_index_25": mass_index_25,
            "ulcer_index_14": ulcer_index_14,
            "rolling_drawdown_20": rolling_drawdown_20,
        }, index=frame.index)

        volume_frame = pd.DataFrame({
            "obv": obv,
            "obv_slope_20": obv_slope_20,
            "adl": adl,
            "adl_slope_20": adl_slope_20,
            "chaikin_oscillator": chaikin_oscillator,
            "vwma_20": vwma_20,
            "price_to_vwma_20": price_to_vwma_20,
            "rolling_vwap_20": rolling_vwap_20,
            "rolling_vwap_deviation_20": rolling_vwap_deviation_20,
            "cmf_20": cmf_20,
            "price_volume_trend": price_volume_trend,
            "nvi": nvi,
            "pvi": pvi,
            "kvo_line": kvo_line,
            "kvo_signal": kvo_signal,
            "ease_of_movement_14": ease_of_movement_14,
            "volume_oscillator_5_20": volume_oscillator_5_20,
            "volume_price_correlation_20": volume_price_correlation_20,
            "pvo_line": pvo_line,
            "pvo_signal": pvo_signal,
            "pvo_hist": pvo_hist,
            "force_index_13": force_index_13,
            "volume_ratio_20": volume_ratio_20,
        }, index=frame.index)

        structure_frame = pd.DataFrame({
            "balance_of_power": balance_of_power,
            "candle_body_pct": candle_body_pct,
            "upper_shadow_pct": upper_shadow_pct,
            "lower_shadow_pct": lower_shadow_pct,
            "body_to_range_ratio": body_to_range_ratio,
            "close_location_value": close_location_value,
            "intrabar_trend_efficiency": intrabar_trend_efficiency,
        }, index=frame.index)

        state_frame = pd.DataFrame({
            "return_1": return_1,
            "return_5": return_5,
            "return_20": return_20,
            "volatility_20": volatility_20,
            "price_zscore_20": price_zscore_20,
            "price_percent_rank_20": price_percent_rank_20,
            "volume_percent_rank_20": volume_percent_rank_20,
            "atr_percent_rank_20": atr_percent_rank_20,
            "range_percent_rank_20": range_percent_rank_20,
            "volume_zscore_20": volume_zscore_20,
        }, index=frame.index)

        risk_frame = pd.DataFrame({
            "downside_deviation_20": downside_deviation_20,
            "upside_deviation_20": upside_deviation_20,
            "sharpe_like_20": sharpe_like_20,
            "sortino_like_20": sortino_like_20,
            "calmar_like_20": calmar_like_20,
            "gain_to_pain_ratio_20": gain_to_pain_ratio_20,
            "median_return_20": median_return_20,
            "mad_return_20": mad_return_20,
            "return_iqr_20": return_iqr_20,
            "tail_ratio_20": tail_ratio_20,
            "positive_return_ratio_20": positive_return_ratio_20,
            "return_autocorr_20": return_autocorr_20,
            "volume_autocorr_20": volume_autocorr_20,
            "return_skew_20": return_skew_20,
            "return_kurtosis_20": return_kurtosis_20,
        }, index=frame.index)

        # === Batch 3: Crossover signals ===
        ema_cross_7_20 = pd.Series(np.where(
            (ema_7 > ema_20) & (ema_7.shift(1) <= ema_20.shift(1)), 1.0,
            np.where((ema_7 < ema_20) & (ema_7.shift(1) >= ema_20.shift(1)), -1.0, 0.0)
        ), index=frame.index)
        ema_cross_20_50 = pd.Series(np.where(
            (ema_20 > ema_50) & (ema_20.shift(1) <= ema_50.shift(1)), 1.0,
            np.where((ema_20 < ema_50) & (ema_20.shift(1) >= ema_50.shift(1)), -1.0, 0.0)
        ), index=frame.index)
        sma_cross_10_60 = pd.Series(np.where(
            (sma_10 > sma_60) & (sma_10.shift(1) <= sma_60.shift(1)), 1.0,
            np.where((sma_10 < sma_60) & (sma_10.shift(1) >= sma_60.shift(1)), -1.0, 0.0)
        ), index=frame.index)
        macd_cross_signal_col = pd.Series(np.where(
            (macd_line > macd_signal) & (macd_line.shift(1) <= macd_signal.shift(1)), 1.0,
            np.where((macd_line < macd_signal) & (macd_line.shift(1) >= macd_signal.shift(1)), -1.0, 0.0)
        ), index=frame.index)
        price_above_ema_count = (
            (close > ema_7).astype(float) +
            (close > ema_20).astype(float) +
            (close > ema_50).astype(float) +
            (close > ema_100).astype(float)
        )
        # MA alignment: +1 if EMA7>EMA20>EMA50>EMA100, -1 if reversed
        ma_alignment_score = (
            np.sign(ema_7 - ema_20) +
            np.sign(ema_20 - ema_50) +
            np.sign(ema_50 - ema_100)
        ) / 3.0
        # Ichimoku signal: price vs cloud + tenkan vs kijun
        ichi_price_signal = pd.Series(np.where(
            close > cloud_top, 1.0, np.where(close < cloud_bottom, -1.0, 0.0)
        ), index=frame.index)
        ichi_tk_signal = pd.Series(np.where(
            ichimoku_tenkan_9 > ichimoku_kijun_26, 1.0,
            np.where(ichimoku_tenkan_9 < ichimoku_kijun_26, -1.0, 0.0)
        ), index=frame.index)
        ichimoku_signal_col = ichi_price_signal + ichi_tk_signal
        trend_consistency_20 = (close > ema_20).astype(float).rolling(20).mean()

        crossover_frame = pd.DataFrame({
            "ema_cross_7_20": ema_cross_7_20,
            "ema_cross_20_50": ema_cross_20_50,
            "sma_cross_10_60": sma_cross_10_60,
            "macd_cross_signal": macd_cross_signal_col,
            "price_above_ema_count": price_above_ema_count,
            "ma_alignment_score": ma_alignment_score,
            "ichimoku_signal": ichimoku_signal_col,
            "trend_consistency_20": trend_consistency_20,
        }, index=frame.index)

        # === Batch 3: Pivot points (using previous bar H/L/C) ===
        prev_high = high.shift(1)
        prev_low = low.shift(1)
        prev_close = close.shift(1)
        pivot_classic = (prev_high + prev_low + prev_close) / 3
        pivot_r1 = 2 * pivot_classic - prev_low
        pivot_s1 = 2 * pivot_classic - prev_high
        pivot_r2 = pivot_classic + (prev_high - prev_low)
        pivot_s2 = pivot_classic - (prev_high - prev_low)
        distance_to_pivot_pct = (close - pivot_classic) / pivot_classic.replace(0, np.nan)

        pivot_frame = pd.DataFrame({
            "pivot_classic": pivot_classic,
            "pivot_r1": pivot_r1,
            "pivot_s1": pivot_s1,
            "pivot_r2": pivot_r2,
            "pivot_s2": pivot_s2,
            "distance_to_pivot_pct": distance_to_pivot_pct,
        }, index=frame.index)

        # === Batch 3: Candle patterns ===
        pattern_doji = (candle_body_abs / candle_range.replace(0, np.nan) < 0.1).astype(float)
        # Hammer: small body at top, long lower shadow > 2x body
        pattern_hammer = (
            (lower_shadow > 2 * candle_body_abs) &
            (upper_shadow < candle_body_abs) &
            (candle_range > 0)
        ).astype(float)
        # Engulfing
        prev_body = candle_body.shift(1)
        pattern_engulfing = pd.Series(np.where(
            (candle_body > 0) & (prev_body < 0) & (candle_body_abs > candle_body.shift(1).abs()),
            1.0,
            np.where(
                (candle_body < 0) & (prev_body > 0) & (candle_body_abs > candle_body.shift(1).abs()),
                -1.0, 0.0
            )
        ), index=frame.index)
        # Morning/Evening star (simplified 3-bar pattern)
        body_2_ago = candle_body.shift(2)
        small_body_1 = candle_body_abs.shift(1) < candle_range.shift(1).replace(0, np.nan) * 0.3
        pattern_morning_evening_star = pd.Series(np.where(
            (body_2_ago < 0) & small_body_1 & (candle_body > 0) & (close > close.shift(2)),
            1.0,
            np.where(
                (body_2_ago > 0) & small_body_1 & (candle_body < 0) & (close < close.shift(2)),
                -1.0, 0.0
            )
        ), index=frame.index)
        # Three soldiers/crows
        three_up = (
            (candle_body > 0) & (candle_body.shift(1) > 0) & (candle_body.shift(2) > 0) &
            (close > close.shift(1)) & (close.shift(1) > close.shift(2))
        )
        three_down = (
            (candle_body < 0) & (candle_body.shift(1) < 0) & (candle_body.shift(2) < 0) &
            (close < close.shift(1)) & (close.shift(1) < close.shift(2))
        )
        pattern_three_soldiers_crows = pd.Series(np.where(
            three_up, 1.0, np.where(three_down, -1.0, 0.0)
        ), index=frame.index)
        # Pin bar: long shadow > 2.5x body, body in upper/lower 1/3
        long_upper_pin = (upper_shadow > 2.5 * candle_body_abs) & (lower_shadow < candle_body_abs)
        long_lower_pin = (lower_shadow > 2.5 * candle_body_abs) & (upper_shadow < candle_body_abs)
        pattern_pin_bar = pd.Series(np.where(
            long_lower_pin, 1.0, np.where(long_upper_pin, -1.0, 0.0)
        ), index=frame.index)
        # Inside bar: current H < prev H and current L > prev L
        pattern_inside_bar = (
            (high < high.shift(1)) & (low > low.shift(1))
        ).astype(float)
        # Outside bar: current H > prev H and current L < prev L
        pattern_outside_bar = (
            (high > high.shift(1)) & (low < low.shift(1))
        ).astype(float)

        pattern_frame = pd.DataFrame({
            "pattern_doji": pattern_doji,
            "pattern_hammer": pattern_hammer,
            "pattern_engulfing": pattern_engulfing,
            "pattern_morning_evening_star": pattern_morning_evening_star,
            "pattern_three_soldiers_crows": pattern_three_soldiers_crows,
            "pattern_pin_bar": pattern_pin_bar,
            "pattern_inside_bar": pattern_inside_bar,
            "pattern_outside_bar": pattern_outside_bar,
        }, index=frame.index)

        # === Batch 3: Adaptive / Ehlers indicators ===
        ehlers_fisher_transform_13, _ = self._fisher_transform(median_price, period=13)
        ehlers_instantaneous_trendline = self._ehlers_instantaneous_trendline(close)
        ehlers_cyber_cycle = self._ehlers_cyber_cycle(close)
        ehlers_dominant_cycle_period = self._ehlers_dominant_cycle_period(close)
        # Adaptive RSI: weight RSI by efficiency ratio
        er_10 = close.diff(10).abs() / close.diff().abs().rolling(10).sum().replace(0, np.nan)
        adaptive_rsi_14 = rsi_14 * er_10 + 50 * (1 - er_10)
        # Fractal dimension (Higuchi method approximation)
        fractal_dimension_20 = close.rolling(20).apply(self._fractal_dimension, raw=True)
        # Hurst exponent (R/S method)
        hurst_exponent_20 = close.rolling(20).apply(self._hurst_exponent, raw=True)
        # Shannon entropy of returns
        entropy_20 = return_1.rolling(20).apply(self._shannon_entropy, raw=True)

        adaptive_frame = pd.DataFrame({
            "ehlers_fisher_transform_13": ehlers_fisher_transform_13,
            "ehlers_instantaneous_trendline": ehlers_instantaneous_trendline,
            "ehlers_cyber_cycle": ehlers_cyber_cycle,
            "ehlers_dominant_cycle_period": ehlers_dominant_cycle_period,
            "adaptive_rsi_14": adaptive_rsi_14,
            "fractal_dimension_20": fractal_dimension_20,
            "hurst_exponent_20": hurst_exponent_20,
            "entropy_20": entropy_20,
        }, index=frame.index)

        # === Batch 3: Microstructure stats ===
        realized_volatility_10 = (log_return_1.pow(2).rolling(10).sum()).pow(0.5)
        # Yang-Zhang volatility
        log_oc = np.log(open_price / previous_close.replace(0, np.nan))
        log_co = np.log(close / open_price.replace(0, np.nan))
        oc_var = log_oc.rolling(20).var(ddof=1)
        co_var = log_co.rolling(20).var(ddof=1)
        rs_var = rogers_satchell_component.rolling(20).mean()
        k_yz = 0.34 / (1.34 + (21.0 / 19.0))
        yang_zhang_volatility_20 = (oc_var + k_yz * co_var + (1 - k_yz) * rs_var).clip(lower=0).pow(0.5)
        # Intraday intensity
        ii_raw = ((2 * close - high - low) / (high - low).replace(0, np.nan)) * volume
        intraday_intensity_20 = ii_raw.rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
        # Volume-weighted RSI
        vol_weight = volume / volume.rolling(14).mean().replace(0, np.nan)
        vw_gain = (gain * vol_weight).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        vw_loss = (loss * vol_weight).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        vw_rs = vw_gain / vw_loss.replace(0, np.nan)
        volume_weighted_rsi_14 = 100 - (100 / (1 + vw_rs))
        # Relative volume
        relative_volume_5 = volume / volume.rolling(5).mean().replace(0, np.nan)
        # Tick intensity
        tick_intensity = return_1.abs() / (volume.replace(0, np.nan) / volume.rolling(20).mean().replace(0, np.nan))
        # Amihud illiquidity
        amihud_illiquidity_20 = (return_1.abs() / (volume * close).replace(0, np.nan)).rolling(20).mean()
        # Kyle's lambda (price impact)
        signed_volume = np.sign(close.diff()) * volume
        kyle_lambda_20 = return_1.rolling(20).corr(signed_volume / volume.rolling(20).mean().replace(0, np.nan))
        # Return dispersion
        return_dispersion_20 = (np.log(high / low.replace(0, np.nan))).rolling(20).std(ddof=0)
        # Overnight gap
        overnight_gap_pct = (open_price - previous_close) / previous_close.replace(0, np.nan)

        microstructure_frame = pd.DataFrame({
            "realized_volatility_10": realized_volatility_10,
            "yang_zhang_volatility_20": yang_zhang_volatility_20,
            "intraday_intensity_20": intraday_intensity_20,
            "volume_weighted_rsi_14": volume_weighted_rsi_14,
            "relative_volume_5": relative_volume_5,
            "tick_intensity": tick_intensity,
            "amihud_illiquidity_20": amihud_illiquidity_20,
            "kyle_lambda_20": kyle_lambda_20,
            "return_dispersion_20": return_dispersion_20,
            "overnight_gap_pct": overnight_gap_pct,
        }, index=frame.index)

        indicator_frame = pd.concat(
            [
                trend_frame,
                momentum_frame,
                volatility_frame,
                volume_frame,
                structure_frame,
                state_frame,
                risk_frame,
                crossover_frame,
                pivot_frame,
                pattern_frame,
                adaptive_frame,
                microstructure_frame,
            ],
            axis=1,
        )
        result = pd.concat([base, indicator_frame], axis=1)
        return result[self.OUTPUT_COLUMNS]

    @staticmethod
    def _aroon_up(values) -> float:
        window = pd.Series(values)
        if window.isna().any():
            return float("nan")
        period = len(window)
        periods_since_high = period - 1 - int(window.values.argmax())
        return ((period - periods_since_high) / period) * 100

    @staticmethod
    def _aroon_down(values) -> float:
        window = pd.Series(values)
        if window.isna().any():
            return float("nan")
        period = len(window)
        periods_since_low = period - 1 - int(window.values.argmin())
        return ((period - periods_since_low) / period) * 100

    @staticmethod
    def _supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr: pd.Series,
        multiplier: float,
    ) -> tuple[pd.Series, pd.Series]:
        hl2 = (high + low) / 2
        basic_upper = hl2 + (multiplier * atr)
        basic_lower = hl2 - (multiplier * atr)
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        supertrend = pd.Series(index=close.index, dtype="float64")
        direction = pd.Series(index=close.index, dtype="float64")

        for i in range(1, len(close)):
            if (
                pd.isna(basic_upper.iloc[i]) or
                pd.isna(basic_lower.iloc[i]) or
                pd.isna(close.iloc[i - 1])
            ):
                continue

            previous_upper = final_upper.iloc[i - 1]
            previous_lower = final_lower.iloc[i - 1]
            if (
                pd.isna(previous_upper) or
                basic_upper.iloc[i] < previous_upper or
                close.iloc[i - 1] > previous_upper
            ):
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = previous_upper

            if (
                pd.isna(previous_lower) or
                basic_lower.iloc[i] > previous_lower or
                close.iloc[i - 1] < previous_lower
            ):
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = previous_lower

        first_valid = atr.first_valid_index()
        if first_valid is None:
            return supertrend, direction

        direction.iloc[first_valid] = 1.0 if close.iloc[first_valid] >= hl2.iloc[first_valid] else -1.0
        supertrend.iloc[first_valid] = (
            final_lower.iloc[first_valid]
            if direction.iloc[first_valid] > 0
            else final_upper.iloc[first_valid]
        )

        for i in range(first_valid + 1, len(close)):
            previous_upper = final_upper.iloc[i - 1]
            previous_lower = final_lower.iloc[i - 1]
            previous_direction = direction.iloc[i - 1]

            if (
                pd.isna(previous_upper) or
                pd.isna(previous_lower) or
                pd.isna(previous_direction)
            ):
                continue

            if close.iloc[i] > previous_upper:
                direction.iloc[i] = 1.0
            elif close.iloc[i] < previous_lower:
                direction.iloc[i] = -1.0
            else:
                direction.iloc[i] = previous_direction
                if direction.iloc[i] > 0 and final_lower.iloc[i] < previous_lower:
                    final_lower.iloc[i] = previous_lower
                if direction.iloc[i] < 0 and final_upper.iloc[i] > previous_upper:
                    final_upper.iloc[i] = previous_upper

            supertrend.iloc[i] = (
                final_lower.iloc[i]
                if direction.iloc[i] > 0
                else final_upper.iloc[i]
            )

        return supertrend, direction

    @staticmethod
    def _parabolic_sar(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        step: float = 0.02,
        max_step: float = 0.2,
    ) -> tuple[pd.Series, pd.Series]:
        psar = pd.Series(index=close.index, dtype="float64")
        trend = pd.Series(index=close.index, dtype="float64")
        if len(close) == 0:
            return psar, trend

        uptrend = True
        if len(close) > 1 and close.iloc[1] < close.iloc[0]:
            uptrend = False

        psar.iloc[0] = low.iloc[0] if uptrend else high.iloc[0]
        trend.iloc[0] = 1.0 if uptrend else -1.0
        extreme_point = high.iloc[0] if uptrend else low.iloc[0]
        acceleration = step

        for i in range(1, len(close)):
            previous_psar = psar.iloc[i - 1]
            current_psar = previous_psar + acceleration * (extreme_point - previous_psar)

            if uptrend:
                current_psar = min(
                    current_psar,
                    low.iloc[i - 1],
                    low.iloc[i - 2] if i > 1 else low.iloc[i - 1],
                )
                if low.iloc[i] < current_psar:
                    uptrend = False
                    current_psar = extreme_point
                    extreme_point = low.iloc[i]
                    acceleration = step
                else:
                    if high.iloc[i] > extreme_point:
                        extreme_point = high.iloc[i]
                        acceleration = min(acceleration + step, max_step)
            else:
                current_psar = max(
                    current_psar,
                    high.iloc[i - 1],
                    high.iloc[i - 2] if i > 1 else high.iloc[i - 1],
                )
                if high.iloc[i] > current_psar:
                    uptrend = True
                    current_psar = extreme_point
                    extreme_point = high.iloc[i]
                    acceleration = step
                else:
                    if low.iloc[i] < extreme_point:
                        extreme_point = low.iloc[i]
                        acceleration = min(acceleration + step, max_step)

            psar.iloc[i] = current_psar
            trend.iloc[i] = 1.0 if uptrend else -1.0

        return psar, trend

    @staticmethod
    def _kama(
        close: pd.Series,
        er_period: int,
        fast_period: int,
        slow_period: int,
    ) -> pd.Series:
        kama = pd.Series(index=close.index, dtype="float64")
        if len(close) <= er_period:
            return kama

        change = close.diff(er_period).abs()
        volatility = close.diff().abs().rolling(er_period).sum()
        efficiency_ratio = change / volatility.replace(0, np.nan)
        fast_sc = 2 / (fast_period + 1)
        slow_sc = 2 / (slow_period + 1)
        smoothing_constant = (
            efficiency_ratio * (fast_sc - slow_sc) + slow_sc
        ) ** 2

        kama.iloc[er_period] = close.iloc[er_period]
        for i in range(er_period + 1, len(close)):
            previous_kama = kama.iloc[i - 1]
            current_sc = smoothing_constant.iloc[i]
            if pd.isna(previous_kama) or pd.isna(current_sc):
                kama.iloc[i] = previous_kama
                continue
            kama.iloc[i] = previous_kama + current_sc * (close.iloc[i] - previous_kama)

        return kama

    @staticmethod
    def _mass_index(
        high: pd.Series,
        low: pd.Series,
        ema_period: int,
        sum_period: int,
    ) -> pd.Series:
        intraday_range = high - low
        ema1 = intraday_range.ewm(
            span=ema_period,
            adjust=False,
            min_periods=ema_period,
        ).mean()
        ema2 = ema1.ewm(
            span=ema_period,
            adjust=False,
            min_periods=ema_period,
        ).mean()
        mass_ratio = ema1 / ema2.replace(0, np.nan)
        return mass_ratio.rolling(sum_period).sum()

    @staticmethod
    def _weighted_moving_average(series: pd.Series, period: int) -> pd.Series:
        weights = np.arange(1, period + 1, dtype="float64")
        return series.rolling(period).apply(
            lambda values: float(np.dot(values, weights) / weights.sum()),
            raw=True,
        )

    @staticmethod
    def _percent_rank(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        return float((window <= window[-1]).sum() / len(window) * 100)

    @staticmethod
    def _lag1_autocorrelation(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any() or len(window) < 2:
            return float("nan")
        x = window[:-1]
        y = window[1:]
        if np.std(x) == 0 or np.std(y) == 0:
            return float("nan")
        return float(np.corrcoef(x, y)[0, 1])

    @staticmethod
    def _median_absolute_deviation(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        median = np.median(window)
        return float(np.median(np.abs(window - median)))

    @staticmethod
    def _interquartile_range(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        return float(np.percentile(window, 75) - np.percentile(window, 25))

    @staticmethod
    def _tail_ratio(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        lower_tail = np.percentile(window, 5)
        upper_tail = np.percentile(window, 95)
        if lower_tail == 0:
            return float("nan")
        return float(upper_tail / abs(lower_tail))

    @staticmethod
    def _gain_to_pain_ratio(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        gains = window[window > 0].sum()
        pain = np.abs(window[window < 0].sum())
        if pain == 0:
            return float("nan")
        return float(gains / pain)

    @staticmethod
    def _chande_forecast_oscillator(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        x = np.arange(len(window), dtype="float64")
        slope = TechnicalIndicatorCalculator._linear_regression_slope(window)
        if np.isnan(slope):
            return float("nan")
        intercept = window.mean() - (slope * x.mean())
        forecast = intercept + (slope * len(window))
        if window[-1] == 0:
            return float("nan")
        return float((window[-1] - forecast) / window[-1] * 100)

    @staticmethod
    def _positive_negative_volume_index(
        close: pd.Series,
        volume: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        nvi = pd.Series(index=close.index, dtype="float64")
        pvi = pd.Series(index=close.index, dtype="float64")
        if len(close) == 0:
            return nvi, pvi

        returns = close.pct_change(fill_method=None).fillna(0)
        nvi.iloc[0] = 1000.0
        pvi.iloc[0] = 1000.0
        for i in range(1, len(close)):
            previous_nvi = nvi.iloc[i - 1]
            previous_pvi = pvi.iloc[i - 1]
            if volume.iloc[i] < volume.iloc[i - 1]:
                nvi.iloc[i] = previous_nvi * (1 + returns.iloc[i])
            else:
                nvi.iloc[i] = previous_nvi

            if volume.iloc[i] > volume.iloc[i - 1]:
                pvi.iloc[i] = previous_pvi * (1 + returns.iloc[i])
            else:
                pvi.iloc[i] = previous_pvi

        return nvi, pvi

    @staticmethod
    def _klinger_volume_oscillator(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
        fast_period: int = 34,
        slow_period: int = 55,
        signal_period: int = 13,
    ) -> tuple[pd.Series, pd.Series]:
        line = pd.Series(index=close.index, dtype="float64")
        signal = pd.Series(index=close.index, dtype="float64")
        if len(close) == 0:
            return line, signal

        trend_basis = high + low + close
        trend = pd.Series(
            np.where(
                trend_basis > trend_basis.shift(1),
                1.0,
                np.where(trend_basis < trend_basis.shift(1), -1.0, np.nan),
            ),
            index=close.index,
        ).ffill().fillna(1.0)
        dm = high - low
        cm = pd.Series(index=close.index, dtype="float64")
        cm.iloc[0] = dm.iloc[0]
        for i in range(1, len(close)):
            if trend.iloc[i] == trend.iloc[i - 1]:
                cm.iloc[i] = cm.iloc[i - 1] + dm.iloc[i]
            else:
                cm.iloc[i] = dm.iloc[i - 1] + dm.iloc[i]

        vf = volume * trend * (2 * ((dm / cm.replace(0, np.nan)) - 1)).abs() * 100
        line = vf.ewm(span=fast_period, adjust=False).mean() - vf.ewm(
            span=slow_period,
            adjust=False,
        ).mean()
        signal = line.ewm(span=signal_period, adjust=False).mean()
        return line, signal

    @staticmethod
    def _schaff_trend_cycle(
        close: pd.Series,
        cycle_period: int,
        fast_period: int,
        slow_period: int,
    ) -> pd.Series:
        ema_fast = close.ewm(span=fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=slow_period, adjust=False).mean()
        macd = ema_fast - ema_slow

        lowest_macd = macd.rolling(cycle_period).min()
        highest_macd = macd.rolling(cycle_period).max()
        stochastic_macd = (
            100 * (macd - lowest_macd) /
            (highest_macd - lowest_macd).replace(0, np.nan)
        )
        smoothed_stochastic = stochastic_macd.ewm(span=3, adjust=False).mean()

        lowest_smoothed = smoothed_stochastic.rolling(cycle_period).min()
        highest_smoothed = smoothed_stochastic.rolling(cycle_period).max()
        second_stochastic = (
            100 * (smoothed_stochastic - lowest_smoothed) /
            (highest_smoothed - lowest_smoothed).replace(0, np.nan)
        )
        return second_stochastic.ewm(span=3, adjust=False).mean()

    @staticmethod
    def _linear_regression_slope(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        x = np.arange(len(window), dtype="float64")
        x_centered = x - x.mean()
        y_centered = window - window.mean()
        denominator = np.dot(x_centered, x_centered)
        if denominator == 0:
            return float("nan")
        return float(np.dot(x_centered, y_centered) / denominator)

    @staticmethod
    def _linear_regression_r2(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        x = np.arange(len(window), dtype="float64")
        slope = TechnicalIndicatorCalculator._linear_regression_slope(window)
        if np.isnan(slope):
            return float("nan")
        intercept = window.mean() - (slope * x.mean())
        fitted = intercept + (slope * x)
        ss_tot = np.square(window - window.mean()).sum()
        if ss_tot == 0:
            return float("nan")
        ss_res = np.square(window - fitted).sum()
        return float(1 - (ss_res / ss_tot))

    @staticmethod
    def _linear_regression_last_distance(values) -> float:
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any():
            return float("nan")
        x = np.arange(len(window), dtype="float64")
        slope = TechnicalIndicatorCalculator._linear_regression_slope(window)
        if np.isnan(slope):
            return float("nan")
        intercept = window.mean() - (slope * x.mean())
        fitted_last = intercept + (slope * x[-1])
        if fitted_last == 0:
            return float("nan")
        return float((window[-1] - fitted_last) / fitted_last)

    @staticmethod
    def _fisher_transform(
        price: pd.Series,
        period: int,
    ) -> tuple[pd.Series, pd.Series]:
        highest = price.rolling(period).max()
        lowest = price.rolling(period).min()
        smoothed_value = pd.Series(index=price.index, dtype="float64")
        fisher = pd.Series(index=price.index, dtype="float64")

        for i in range(len(price)):
            highest_value = highest.iloc[i]
            lowest_value = lowest.iloc[i]
            current_price = price.iloc[i]
            if (
                pd.isna(highest_value) or
                pd.isna(lowest_value) or
                pd.isna(current_price) or
                highest_value == lowest_value
            ):
                continue

            normalized = 2 * (
                (current_price - lowest_value) / (highest_value - lowest_value)
            ) - 1
            previous_smoothed = (
                smoothed_value.iloc[i - 1]
                if i > 0 and pd.notna(smoothed_value.iloc[i - 1])
                else 0.0
            )
            current_smoothed = (0.33 * normalized) + (0.67 * previous_smoothed)
            current_smoothed = min(max(current_smoothed, -0.999), 0.999)
            smoothed_value.iloc[i] = current_smoothed

            previous_fisher = (
                fisher.iloc[i - 1]
                if i > 0 and pd.notna(fisher.iloc[i - 1])
                else 0.0
            )
            fisher.iloc[i] = (
                0.5 * np.log((1 + current_smoothed) / (1 - current_smoothed)) +
                0.5 * previous_fisher
            )

        return fisher, fisher.shift(1)

    @staticmethod
    def _ehlers_instantaneous_trendline(close: pd.Series) -> pd.Series:
        """Ehlers Instantaneous Trendline (2-pole super smoother)."""
        it = pd.Series(index=close.index, dtype="float64")
        if len(close) < 7:
            return it
        a = np.exp(-np.sqrt(2) * np.pi / 10)
        b = 2 * a * np.cos(np.sqrt(2) * np.pi / 10)
        c2 = b
        c3 = -(a * a)
        c1 = 1 - c2 - c3
        it.iloc[0] = close.iloc[0]
        it.iloc[1] = close.iloc[1]
        for i in range(2, len(close)):
            it.iloc[i] = c1 * (close.iloc[i] + close.iloc[i - 1]) / 2 + c2 * it.iloc[i - 1] + c3 * it.iloc[i - 2]
        return it

    @staticmethod
    def _ehlers_cyber_cycle(close: pd.Series) -> pd.Series:
        """Ehlers Cyber Cycle oscillator."""
        cycle = pd.Series(0.0, index=close.index, dtype="float64")
        smooth = pd.Series(0.0, index=close.index, dtype="float64")
        if len(close) < 7:
            return cycle
        for i in range(2, len(close)):
            smooth.iloc[i] = (close.iloc[i] + 2 * close.iloc[i - 1] + close.iloc[i - 2]) / 4
        alpha = 0.07
        for i in range(6, len(close)):
            cycle.iloc[i] = (
                (1 - 0.5 * alpha) ** 2 * (smooth.iloc[i] - 2 * smooth.iloc[i - 1] + smooth.iloc[i - 2])
                + 2 * (1 - alpha) * cycle.iloc[i - 1]
                - (1 - alpha) ** 2 * cycle.iloc[i - 2]
            )
        return cycle

    @staticmethod
    def _ehlers_dominant_cycle_period(close: pd.Series) -> pd.Series:
        """Estimate dominant cycle period using autocorrelation."""
        period = pd.Series(np.nan, index=close.index, dtype="float64")
        window = 50
        if len(close) < window:
            return period
        for i in range(window, len(close)):
            segment = close.iloc[i - window:i].values
            segment = segment - segment.mean()
            if np.std(segment) == 0:
                continue
            best_period = 10
            best_corr = -1.0
            for p in range(5, 25):
                if p >= len(segment):
                    break
                corr = np.corrcoef(segment[p:], segment[:-p])[0, 1]
                if corr > best_corr:
                    best_corr = corr
                    best_period = p
            period.iloc[i] = float(best_period)
        return period

    @staticmethod
    def _fractal_dimension(values) -> float:
        """Approximate fractal dimension using variation method."""
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any() or len(window) < 4:
            return float("nan")
        n = len(window)
        max_val = np.max(window)
        min_val = np.min(window)
        rng = max_val - min_val
        if rng == 0:
            return 1.0
        # Simplified box-counting approximation
        n1 = int(n / 2)
        # Length at scale 1
        l1 = sum(abs(window[i] - window[i - 1]) for i in range(1, n))
        # Length at scale 2
        l2 = sum(abs(window[i] - window[i - 2]) for i in range(2, n, 2))
        if l2 == 0 or l1 == 0:
            return 1.5
        return 1 + np.log(l1 / l2) / np.log(2)

    @staticmethod
    def _hurst_exponent(values) -> float:
        """Simplified R/S Hurst exponent estimation."""
        window = np.asarray(values, dtype="float64")
        if np.isnan(window).any() or len(window) < 10:
            return float("nan")
        returns = np.diff(window) / window[:-1]
        returns = returns[~np.isnan(returns)]
        if len(returns) < 8:
            return float("nan")
        mean_r = np.mean(returns)
        deviations = np.cumsum(returns - mean_r)
        r = np.max(deviations) - np.min(deviations)
        s = np.std(returns, ddof=1)
        if s == 0 or r == 0:
            return 0.5
        rs = r / s
        n = len(returns)
        if rs <= 0 or n <= 1:
            return 0.5
        return np.log(rs) / np.log(n)

    @staticmethod
    def _shannon_entropy(values) -> float:
        """Shannon entropy of return distribution (binned)."""
        window = np.asarray(values, dtype="float64")
        window = window[~np.isnan(window)]
        if len(window) < 5:
            return float("nan")
        # Bin into 5 equal-width bins
        hist, _ = np.histogram(window, bins=5)
        probs = hist / hist.sum()
        probs = probs[probs > 0]
        return float(-np.sum(probs * np.log2(probs)))
