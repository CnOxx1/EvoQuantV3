"""跨场所套利服务：编排 CEX/DEX 间套利检测、持续性分析、市场效率评估。"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from itertools import combinations

from loguru import logger

from database.db_manager import DBManager
from logic_layer.cross_venue_arbitrage.calculator import CrossVenueArbCalculator
from logic_layer.cross_venue_arbitrage.repository import CrossVenueArbRepository


class CrossVenueArbService:
    """跨场所套利编排服务。

    职责：
    - 从 exchange_data 读取各场所最新价格
    - 调用 calculator 计算价差、检测套利、分析持续性
    - 评估市场效率
    - 通过 repository 落库
    """

    SYMBOLS: list[str] = [
        "BTC", "ETH", "SOL", "DOGE", "XRP", "ARB", "OP", "AVAX",
    ]
    VENUES: list[str] = [
        "binance", "okx", "bybit", "dydx", "hyperliquid",
    ]

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = CrossVenueArbRepository(self.db)
        self.calculator = CrossVenueArbCalculator()

    def init_storage(self):
        """创建跨场所套利分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_venue_prices(self, symbol: str) -> list[dict]:
        """从 exchange_data 加载各场所最新价格。

        Parameters
        ----------
        symbol : str
            交易对基础资产（如 BTC）

        Returns
        -------
        list[dict]
            每个元素包含 venue, price 字段
        """
        results = []
        for venue in self.VENUES:
            # 尝试从 merged_klines 查询各场所最新价格
            pair = f"{symbol}/USDT"
            rows = self.db.fetch_all(
                """SELECT close, exchange AS source
                   FROM klines
                   WHERE symbol = ? AND exchange LIKE ?
                   ORDER BY open_time DESC LIMIT 1""",
                (pair, f"%{venue}%"),
            )
            if rows:
                price = float(rows[0]["close"])
                if price > 0:
                    results.append({
                        "venue": venue,
                        "price": price,
                    })
        # 如果 merged_klines 无数据，尝试 ticker 表
        if not results:
            for venue in self.VENUES:
                pair = f"{symbol}/USDT"
                rows = self.db.fetch_all(
                    """SELECT last_price
                       FROM tickers
                       WHERE symbol = ? AND exchange = ?
                       ORDER BY ts DESC LIMIT 1""",
                    (pair, venue),
                )
                if rows and rows[0]["last_price"]:
                    results.append({
                        "venue": venue,
                        "price": float(rows[0]["last_price"]),
                    })
        return results

    def _load_price_history(
        self, symbol: str, venue: str, hours: int = 1
    ) -> list[float]:
        """加载指定场所的历史价格序列。

        Parameters
        ----------
        symbol : str
            交易对基础资产
        venue : str
            场所名称
        hours : int
            回溯小时数，默认 1

        Returns
        -------
        list[float]
            价格序列（时间正序）
        """
        pair = f"{symbol}/USDT"
        limit = hours * 60  # 假设 1 分钟粒度
        rows = self.db.fetch_all(
            """SELECT close
               FROM klines
               WHERE symbol = ? AND exchange LIKE ?
               ORDER BY open_time DESC
               LIMIT ?""",
            (pair, f"%{venue}%", limit),
        )
        if not rows:
            return []
        prices = [float(r["close"]) for r in rows if r["close"]]
        prices.reverse()
        return prices

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部跨场所套利分析并落库。"""
        ts = self._utc_now_iso()
        all_opportunities: list[dict] = []
        all_spreads: list[dict] = []
        all_persistence: list[dict] = []

        for symbol in self.SYMBOLS:
            logger.info("分析跨场所套利: {}", symbol)
            prices = self._load_venue_prices(symbol)
            if len(prices) < 2:
                logger.debug("{} 场所价格不足，跳过", symbol)
                continue

            # 检测套利机会
            arbs = self.calculator.detect_arbitrage(prices)
            for arb in arbs:
                profit = self.calculator.estimate_profit(
                    arb["spread_bps"], 100000.0
                )
                entry = {
                    "ts": ts,
                    "symbol": symbol,
                    "venue_buy": arb["venue_buy"],
                    "venue_sell": arb["venue_sell"],
                    "price_buy": arb["price_buy"],
                    "price_sell": arb["price_sell"],
                    "spread_bps": arb["spread_bps"],
                    "estimated_profit_usd": profit,
                    "latency_ms": 0,
                }
                all_opportunities.append(entry)

            # 计算场所间价差
            for i, j in combinations(range(len(prices)), 2):
                pa = prices[i]
                pb = prices[j]
                spread = self.calculator.compute_spread_bps(
                    pa["price"], pb["price"]
                )
                cross = 1 if spread > 0 and pa["price"] != pb["price"] else 0
                all_spreads.append({
                    "ts": ts,
                    "symbol": symbol,
                    "venue_a": pa["venue"],
                    "venue_b": pb["venue"],
                    "mid_spread_bps": spread,
                    "bid_ask_cross": cross,
                })

            # 持续性分析
            self._compute_persistence_for_symbol(
                symbol, prices, ts, all_persistence
            )

        # 落库
        if all_opportunities:
            self.repository.save_opportunities(all_opportunities)
        if all_spreads:
            self.repository.save_spreads(all_spreads)
        if all_persistence:
            self.repository.save_persistence(all_persistence)

        efficiency = self.calculator.compute_market_efficiency_score(
            all_opportunities
        )
        logger.info(
            "跨场所套利分析完成: {} 个机会, 效率评分 {}",
            len(all_opportunities), efficiency,
        )
        return {
            "ts": ts,
            "opportunities_count": len(all_opportunities),
            "spreads_count": len(all_spreads),
            "persistence_count": len(all_persistence),
            "market_efficiency_score": efficiency,
        }

    def _compute_persistence_for_symbol(
        self, symbol: str, prices: list[dict],
        ts: str, results: list[dict],
    ):
        """为单个 symbol 计算套利持续性。"""
        if len(prices) < 2:
            return
        # 构建历史价差记录用于持续性分析
        spreads_history: list[dict] = []
        for i, j in combinations(range(len(prices)), 2):
            pa = prices[i]
            pb = prices[j]
            venue_pair = f"{pa['venue']}_{pb['venue']}"
            # 加载两个场所的历史价格
            hist_a = self._load_price_history(symbol, pa["venue"])
            hist_b = self._load_price_history(symbol, pb["venue"])
            n = min(len(hist_a), len(hist_b))
            if n < 2:
                continue
            for k in range(n):
                spread = self.calculator.compute_spread_bps(
                    hist_a[k], hist_b[k]
                )
                if spread > 0:
                    spreads_history.append({
                        "venue_pair": venue_pair,
                        "spread_bps": spread,
                        "timestamp_epoch": k * 60,
                    })

        persistence = self.calculator.compute_persistence(spreads_history)
        for p in persistence:
            results.append({
                "ts": ts,
                "symbol": symbol,
                "venue_pair": p["venue_pair"],
                "avg_spread_bps": p["avg_spread_bps"],
                "duration_seconds": p["duration_seconds"],
                "frequency_per_hour": p["frequency_per_hour"],
            })

    # ------------------------------------------------------------------
    # 上下文输出
    # ------------------------------------------------------------------

    def load_latest_context_bundle(self) -> dict:
        """加载最新跨场所套利分析结果，供 AI 上下文消费。"""
        opportunities = self.repository.load_latest_opportunities()
        persistence = self.repository.load_latest_persistence()
        efficiency = self.calculator.compute_market_efficiency_score(
            opportunities
        )
        # 筛选持续性较强的低效场所对
        persistent_inefficiencies = [
            p for p in persistence
            if p.get("avg_spread_bps", 0) > 5.0
            and p.get("frequency_per_hour", 0) > 2.0
        ]
        return {
            "as_of": self._utc_now_iso(),
            "active_arb_opportunities": opportunities,
            "market_efficiency_score": efficiency,
            "persistent_inefficiencies": persistent_inefficiencies,
            "summary": {
                "total_opportunities": len(opportunities),
                "efficiency_regime": self._classify_efficiency(efficiency),
            },
        }

    @staticmethod
    def _classify_efficiency(score: float) -> str:
        """根据效率评分判定市场效率 regime。"""
        if score >= 90:
            return "highly_efficient"
        elif score >= 70:
            return "efficient"
        elif score >= 50:
            return "moderate"
        else:
            return "inefficient"

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
