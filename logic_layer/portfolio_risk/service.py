"""组合风险分析服务：编排波动率、集中度、分散化计算。"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from config.symbols import (
    SECTOR_DEFINITIONS,
    SYMBOL_UNIVERSE,
    TARGET_SYMBOLS,
    get_symbol_sector,
)
from database.db_manager import DBManager
from logic_layer.portfolio_risk.calculator import PortfolioRiskCalculator
from logic_layer.portfolio_risk.repository import PortfolioRiskRepository


class PortfolioRiskService:
    """组合风险分析编排服务。

    职责：
    - 从跨资产模块获取相关性矩阵
    - 从 merged_klines 计算各资产波动率
    - 调用 calculator 计算组合风险指标
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = PortfolioRiskRepository(self.db)
        self.calculator = PortfolioRiskCalculator()

    def init_storage(self):
        """创建组合风险所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    def _load_volatilities(self) -> dict[str, float]:
        """从 merged_klines 1h 计算各资产日波动率。"""
        rows = self.db.fetch_all(
            """SELECT symbol, close, open_time
               FROM merged_klines
               WHERE timeframe = '1h'
               ORDER BY symbol, open_time DESC""",
            (),
        )
        # 按 symbol 分组，取最近 168 根（7天）
        series: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for row in rows:
            sym = row["symbol"]
            if counts.get(sym, 0) >= 168:
                continue
            series.setdefault(sym, []).append(float(row["close"]))
            counts[sym] = counts.get(sym, 0) + 1

        volatilities: dict[str, float] = {}
        for sym, prices in series.items():
            prices.reverse()
            if len(prices) < 2:
                continue
            log_rets = [
                math.log(prices[i] / prices[i - 1])
                for i in range(1, len(prices))
                if prices[i - 1] > 0
            ]
            if not log_rets:
                continue
            mean_r = sum(log_rets) / len(log_rets)
            var = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
            # 1h vol → daily vol (sqrt(24))
            hourly_vol = math.sqrt(var)
            daily_vol = hourly_vol * math.sqrt(24)
            volatilities[sym] = daily_vol
        return volatilities

    def _load_correlation_matrix(self) -> dict[str, dict[str, float]] | None:
        """从跨资产模块加载最新相关性矩阵。"""
        from logic_layer.cross_asset_analysis.repository import CrossAssetRepository
        repo = CrossAssetRepository(self.db)
        result = repo.load_latest_correlation(window_hours=168)
        if not result:
            return None
        return result.get("matrix")

    def _default_equal_weights(self, symbols: list[str]) -> dict[str, float]:
        """生成等权权重。"""
        n = len(symbols)
        if n == 0:
            return {}
        w = round(1.0 / n, 6)
        return {s: w for s in symbols}

    # ------------------------------------------------------------------
    # 主计算
    # ------------------------------------------------------------------

    def compute_risk(
        self,
        weights: dict[str, float] | None = None,
        portfolio_name: str = "default",
    ) -> dict | None:
        """计算组合风险指标并落库。

        Parameters
        ----------
        weights : dict[str, float] | None
            {symbol: weight}，为 None 时使用等权
        portfolio_name : str
            组合名称标识
        """
        correlation_matrix = self._load_correlation_matrix()
        volatilities = self._load_volatilities()

        if not volatilities:
            return None

        # 确定可用 symbols（同时有波动率和相关性数据）
        available = set(volatilities.keys())
        if correlation_matrix:
            available &= set(correlation_matrix.keys())
        available_symbols = sorted(available)

        if len(available_symbols) < 2:
            return None

        # 权重
        if weights is None:
            weights = self._default_equal_weights(available_symbols)
        else:
            # 过滤掉没有数据的 symbol
            weights = {s: w for s, w in weights.items() if s in available}
            if not weights:
                weights = self._default_equal_weights(available_symbols)

        # 构建协方差矩阵
        if correlation_matrix:
            cov_matrix = self.calculator.build_covariance_matrix(
                correlation_matrix, volatilities
            )
        else:
            # 无相关性数据时假设不相关
            cov_matrix = {
                si: {
                    sj: (volatilities[si] ** 2 if si == sj else 0.0)
                    for sj in weights
                }
                for si in weights
            }

        # 计算组合波动率
        vol_result = self.calculator.compute_portfolio_volatility(weights, cov_matrix)

        # 计算集中度
        concentration = self.calculator.compute_concentration(weights)

        # 计算分散化比率
        div_ratio = self.calculator.compute_diversification_ratio(
            weights, volatilities, vol_result["portfolio_vol_daily"]
        )

        # 板块集中度
        sector_weights: dict[str, float] = {}
        for sym, w in weights.items():
            sector = get_symbol_sector(sym) or "unknown"
            sector_weights[sector] = sector_weights.get(sector, 0) + w

        snapshot = {
            "snapshot_time": self._utc_now_iso(),
            "portfolio_name": portfolio_name,
            "asset_count": len(weights),
            "weights": weights,
            "annualized_volatility": vol_result["annualized_vol"],
            "daily_var_95": vol_result["var_95"],
            "daily_var_99": vol_result["var_99"],
            "hhi": concentration["hhi"],
            "effective_n": concentration["effective_n"],
            "max_weight": concentration["max_weight"],
            "diversification_ratio": div_ratio,
            "risk_contributions": vol_result["risk_contributions"],
            "sector_concentration": sector_weights,
        }

        self.repository.save_snapshot(snapshot)
        return snapshot

    def load_latest_context_bundle(self) -> dict:
        """加载最新组合风险快照，供 AI 上下文消费。"""
        snapshot = self.repository.load_latest_snapshot()
        if not snapshot:
            return {
                "as_of": self._utc_now_iso(),
                "status": "no_data",
            }
        return {
            "as_of": self._utc_now_iso(),
            "status": "ready",
            "portfolio_name": snapshot["portfolio_name"],
            "asset_count": snapshot["asset_count"],
            "annualized_volatility": snapshot["annualized_volatility"],
            "daily_var_95": snapshot["daily_var_95"],
            "daily_var_99": snapshot["daily_var_99"],
            "hhi": snapshot["hhi"],
            "effective_n": snapshot["effective_n"],
            "max_weight": snapshot["max_weight"],
            "diversification_ratio": snapshot["diversification_ratio"],
            "sector_concentration": snapshot["sector_concentration"],
            "top_risk_contributors": self._top_risk_contributors(
                snapshot["risk_contributions"]
            ),
        }

    @staticmethod
    def _top_risk_contributors(
        risk_contributions: dict[str, float], top_n: int = 5
    ) -> list[dict]:
        """返回风险贡献最大的 N 个资产。"""
        sorted_items = sorted(
            risk_contributions.items(), key=lambda x: abs(x[1]), reverse=True
        )
        return [
            {"symbol": sym, "risk_contribution": rc}
            for sym, rc in sorted_items[:top_n]
        ]

    def close(self):
        self.db.close()
