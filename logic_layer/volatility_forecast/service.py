"""volatility_forecast 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from logic_layer.volatility_forecast.calculator import VolatilityCalculator
from logic_layer.volatility_forecast.repository import VolatilityForecastRepository


TARGET_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "ARB", "OP"]
CONE_WINDOWS = [7, 14, 30, 60, 90]


class VolatilityForecastService:
    """波动率预测服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = VolatilityForecastRepository(self.db)
        self.calculator = VolatilityCalculator()

    def init_storage(self):
        self.repository.ensure_tables()
        logger.info("volatility_forecast 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_forecast(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行波动率预测。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        results = {}

        for symbol in symbols:
            snapshot = self._compute_for_symbol(symbol)
            if snapshot is None:
                continue
            results[symbol] = snapshot
            if save:
                self.repository.save_snapshot(symbol, snapshot, now_iso)
                # 计算波动率锥
                returns = self._fetch_returns(symbol, 180)
                if returns:
                    for window in CONE_WINDOWS:
                        cone = self.calculator.compute_volatility_cone(returns, window)
                        if cone:
                            self.repository.save_cone(symbol, cone, now_iso)

        return {"status": "ok", "as_of": now_iso, "results": results}

    def _compute_for_symbol(self, symbol: str) -> dict | None:
        """计算单个标的的波动率指标。"""
        returns = self._fetch_returns(symbol, 90)
        if not returns or len(returns) < 30:
            return None

        rv_1d = self.calculator.compute_realized_vol(returns, window=1)
        rv_7d = self.calculator.compute_realized_vol(returns, window=7)
        rv_30d = self.calculator.compute_realized_vol(returns, window=30)
        forecast_1d = self.calculator.compute_ewma_forecast(returns, horizon_days=1)
        forecast_7d = self.calculator.compute_ewma_forecast(returns, horizon_days=7)
        vol_percentile = self.calculator.compute_vol_percentile(returns, window=30)
        vol_regime = self.calculator.classify_vol_regime(rv_30d)

        # 尝试获取隐含波动率
        iv = self._fetch_implied_vol(symbol)
        rv_iv_spread = rv_30d - iv if iv > 0 else 0.0

        return {
            "realized_vol_1d": rv_1d,
            "realized_vol_7d": rv_7d,
            "realized_vol_30d": rv_30d,
            "implied_vol": iv,
            "rv_iv_spread": round(rv_iv_spread, 6),
            "vol_regime": vol_regime,
            "forecast_1d": forecast_1d,
            "forecast_7d": forecast_7d,
            "vol_percentile": vol_percentile,
        }

    def _fetch_returns(self, symbol: str, days: int) -> list[float]:
        """从市场数据库获取收益率序列。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
            cursor = market_db.conn.execute("""
                SELECT close FROM merged_klines
                WHERE entity_key = ? ORDER BY open_time DESC LIMIT ?
            """, (symbol, days * 24))
            rows = cursor.fetchall()
            if len(rows) < 20:
                return []
            closes = [r[0] for r in reversed(rows)]
            return [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        except Exception as e:
            logger.debug(f"获取收益率失败 [{symbol}]: {e}")
            return []

    def _fetch_implied_vol(self, symbol: str) -> float:
        """尝试从期权数据获取隐含波动率。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
            cursor = market_db.conn.execute("""
                SELECT atm_iv FROM options_vol_surface
                WHERE entity_key = ? ORDER BY collected_at DESC LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的波动率预测上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        snapshots = self.repository.fetch_latest_snapshots()
        if not snapshots:
            return {"status": "no_data", "as_of": now_iso}

        filtered = {s["entity_key"]: s for s in snapshots if s["entity_key"] in symbols}

        # 市场波动率概览
        vol_regimes = [s["vol_regime"] for s in filtered.values()]
        extreme_count = sum(1 for v in vol_regimes if v == "extreme")
        high_count = sum(1 for v in vol_regimes if v == "high")

        if extreme_count >= 3:
            market_vol_state = "crisis_volatility"
        elif high_count >= len(vol_regimes) * 0.5:
            market_vol_state = "elevated"
        else:
            market_vol_state = "normal"

        # 波动率锥（仅 BTC）
        btc_cone = self.repository.fetch_cone_data("BTC")

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_volatility_state": market_vol_state,
            "summary": {
                "extreme_vol_assets": extreme_count,
                "high_vol_assets": high_count,
                "avg_rv_30d": round(
                    sum(s["realized_vol_30d"] for s in filtered.values()) / max(len(filtered), 1), 4
                ),
            },
            "entities": filtered,
            "btc_volatility_cone": btc_cone,
            "coverage": {
                "symbols_with_data": len(filtered),
                "symbols_requested": len(symbols),
            },
        }

    def close(self):
        pass
