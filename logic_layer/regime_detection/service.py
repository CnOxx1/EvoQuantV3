"""regime_detection 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from config.symbols import TARGET_ASSET_CODES
from logic_layer.regime_detection.classifier import RegimeClassifier, RegimeFeatures
from logic_layer.regime_detection.repository import RegimeDetectionRepository

TARGET_SYMBOLS = TARGET_ASSET_CODES


class RegimeDetectionService:
    """市场状态识别服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = RegimeDetectionRepository(self.db)
        self.classifier = RegimeClassifier()

    def init_storage(self):
        """初始化存储。"""
        self.repository.ensure_tables()
        logger.info("regime_detection 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_detection(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行状态识别。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        results = {}

        for symbol in symbols:
            features = self._build_features(symbol)
            if features is None:
                continue

            # 分类各维度
            price_regime, confidence = self.classifier.classify_price_regime(features)
            vol_regime = self.classifier.classify_volatility_regime(features)
            corr_regime = self.classifier.classify_correlation_regime(features.correlation_to_btc)
            momentum_regime = self.classifier.classify_momentum_regime(features)

            # 计算持续时间
            prev = self.repository.fetch_latest_regime(symbol)
            if prev and prev["regime"] == price_regime:
                prev_time = datetime.fromisoformat(prev["as_of"])
                duration = int((datetime.now(timezone.utc) - prev_time).total_seconds() / 3600)
            else:
                duration = 0
                # 记录转换
                if prev and save:
                    self.repository.save_transition(
                        symbol, prev["regime"], price_regime, now_iso,
                        self._infer_triggers(features, prev["regime"], price_regime),
                        "sudden" if confidence > 0.7 else "gradual",
                    )

            # 计算转换概率
            history = self.repository.fetch_regime_history(symbol)
            transition_probs = self.classifier.compute_transition_probability(price_regime, history)

            if save:
                self.repository.save_regime_state(
                    symbol, price_regime, confidence, duration,
                    vol_regime, corr_regime, momentum_regime, now_iso,
                )

            results[symbol] = {
                "regime": price_regime,
                "confidence": round(confidence, 4),
                "duration_hours": duration,
                "volatility_regime": vol_regime,
                "correlation_regime": corr_regime,
                "momentum_regime": momentum_regime,
                "transition_probabilities": transition_probs,
            }

        return {"status": "ok", "as_of": now_iso, "results": results}

    def _build_features(self, symbol: str) -> RegimeFeatures | None:
        """从数据库构建分类特征。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            # 获取近期 kline 数据
            cursor = market_db.conn.execute("""
                SELECT close, volume FROM merged_klines
                WHERE entity_key = ? ORDER BY open_time DESC LIMIT 168
            """, (symbol,))
            rows = cursor.fetchall()
            if len(rows) < 20:
                return None

            closes = [r[0] for r in reversed(rows)]
            volumes = [r[1] for r in reversed(rows)]

            # 计算收益率
            returns = [(closes[i] - closes[i-1]) / closes[i-1]
                       for i in range(1, len(closes))]

            # 计算波动率（滚动 24h）
            volatility = []
            for i in range(24, len(returns)):
                window = returns[i-24:i]
                vol = (sum(r**2 for r in window) / len(window)) ** 0.5
                volatility.append(vol)

            # 成交量比率
            avg_vol = sum(volumes) / len(volumes) if volumes else 1
            vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1

            # 简化 RSI 计算
            gains = [r for r in returns[-14:] if r > 0]
            losses = [-r for r in returns[-14:] if r < 0]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_loss = sum(losses) / 14 if losses else 0.001
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            # 简化 ADX 计算（用方向性近似）
            up_moves = sum(1 for r in returns[-14:] if r > 0)
            adx = abs(up_moves - 7) / 7 * 50  # 粗略近似

            # BTC 相关性
            corr = self._compute_btc_correlation(symbol, market_db) if symbol != "BTC" else 1.0

            return RegimeFeatures(
                returns=returns[-48:],  # 最近 48h
                volatility=volatility[-24:] if volatility else [0],
                volume_ratio=vol_ratio,
                rsi=rsi,
                adx=adx,
                correlation_to_btc=corr,
            )
        except Exception as e:
            logger.debug(f"构建特征失败 [{symbol}]: {e}")
            return None

    def _compute_btc_correlation(self, symbol: str, market_db) -> float:
        """计算与 BTC 的相关性。"""
        try:
            cursor = market_db.conn.execute("""
                SELECT close FROM merged_klines
                WHERE entity_key = 'BTC' ORDER BY open_time DESC LIMIT 48
            """)
            btc_closes = [r[0] for r in reversed(cursor.fetchall())]

            cursor = market_db.conn.execute("""
                SELECT close FROM merged_klines
                WHERE entity_key = ? ORDER BY open_time DESC LIMIT 48
            """, (symbol,))
            sym_closes = [r[0] for r in reversed(cursor.fetchall())]

            if len(btc_closes) < 20 or len(sym_closes) < 20:
                return 0.5

            # 收益率
            n = min(len(btc_closes), len(sym_closes))
            btc_ret = [(btc_closes[i] - btc_closes[i-1]) / btc_closes[i-1] for i in range(1, n)]
            sym_ret = [(sym_closes[i] - sym_closes[i-1]) / sym_closes[i-1] for i in range(1, n)]

            # 皮尔逊相关系数
            n = len(btc_ret)
            mean_b = sum(btc_ret) / n
            mean_s = sum(sym_ret) / n
            cov = sum((btc_ret[i] - mean_b) * (sym_ret[i] - mean_s) for i in range(n)) / n
            std_b = (sum((r - mean_b)**2 for r in btc_ret) / n) ** 0.5
            std_s = (sum((r - mean_s)**2 for r in sym_ret) / n) ** 0.5
            if std_b == 0 or std_s == 0:
                return 0.0
            return cov / (std_b * std_s)
        except Exception:
            return 0.5

    @staticmethod
    def _infer_triggers(features: RegimeFeatures, from_regime: str, to_regime: str) -> str:
        """推断状态转换触发因素。"""
        triggers = []
        if to_regime == "crisis":
            triggers.append("drawdown_threshold")
        if features.volume_ratio > 2.0:
            triggers.append("volume_spike")
        if features.rsi > 70 or features.rsi < 30:
            triggers.append("rsi_extreme")
        if abs(features.correlation_to_btc) < 0.3:
            triggers.append("decorrelation")
        return ",".join(triggers) if triggers else "gradual_shift"

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的市场状态上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        all_regimes = self.repository.fetch_all_latest_regimes()
        if not all_regimes:
            return {"status": "no_data", "as_of": now_iso}

        # 按 symbol 过滤
        regime_map = {r["entity_key"]: r for r in all_regimes if r["entity_key"] in symbols}

        # 市场整体状态
        regimes = [r["regime"] for r in regime_map.values()]
        crisis_count = sum(1 for r in regimes if r == "crisis")
        trending_up_count = sum(1 for r in regimes if r == "trending_up")
        trending_down_count = sum(1 for r in regimes if r == "trending_down")

        if crisis_count >= len(regimes) * 0.3:
            market_phase = "crisis"
        elif trending_up_count >= len(regimes) * 0.5:
            market_phase = "bull_trend"
        elif trending_down_count >= len(regimes) * 0.5:
            market_phase = "bear_trend"
        else:
            market_phase = "mixed_ranging"

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_phase": market_phase,
            "market_summary": {
                "crisis_assets": crisis_count,
                "trending_up_assets": trending_up_count,
                "trending_down_assets": trending_down_count,
                "ranging_assets": sum(1 for r in regimes if r == "ranging"),
            },
            "entities": regime_map,
            "coverage": {
                "symbols_with_data": len(regime_map),
                "symbols_requested": len(symbols),
            },
        }

    def close(self):
        pass
