"""代币解锁冲击服务：编排卖压比率、冲击评分、价格影响、流动性吸收计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.unlock_impact.calculator import UnlockImpactCalculator
from logic_layer.unlock_impact.repository import UnlockImpactRepository


class UnlockImpactService:
    """代币解锁冲击编排服务。

    职责：
    - 从 token_unlocks、klines 读取市场数据
    - 调用 calculator 计算卖压比率、冲击评分、价格影响
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = UnlockImpactRepository(self.db)
        self.calculator = UnlockImpactCalculator()
        # market_data DB 用于读取源数据
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建代币解锁冲击分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_upcoming_unlocks(self) -> list[dict]:
        """从 token_unlocks 加载即将到来的解锁事件。

        Returns
        -------
        list[dict]
            解锁事件列表，每项包含 token, unlock_amount_usd
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT token, unlock_amount_usd, unlock_date
               FROM token_unlocks
               ORDER BY unlock_date ASC LIMIT 20""",
            (),
        )
        if not rows:
            return []
        return [dict(r) for r in rows]

    def _load_token_volume(self, token: str) -> float:
        """加载代币的日均成交量。"""
        market_db = self._get_market_db()
        symbol = f"{token}USDT"
        rows = market_db.fetch_all(
            """SELECT volume FROM klines
               WHERE symbol = ?
               ORDER BY open_time DESC LIMIT 7""",
            (symbol,),
        )
        if not rows:
            return 0.0
        volumes = [float(r["volume"]) for r in rows]
        return sum(volumes) / len(volumes)

    def _load_token_depth(self, token: str) -> float:
        """加载代币的 1% 盘口深度。"""
        market_db = self._get_market_db()
        symbol = f"{token}USDT"
        rows = market_db.fetch_all(
            """SELECT bid_depth_1pct, ask_depth_1pct FROM orderbook_snapshots
               WHERE symbol = ?
               ORDER BY created_at DESC LIMIT 1""",
            (symbol,),
        )
        if not rows:
            return 0.0
        bid = float(rows[0].get("bid_depth_1pct") or 0)
        ask = float(rows[0].get("ask_depth_1pct") or 0)
        return bid + ask

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部代币解锁冲击分析计算并落库。"""
        ts = self._utc_now_iso()

        unlocks = self._load_upcoming_unlocks()
        if not unlocks:
            return {"ts": ts, "top_5_impacts": [], "total_at_risk_usd": 0.0}

        results = []
        for unlock in unlocks:
            token = unlock.get("token", "UNKNOWN")
            amount_usd = float(unlock.get("unlock_amount_usd") or 0)
            daily_volume = self._load_token_volume(token)
            depth_1pct = self._load_token_depth(token)

            sell_pressure = self.calculator.compute_sell_pressure_ratio(
                amount_usd, daily_volume
            )
            historical_reaction = 0.03  # 默认历史反应 3%
            impact_score = self.calculator.compute_impact_score(
                sell_pressure, historical_reaction
            )
            depth_factor = (
                daily_volume / depth_1pct if depth_1pct > 0 else 1.0
            )
            expected_impact = self.calculator.estimate_price_impact(
                sell_pressure, depth_factor
            )
            absorption = self.calculator.compute_liquidity_absorption(
                daily_volume, depth_1pct
            )

            entry = {
                "ts": ts,
                "token": token,
                "unlock_amount_usd": amount_usd,
                "daily_volume": daily_volume,
                "sell_pressure_ratio": sell_pressure,
                "liquidity_absorption": absorption,
                "impact_score": impact_score,
                "expected_price_impact_pct": expected_impact,
            }
            self.repository.save_state(entry)
            results.append(entry)

        # 按 impact_score 降序取 top 5
        results.sort(key=lambda x: x.get("impact_score", 0), reverse=True)
        top_5 = results[:5]
        total_at_risk = sum(r["unlock_amount_usd"] for r in results)

        return {
            "ts": ts,
            "top_5_impacts": top_5,
            "total_at_risk_usd": total_at_risk,
            "count": len(results),
        }

    def load_latest_context_bundle(self) -> dict:
        """加载最新代币解锁冲击分析结果，供 AI 上下文消费。"""
        top_impacts = self.repository.load_top_impacts(5)
        if not top_impacts:
            return {
                "as_of": self._utc_now_iso(),
                "top_5_impacts": [],
                "total_at_risk_usd": 0.0,
                "avg_impact_score": 0.0,
            }
        avg_score = sum(
            r.get("impact_score", 0) for r in top_impacts
        ) / len(top_impacts)
        total_at_risk = sum(
            r.get("unlock_amount_usd", 0) for r in top_impacts
        )
        return {
            "as_of": top_impacts[0].get("ts", self._utc_now_iso()),
            "top_5_impacts": [
                {
                    "token": r.get("token"),
                    "impact_score": r.get("impact_score"),
                    "expected_price_impact_pct": r.get("expected_price_impact_pct"),
                }
                for r in top_impacts
            ],
            "total_at_risk_usd": total_at_risk,
            "avg_impact_score": round(avg_score, 2),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
