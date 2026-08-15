"""funding_rate_model 服务层。"""

import statistics
from datetime import datetime, timezone

from loguru import logger

from logic_layer.funding_rate_model.calculator import FundingRateCalculator
from logic_layer.funding_rate_model.repository import FundingRateModelRepository


from config.symbols import TARGET_ASSET_CODES

TARGET_SYMBOLS = TARGET_ASSET_CODES


class FundingRateModelService:
    """资金费率模型服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = FundingRateModelRepository(self.db)
        self.calculator = FundingRateCalculator()

    def init_storage(self):
        self.repository.ensure_tables()
        logger.info("funding_rate_model 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_model(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行资金费率建模。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        funding_results = {}
        basis_results = {}

        for symbol in symbols:
            fr = self._model_funding(symbol)
            if fr:
                funding_results[symbol] = fr
                if save:
                    self.repository.save_funding_snapshot(symbol, fr, now_iso)

            br = self._model_basis(symbol)
            if br:
                basis_results[symbol] = br
                if save:
                    self.repository.save_basis_snapshot(symbol, br, now_iso)

        return {
            "status": "ok",
            "as_of": now_iso,
            "funding": funding_results,
            "basis": basis_results,
        }

    def _model_funding(self, symbol: str) -> dict | None:
        """建模单个标的的 funding rate。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            cursor = market_db.conn.execute("""
                SELECT funding_rate FROM latest_funding_rates
                WHERE entity_key = ? ORDER BY collected_at DESC LIMIT 100
            """, (symbol,))
            rows = cursor.fetchall()
            if len(rows) < 10:
                return None

            rates = [r[0] for r in reversed(rows)]
            current = rates[-1]

            return {
                "current_rate": current,
                "predicted_next": self.calculator.predict_next_funding(rates),
                "rate_zscore": self.calculator.compute_rate_zscore(rates),
                "rate_percentile": self.calculator.compute_rate_percentile(rates),
                "cumulative_7d": self.calculator.compute_cumulative_funding(rates),
                "direction_bias": self.calculator.classify_direction_bias(current),
                "mean_reversion_signal": self.calculator.compute_mean_reversion_signal(rates),
            }
        except Exception as e:
            logger.debug(f"Funding 建模失败 [{symbol}]: {e}")
            return None

    def _model_basis(self, symbol: str) -> dict | None:
        """建模单个标的的期现基差。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            # 获取现货和期货价格
            cursor = market_db.conn.execute("""
                SELECT last_price FROM latest_tickers
                WHERE entity_key = ? AND market_type = 'spot'
                ORDER BY collected_at DESC LIMIT 1
            """, (symbol,))
            spot_row = cursor.fetchone()

            cursor = market_db.conn.execute("""
                SELECT last_price FROM latest_tickers
                WHERE entity_key = ? AND market_type = 'futures'
                ORDER BY collected_at DESC LIMIT 1
            """, (symbol,))
            futures_row = cursor.fetchone()

            if not spot_row or not futures_row:
                return None

            spot = float(spot_row[0])
            futures = float(futures_row[0])
            if spot <= 0:
                return None

            basis_pct = self.calculator.compute_basis(spot, futures)
            annualized = self.calculator.compute_annualized_basis(basis_pct)
            regime = self.calculator.classify_basis_regime(basis_pct)

            # 获取历史基差
            cursor = market_db.conn.execute("""
                SELECT basis_pct FROM latest_basis
                WHERE entity_key = ? ORDER BY collected_at DESC LIMIT 50
            """, (symbol,))
            basis_rows = cursor.fetchall()
            basis_history = [r[0] for r in reversed(basis_rows)] if basis_rows else [basis_pct]

            basis_zscore = 0.0
            if len(basis_history) >= 10:
                mean = statistics.mean(basis_history[:-1])
                std = statistics.stdev(basis_history[:-1])
                if std > 0:
                    basis_zscore = round((basis_pct - mean) / std, 4)

            mr_signal = self.calculator.compute_basis_mean_reversion(basis_history)

            return {
                "spot_price": spot,
                "futures_price": futures,
                "basis_pct": basis_pct,
                "basis_zscore": basis_zscore,
                "annualized_basis": annualized,
                "basis_regime": regime,
                "mean_reversion_signal": mr_signal,
            }
        except Exception as e:
            logger.debug(f"Basis 建模失败 [{symbol}]: {e}")
            return None

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的资金费率模型上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        funding_data = self.repository.fetch_latest_funding()
        basis_data = self.repository.fetch_latest_basis()

        if not funding_data and not basis_data:
            return {"status": "no_data", "as_of": now_iso}

        filtered_funding = {f["entity_key"]: f for f in funding_data if f["entity_key"] in symbols}
        filtered_basis = {b["entity_key"]: b for b in basis_data if b["entity_key"] in symbols}

        # 市场信号
        long_crowded = [k for k, v in filtered_funding.items() if v["direction_bias"] == "long_crowded"]
        short_crowded = [k for k, v in filtered_funding.items() if v["direction_bias"] == "short_crowded"]
        strong_mr_signals = [
            k for k, v in filtered_funding.items()
            if abs(v["mean_reversion_signal"]) > 0.5
        ]

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_positioning": {
                "long_crowded_assets": long_crowded,
                "short_crowded_assets": short_crowded,
                "strong_mean_reversion_signals": strong_mr_signals,
                "overall_bias": "long" if len(long_crowded) > len(short_crowded) else
                               "short" if len(short_crowded) > len(long_crowded) else "balanced",
            },
            "funding": filtered_funding,
            "basis": filtered_basis,
            "coverage": {
                "funding_symbols": len(filtered_funding),
                "basis_symbols": len(filtered_basis),
                "symbols_requested": len(symbols),
            },
        }

    def close(self):
        pass
