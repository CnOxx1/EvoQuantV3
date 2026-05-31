"""liquidity_analysis 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from logic_layer.liquidity_analysis.calculator import LiquidityCalculator
from logic_layer.liquidity_analysis.repository import LiquidityAnalysisRepository


TARGET_SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK", "ARB", "OP"]


class LiquidityAnalysisService:
    """流动性分析服务。"""

    def __init__(self, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = LiquidityAnalysisRepository(self.db)
        self.calculator = LiquidityCalculator()

    def init_storage(self):
        self.repository.ensure_tables()
        logger.info("liquidity_analysis 存储初始化完成")

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def run_analysis(self, symbols: list[str] | None = None, save: bool = True) -> dict:
        """执行流动性分析。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()
        results = {}
        all_alerts = []

        for symbol in symbols:
            profile = self._analyze_symbol(symbol)
            if profile is None:
                continue

            results[symbol] = profile

            if save:
                self.repository.save_profile(symbol, profile.get("exchange", "binance"), profile, now_iso)

            # 检测预警
            historical_depth = self.repository.fetch_historical_depth(symbol)
            alerts = self.calculator.detect_alerts(
                symbol, profile["spread_bps"],
                profile["bid_depth_usd"], profile["ask_depth_usd"],
                historical_depth,
            )
            for alert in alerts:
                all_alerts.append({"entity_key": symbol, **alert})
                if save:
                    self.repository.save_alert(symbol, alert, now_iso)

        return {
            "status": "ok",
            "as_of": now_iso,
            "profiles": results,
            "alerts": all_alerts,
            "symbols_analyzed": len(results),
        }

    def _analyze_symbol(self, symbol: str) -> dict | None:
        """分析单个标的的流动性。"""
        try:
            from database.router import DatabaseRouter, Domain
            market_db = DatabaseRouter().get_manager(Domain.MARKET_DATA)

            # 获取订单簿数据
            cursor = market_db.conn.execute("""
                SELECT best_bid, best_ask, bid_depth_2pct, ask_depth_2pct
                FROM latest_orderbook_snapshot
                WHERE entity_key = ?
                ORDER BY collected_at DESC LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            if not row:
                return None

            best_bid, best_ask = float(row[0] or 0), float(row[1] or 0)
            bid_depth = float(row[2] or 0)
            ask_depth = float(row[3] or 0)

            if best_bid <= 0 or best_ask <= 0:
                return None

            spread_bps = self.calculator.compute_spread_bps(best_bid, best_ask)
            score = self.calculator.compute_liquidity_score(spread_bps, bid_depth, ask_depth)

            # 简化滑点估算（基于深度线性模型）
            total_depth = bid_depth + ask_depth
            slippage_10k = spread_bps + (10_000 / max(total_depth, 1)) * 10 if total_depth > 0 else 999
            slippage_100k = spread_bps + (100_000 / max(total_depth, 1)) * 10 if total_depth > 0 else 999
            slippage_1m = spread_bps + (1_000_000 / max(total_depth, 1)) * 10 if total_depth > 0 else 999

            return {
                "exchange": "binance",
                "bid_depth_usd": round(bid_depth, 2),
                "ask_depth_usd": round(ask_depth, 2),
                "spread_bps": round(spread_bps, 2),
                "slippage_10k_bps": round(min(slippage_10k, 999), 2),
                "slippage_100k_bps": round(min(slippage_100k, 999), 2),
                "slippage_1m_bps": round(min(slippage_1m, 999), 2),
                "liquidity_score": score,
            }
        except Exception as e:
            logger.debug(f"流动性分析失败 [{symbol}]: {e}")
            return None

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的流动性分析上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = self._utc_now_iso()

        profiles = self.repository.fetch_latest_profiles()
        alerts = self.repository.fetch_recent_alerts(hours=24)

        if not profiles:
            return {"status": "no_data", "as_of": now_iso}

        # 过滤目标 symbols
        filtered_profiles = {p["entity_key"]: p for p in profiles if p["entity_key"] in symbols}
        filtered_alerts = [a for a in alerts if a["entity_key"] in symbols]

        # 市场流动性概览
        scores = [p["liquidity_score"] for p in filtered_profiles.values()]
        avg_score = sum(scores) / len(scores) if scores else 0
        critical_alerts = [a for a in filtered_alerts if a["severity"] == "critical"]

        if avg_score < 30 or len(critical_alerts) >= 3:
            market_liquidity = "stressed"
        elif avg_score < 60 or len(critical_alerts) >= 1:
            market_liquidity = "tight"
        else:
            market_liquidity = "healthy"

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_liquidity_state": market_liquidity,
            "avg_liquidity_score": round(avg_score, 1),
            "profiles": filtered_profiles,
            "active_alerts": filtered_alerts,
            "coverage": {
                "symbols_with_data": len(filtered_profiles),
                "symbols_requested": len(symbols),
                "active_alert_count": len(filtered_alerts),
            },
        }

    def close(self):
        pass
