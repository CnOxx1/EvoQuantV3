"""sentiment_signal 情绪分析器。"""

import math
import statistics


class SentimentAnalyzer:
    """情绪信号分析器。

    核心功能：
    1. 情绪极值反转信号：当情绪达到极端时生成反向信号
    2. 情绪-价格相关性：计算滚动相关性
    3. 简化 Granger 因果检验：判断情绪是否领先价格
    4. 情绪动量确认：情绪与价格同向时确认趋势
    """

    # 极值阈值
    EXTREME_BULLISH = 0.7      # 情绪 > 0.7 视为极度乐观
    EXTREME_BEARISH = -0.7     # 情绪 < -0.7 视为极度悲观
    ZSCORE_EXTREME = 2.0       # z-score > 2 视为极端

    def detect_extreme_reversal(self, sentiments: list[float], returns: list[float]) -> dict | None:
        """检测情绪极值反转信号。

        逻辑：当情绪达到极端水平时，市场往往即将反转。
        """
        if len(sentiments) < 20 or len(returns) < 5:
            return None

        current_sentiment = sentiments[-1]
        mean = statistics.mean(sentiments[:-1])
        std = statistics.stdev(sentiments[:-1]) if len(sentiments) > 2 else 0.1
        if std == 0:
            std = 0.1
        zscore = (current_sentiment - mean) / std

        # 极度乐观 → 看空反转信号
        if current_sentiment >= self.EXTREME_BULLISH or zscore >= self.ZSCORE_EXTREME:
            strength = min(1.0, abs(zscore) / 3.0)
            return {
                "signal_type": "extreme_reversal",
                "direction": "bearish",
                "strength": round(strength, 4),
                "sentiment_value": round(current_sentiment, 4),
                "sentiment_zscore": round(zscore, 4),
                "description": f"情绪极度乐观 (z={zscore:.1f})，历史上常伴随回调",
            }

        # 极度悲观 → 看多反转信号
        if current_sentiment <= self.EXTREME_BEARISH or zscore <= -self.ZSCORE_EXTREME:
            strength = min(1.0, abs(zscore) / 3.0)
            return {
                "signal_type": "extreme_reversal",
                "direction": "bullish",
                "strength": round(strength, 4),
                "sentiment_value": round(current_sentiment, 4),
                "sentiment_zscore": round(zscore, 4),
                "description": f"情绪极度悲观 (z={zscore:.1f})，历史上常伴随反弹",
            }

        return None

    def detect_momentum_confirm(self, sentiments: list[float], returns: list[float]) -> dict | None:
        """检测情绪动量确认信号。

        逻辑：当情绪方向与价格方向一致且都在加速时，趋势可能延续。
        """
        if len(sentiments) < 10 or len(returns) < 10:
            return None

        # 情绪趋势
        sent_recent = statistics.mean(sentiments[-5:])
        sent_prev = statistics.mean(sentiments[-10:-5])
        sent_delta = sent_recent - sent_prev

        # 价格趋势
        ret_recent = sum(returns[-5:])
        ret_prev = sum(returns[-10:-5])

        # 同向加速
        if sent_delta > 0.1 and ret_recent > 0.02 and ret_prev > 0:
            strength = min(1.0, sent_delta * 2)
            return {
                "signal_type": "momentum_confirm",
                "direction": "bullish",
                "strength": round(strength, 4),
                "sentiment_value": round(sent_recent, 4),
                "sentiment_zscore": 0.0,
                "description": "情绪与价格同步上行，趋势确认",
            }

        if sent_delta < -0.1 and ret_recent < -0.02 and ret_prev < 0:
            strength = min(1.0, abs(sent_delta) * 2)
            return {
                "signal_type": "momentum_confirm",
                "direction": "bearish",
                "strength": round(strength, 4),
                "sentiment_value": round(sent_recent, 4),
                "sentiment_zscore": 0.0,
                "description": "情绪与价格同步下行，趋势确认",
            }

        return None

    def detect_divergence(self, sentiments: list[float], returns: list[float]) -> dict | None:
        """检测情绪-价格背离信号。

        逻辑：当情绪与价格方向相反时，可能预示拐点。
        """
        if len(sentiments) < 10 or len(returns) < 10:
            return None

        sent_trend = statistics.mean(sentiments[-5:]) - statistics.mean(sentiments[-10:-5])
        price_trend = sum(returns[-5:])

        # 价格涨但情绪跌 → 看空背离
        if price_trend > 0.03 and sent_trend < -0.15:
            strength = min(1.0, abs(sent_trend) * 2)
            return {
                "signal_type": "divergence",
                "direction": "bearish",
                "strength": round(strength, 4),
                "sentiment_value": round(sentiments[-1], 4),
                "sentiment_zscore": 0.0,
                "description": "价格上涨但情绪下降，看空背离",
            }

        # 价格跌但情绪涨 → 看多背离
        if price_trend < -0.03 and sent_trend > 0.15:
            strength = min(1.0, abs(sent_trend) * 2)
            return {
                "signal_type": "divergence",
                "direction": "bullish",
                "strength": round(strength, 4),
                "sentiment_value": round(sentiments[-1], 4),
                "sentiment_zscore": 0.0,
                "description": "价格下跌但情绪上升，看多背离",
            }

        return None

    def compute_correlation(self, sentiments: list[float], returns: list[float], lag: int = 0) -> float:
        """计算情绪与收益率的相关性（支持滞后）。"""
        if lag > 0:
            sentiments = sentiments[:-lag]
            returns = returns[lag:]
        elif lag < 0:
            sentiments = sentiments[-lag:]
            returns = returns[:lag]

        n = min(len(sentiments), len(returns))
        if n < 10:
            return 0.0

        s = sentiments[-n:]
        r = returns[-n:]

        mean_s = sum(s) / n
        mean_r = sum(r) / n
        cov = sum((s[i] - mean_s) * (r[i] - mean_r) for i in range(n)) / n
        std_s = (sum((x - mean_s)**2 for x in s) / n) ** 0.5
        std_r = (sum((x - mean_r)**2 for x in r) / n) ** 0.5

        if std_s == 0 or std_r == 0:
            return 0.0
        return round(cov / (std_s * std_r), 4)

    def simplified_granger_test(self, sentiments: list[float], returns: list[float], max_lag: int = 12) -> dict:
        """简化的 Granger 因果检验。

        通过比较不同滞后期的相关性来判断领先/滞后关系。
        """
        if len(sentiments) < 30 or len(returns) < 30:
            return {
                "direction": "none",
                "f_statistic": 0.0,
                "p_value": 1.0,
                "optimal_lag": 0,
                "is_significant": False,
            }

        # 计算不同滞后期的相关性
        best_lag = 0
        best_corr = 0.0

        for lag in range(-max_lag, max_lag + 1):
            corr = self.compute_correlation(sentiments, returns, lag)
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = lag

        # 判断方向
        # lag > 0: sentiment 领先 price
        # lag < 0: price 领先 sentiment
        if best_lag > 0 and abs(best_corr) > 0.2:
            direction = "sentiment_leads_price"
        elif best_lag < 0 and abs(best_corr) > 0.2:
            direction = "price_leads_sentiment"
        elif abs(best_corr) > 0.3:
            direction = "bidirectional"
        else:
            direction = "none"

        # 简化的 F 统计量（用相关性平方近似）
        n = min(len(sentiments), len(returns))
        r_squared = best_corr ** 2
        f_stat = r_squared / (1 - r_squared) * (n - 2) if r_squared < 1 else 0
        # 简化 p-value 估算
        p_value = max(0.001, 1.0 - abs(best_corr) * 2)

        return {
            "direction": direction,
            "f_statistic": round(f_stat, 4),
            "p_value": round(p_value, 4),
            "optimal_lag": best_lag,
            "is_significant": abs(best_corr) > 0.2 and abs(best_lag) > 0,
        }
