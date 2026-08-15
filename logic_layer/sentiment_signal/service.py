"""sentiment_signal 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from logic_layer.sentiment_signal.analyzer import SentimentAnalyzer
from logic_layer.sentiment_signal.repository import SentimentSignalRepository


from config.symbols import TARGET_ASSET_CODES

TARGET_SYMBOLS = TARGET_ASSET_CODES


class SentimentSignalService:
    """情绪信号服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = SentimentSignalRepository(self.db)
        self.analyzer = SentimentAnalyzer()

    def init_storage(self):
        self.repository.ensure_tables()
        logger.info("sentiment_signal 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_analysis(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行情绪信号分析。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        all_signals = {}
        causality_results = {}

        for symbol in symbols:
            sentiments, returns = self._fetch_data(symbol)
            if not sentiments or not returns:
                continue

            signals = []

            # 极值反转检测
            reversal = self.analyzer.detect_extreme_reversal(sentiments, returns)
            if reversal:
                reversal["price_correlation"] = self.analyzer.compute_correlation(sentiments, returns)
                reversal["confidence"] = 0.6
                signals.append(reversal)

            # 动量确认检测
            momentum = self.analyzer.detect_momentum_confirm(sentiments, returns)
            if momentum:
                momentum["price_correlation"] = self.analyzer.compute_correlation(sentiments, returns)
                momentum["confidence"] = 0.5
                signals.append(momentum)

            # 背离检测
            divergence = self.analyzer.detect_divergence(sentiments, returns)
            if divergence:
                divergence["price_correlation"] = self.analyzer.compute_correlation(sentiments, returns)
                divergence["confidence"] = 0.55
                signals.append(divergence)

            # Granger 因果检验
            causality = self.analyzer.simplified_granger_test(sentiments, returns)
            causality_results[symbol] = causality

            if signals:
                all_signals[symbol] = signals
                if save:
                    for s in signals:
                        self.repository.save_signal(symbol, s, now_iso)
            if save:
                self.repository.save_causality(symbol, causality, now_iso)

        return {
            "status": "ok",
            "as_of": now_iso,
            "signals": all_signals,
            "causality": causality_results,
            "symbols_with_signals": len(all_signals),
        }

    def _fetch_data(self, symbol: str) -> tuple[list[float], list[float]]:
        """获取情绪和价格数据。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            # 获取情绪数据
            cursor = market_db.conn.execute("""
                SELECT avg_sentiment FROM social_sentiment_agg
                WHERE entity_key = ? ORDER BY window_start DESC LIMIT 100
            """, (symbol,))
            sent_rows = cursor.fetchall()

            # 获取价格数据
            cursor = market_db.conn.execute("""
                SELECT close FROM merged_klines
                WHERE entity_key = ? ORDER BY open_time DESC LIMIT 100
            """, (symbol,))
            price_rows = cursor.fetchall()

            if len(sent_rows) < 20 or len(price_rows) < 20:
                return [], []

            sentiments = [r[0] for r in reversed(sent_rows)]
            closes = [r[0] for r in reversed(price_rows)]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

            # 对齐长度
            n = min(len(sentiments), len(returns))
            return sentiments[-n:], returns[-n:]
        except Exception as e:
            logger.debug(f"获取数据失败 [{symbol}]: {e}")
            return [], []

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的情绪信号上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        signals = self.repository.fetch_recent_signals(hours=24)
        causality = self.repository.fetch_latest_causality()

        if not signals and not causality:
            return {"status": "no_data", "as_of": now_iso}

        filtered_signals = [s for s in signals if s["entity_key"] in symbols]
        filtered_causality = {c["entity_key"]: c for c in causality if c["entity_key"] in symbols}

        # 信号汇总
        bullish_signals = [s for s in filtered_signals if s["direction"] == "bullish"]
        bearish_signals = [s for s in filtered_signals if s["direction"] == "bearish"]

        # 因果关系汇总
        sentiment_leads = [k for k, v in filtered_causality.items()
                          if v["direction"] == "sentiment_leads_price" and v["is_significant"]]

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "signal_summary": {
                "total_signals": len(filtered_signals),
                "bullish_count": len(bullish_signals),
                "bearish_count": len(bearish_signals),
                "net_bias": "bullish" if len(bullish_signals) > len(bearish_signals)
                           else "bearish" if len(bearish_signals) > len(bullish_signals)
                           else "neutral",
            },
            "causality_summary": {
                "sentiment_leads_price": sentiment_leads,
                "predictive_assets": len(sentiment_leads),
            },
            "active_signals": filtered_signals[:15],
            "causality_details": filtered_causality,
            "coverage": {
                "symbols_with_signals": len(set(s["entity_key"] for s in filtered_signals)),
                "symbols_with_causality": len(filtered_causality),
                "symbols_requested": len(symbols),
            },
        }

    def close(self):
        pass
