"""传染风险服务：编排 CoVaR、条件相关性、尾部 Beta、级联风险计算。"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from config.symbols import TARGET_SYMBOLS
from database.db_manager import DBManager
from logic_layer.contagion_risk.calculator import ContagionRiskCalculator
from logic_layer.contagion_risk.repository import ContagionRiskRepository


class ContagionRiskService:
    """传染风险编排服务。

    职责：
    - 从 merged_klines 读取收益率序列
    - 调用 calculator 计算 CoVaR、条件相关性、尾部 Beta
    - 评估级联风险（DeFi 级联、交易所传染、稳定币脱锚）
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = ContagionRiskRepository(self.db)
        self.calculator = ContagionRiskCalculator()

    def init_storage(self):
        """创建传染风险分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_returns(
        self, symbols: list[str], window_hours: int = 168
    ) -> dict[str, list[float]]:
        """从 merged_klines 加载收益率序列。

        Parameters
        ----------
        symbols : list[str]
            目标交易对列表
        window_hours : int
            回溯窗口（小时数，默认 168 = 7 天）

        Returns
        -------
        dict[str, list[float]]
            {symbol: [hourly_returns...]}
        """
        placeholders = ",".join("?" for _ in symbols)
        rows = self.db.fetch_all(
            f"""SELECT symbol, close, open_time
               FROM merged_klines
               WHERE timeframe = '1h' AND symbol IN ({placeholders})
               ORDER BY symbol, open_time DESC""",
            tuple(symbols),
        )
        # 按 symbol 分组，取最近 window_hours 根
        series: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for row in rows:
            sym = row["symbol"]
            if counts.get(sym, 0) >= window_hours:
                continue
            series.setdefault(sym, []).append(float(row["close"]))
            counts[sym] = counts.get(sym, 0) + 1
        # 反转为时间正序
        for sym in series:
            series[sym].reverse()

        # 转换为收益率
        returns: dict[str, list[float]] = {}
        for sym, prices in series.items():
            if len(prices) < 2:
                continue
            rets = [
                (prices[i] / prices[i - 1]) - 1.0
                for i in range(1, len(prices))
                if prices[i - 1] > 0
            ]
            if rets:
                returns[sym] = rets
        return returns

    def _load_stablecoin_prices(self) -> dict[str, float]:
        """从 merged_klines 加载稳定币最新价格。

        Returns
        -------
        dict[str, float]
            {symbol: latest_close_price}
        """
        stablecoins = ["USDT/USD", "USDC/USD", "DAI/USD", "BUSD/USD"]
        placeholders = ",".join("?" for _ in stablecoins)
        rows = self.db.fetch_all(
            f"""SELECT symbol, close
               FROM merged_klines
               WHERE symbol IN ({placeholders}) AND timeframe = '1h'
               ORDER BY open_time DESC""",
            tuple(stablecoins),
        )
        prices: dict[str, float] = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in prices:
                prices[sym] = float(row["close"])
        return prices

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_contagion(self, symbols: list[str] | None = None) -> dict:
        """计算传染风险指标并落库。

        Parameters
        ----------
        symbols : list[str] | None
            目标交易对列表，默认使用 TARGET_SYMBOLS

        Returns
        -------
        dict
            包含 metrics 列表和 systemic_score 的结果
        """
        if symbols is None:
            symbols = list(TARGET_SYMBOLS)

        returns = self._load_returns(symbols)
        if len(returns) < 2:
            return {"metrics": [], "systemic_score": 0.0}

        ts = self._utc_now_iso()
        # 使用 BTC/USDT 作为市场基准
        market_sym = "BTC/USDT"
        market_returns = returns.get(market_sym, [])

        entries: list[dict] = []
        for sym, rets in returns.items():
            if sym == market_sym or not market_returns:
                covar = 0.0
                cond_corr = 0.0
                tail_beta = 0.0
            else:
                covar = self.calculator.compute_covar(rets, market_returns)
                cond_corr = self.calculator.compute_conditional_correlation(
                    market_returns, rets
                )
                tail_beta = self.calculator.compute_tail_beta(
                    rets, market_returns
                )

            entry = {
                "ts": ts,
                "symbol": sym,
                "covar_95": covar,
                "conditional_correlation": cond_corr,
                "tail_beta": tail_beta,
                "systemic_contribution": abs(covar) * abs(cond_corr),
            }
            entries.append(entry)

        systemic_score = self.calculator.compute_systemic_risk_score(entries)
        self.repository.save_contagion_metrics(entries)

        return {
            "ts": ts,
            "metrics": entries,
            "systemic_score": systemic_score,
            "symbol_count": len(entries),
        }

    def compute_cascade_risk(self) -> list[dict]:
        """评估级联风险场景并落库。

        评估三类级联风险：
        - defi_cascade: DeFi 协议级联清算风险
        - exchange_contagion: 交易所传染风险
        - stablecoin_depeg: 稳定币脱锚风险

        Returns
        -------
        list[dict]
            级联风险评估列表
        """
        ts = self._utc_now_iso()
        entries: list[dict] = []

        # 1. DeFi 级联风险 - 基于尾部相关性
        symbols = list(TARGET_SYMBOLS)
        returns = self._load_returns(symbols)
        if len(returns) >= 2:
            # 计算平均条件相关性作为级联风险代理
            market_returns = returns.get("BTC/USDT", [])
            cond_corrs = []
            for sym, rets in returns.items():
                if sym == "BTC/USDT" or not market_returns:
                    continue
                cc = self.calculator.compute_conditional_correlation(
                    market_returns, rets
                )
                cond_corrs.append(abs(cc))
            avg_cond_corr = (
                sum(cond_corrs) / len(cond_corrs) if cond_corrs else 0.0
            )
            defi_risk = min(avg_cond_corr * 100.0, 100.0)
            affected = [s for s in returns.keys() if s != "BTC/USDT"]
            entries.append({
                "ts": ts,
                "risk_type": "defi_cascade",
                "risk_level": round(defi_risk, 2),
                "affected_assets": json.dumps(affected[:10]),
                "trigger_conditions": json.dumps({
                    "avg_conditional_correlation": round(avg_cond_corr, 4),
                    "threshold": 0.7,
                    "triggered": avg_cond_corr > 0.7,
                }),
            })

        # 2. 交易所传染风险 - 基于 CoVaR
        if len(returns) >= 2:
            market_returns = returns.get("BTC/USDT", [])
            covars = []
            for sym, rets in returns.items():
                if sym == "BTC/USDT" or not market_returns:
                    continue
                cv = self.calculator.compute_covar(rets, market_returns)
                covars.append(abs(cv))
            avg_covar = sum(covars) / len(covars) if covars else 0.0
            # 归一化到 0-100
            exchange_risk = min(avg_covar / 0.1 * 100.0, 100.0)
            entries.append({
                "ts": ts,
                "risk_type": "exchange_contagion",
                "risk_level": round(exchange_risk, 2),
                "affected_assets": json.dumps(list(returns.keys())[:10]),
                "trigger_conditions": json.dumps({
                    "avg_covar": round(avg_covar, 6),
                    "threshold": 0.05,
                    "triggered": avg_covar > 0.05,
                }),
            })

        # 3. 稳定币脱锚风险
        stablecoin_prices = self._load_stablecoin_prices()
        if stablecoin_prices:
            depeg_probs = {}
            for sym, price in stablecoin_prices.items():
                prob = self.calculator.compute_stablecoin_depeg_probability(
                    price=price, peg=1.0, volatility=0.01
                )
                depeg_probs[sym] = prob
            max_prob = max(depeg_probs.values()) if depeg_probs else 0.0
            depeg_risk = max_prob * 100.0
            entries.append({
                "ts": ts,
                "risk_type": "stablecoin_depeg",
                "risk_level": round(depeg_risk, 2),
                "affected_assets": json.dumps(list(stablecoin_prices.keys())),
                "trigger_conditions": json.dumps({
                    "depeg_probabilities": depeg_probs,
                    "max_probability": round(max_prob, 4),
                    "threshold": 0.1,
                    "triggered": max_prob > 0.1,
                }),
            })

        if entries:
            self.repository.save_cascade_risk(entries)
        return entries

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部传染风险分析计算并落库。"""
        results: dict = {}
        results["contagion"] = self.compute_contagion()
        results["cascade_risk"] = self.compute_cascade_risk()
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新传染风险分析结果，供 AI 上下文消费。"""
        metrics = self.repository.load_latest_metrics()
        cascade = self.repository.load_latest_cascade_risk()
        systemic_score = self.calculator.compute_systemic_risk_score(metrics)
        return {
            "as_of": self._utc_now_iso(),
            "contagion_metrics": metrics,
            "cascade_risk": cascade,
            "systemic_risk_score": systemic_score,
            "risk_regime": self._classify_risk_regime(systemic_score),
        }

    @staticmethod
    def _classify_risk_regime(score: float) -> str:
        """根据系统性风险评分判定风险 regime。"""
        if score >= 75:
            return "critical"
        elif score >= 50:
            return "elevated"
        elif score >= 25:
            return "moderate"
        else:
            return "low"

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
