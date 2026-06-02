"""流动性状态服务：编排流动性评分、状态分类、利差、脉冲、质押流计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.liquidity_regime.calculator import LiquidityRegimeCalculator
from logic_layer.liquidity_regime.repository import LiquidityRegimeRepository


class LiquidityRegimeService:
    """流动性状态编排服务。

    职责：
    - 从 staking_positions、exchange_reserves 读取市场数据
    - 调用 calculator 计算流动性评分、状态分类、利差、脉冲
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = LiquidityRegimeRepository(self.db)
        self.calculator = LiquidityRegimeCalculator()
        # market_data DB 用于读取源数据
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建流动性状态分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_staking_data(self) -> dict:
        """从 staking_positions 加载质押数据。

        Returns
        -------
        dict
            包含 net_staked, total_supply, tvl_change 的字典
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT amount, asset
               FROM staking_positions
               ORDER BY created_at DESC LIMIT 100""",
            (),
        )
        if not rows:
            return {"net_staked": 0.0, "total_supply": 1.0, "tvl_change": 0.0}

        amounts = [float(r["amount"]) for r in rows]
        total = sum(abs(a) for a in amounts) or 1.0
        net = sum(amounts)
        # TVL 变化估算：最近 10 笔 vs 之前的平均
        recent = amounts[:10]
        older = amounts[10:50] if len(amounts) > 10 else amounts
        avg_recent = sum(recent) / len(recent) if recent else 0.0
        avg_older = sum(older) / len(older) if older else 0.0
        tvl_change = (
            (avg_recent - avg_older) / abs(avg_older)
            if avg_older != 0
            else 0.0
        )
        return {
            "net_staked": net,
            "total_supply": total,
            "tvl_change": tvl_change,
        }

    def _load_reserve_data(self) -> dict:
        """从 exchange_reserves 加载交易所储备数据。

        Returns
        -------
        dict
            包含 reserve_change 的字典
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT reserve_amount
               FROM exchange_reserves
               ORDER BY created_at DESC LIMIT 50""",
            (),
        )
        if not rows:
            return {"reserve_change": 0.0}

        amounts = [float(r["reserve_amount"]) for r in rows]
        recent = amounts[:10]
        older = amounts[10:] if len(amounts) > 10 else amounts
        avg_recent = sum(recent) / len(recent) if recent else 0.0
        avg_older = sum(older) / len(older) if older else 0.0
        reserve_change = (
            (avg_recent - avg_older) / abs(avg_older)
            if avg_older != 0
            else 0.0
        )
        return {"reserve_change": reserve_change}

    def _load_defi_cefi_rates(self) -> dict:
        """加载 DeFi 和 CeFi 借贷利率。

        从 staking_positions 近似 DeFi 利率，
        从 cefi_lending_rate 字段读取 CeFi 利率。

        Returns
        -------
        dict
            包含 defi_rate, cefi_rate 的字典
        """
        market_db = self._get_market_db()
        # DeFi 利率近似：从 staking_positions 的 apy 字段
        defi_rows = market_db.fetch_all(
            """SELECT apy FROM staking_positions
               WHERE apy IS NOT NULL
               ORDER BY created_at DESC LIMIT 10""",
            (),
        )
        defi_rate = 0.0
        if defi_rows:
            rates = [float(r["apy"]) for r in defi_rows]
            defi_rate = sum(rates) / len(rates)

        # CeFi 利率：从 exchange_reserves 的 lending_rate 字段
        cefi_rows = market_db.fetch_all(
            """SELECT lending_rate FROM exchange_reserves
               WHERE lending_rate IS NOT NULL
               ORDER BY created_at DESC LIMIT 10""",
            (),
        )
        cefi_rate = 0.0
        if cefi_rows:
            rates = [float(r["lending_rate"]) for r in cefi_rows]
            cefi_rate = sum(rates) / len(rates)

        return {"defi_rate": defi_rate, "cefi_rate": cefi_rate}

    def _load_stablecoin_supply_changes(self) -> list[float]:
        """加载稳定币供应变化序列。

        Returns
        -------
        list[float]
            供应变化率序列（从旧到新）
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT reserve_amount FROM exchange_reserves
               WHERE asset IN ('USDT', 'USDC', 'DAI', 'BUSD')
               ORDER BY created_at ASC LIMIT 50""",
            (),
        )
        if len(rows) < 2:
            return []

        amounts = [float(r["reserve_amount"]) for r in rows]
        changes = []
        for i in range(1, len(amounts)):
            if amounts[i - 1] > 0:
                change = (amounts[i] - amounts[i - 1]) / amounts[i - 1]
                changes.append(change)
        return changes

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部流动性状态分析计算并落库。"""
        ts = self._utc_now_iso()

        # 加载源数据
        staking_data = self._load_staking_data()
        reserve_data = self._load_reserve_data()
        rate_data = self._load_defi_cefi_rates()
        supply_changes = self._load_stablecoin_supply_changes()

        # 计算各指标
        liquidity_score = self.calculator.compute_liquidity_score(
            staking_tvl_change=staking_data["tvl_change"],
            reserve_change=reserve_data["reserve_change"],
            stablecoin_supply_change=(
                supply_changes[-1] if supply_changes else 0.0
            ),
        )
        regime = self.calculator.classify_regime(liquidity_score)
        defi_cefi_spread = self.calculator.compute_defi_cefi_spread(
            defi_rate=rate_data["defi_rate"],
            cefi_rate=rate_data["cefi_rate"],
        )
        stablecoin_pulse = self.calculator.compute_stablecoin_pulse(
            supply_changes
        )
        staking_flow_impact = self.calculator.compute_staking_flow_impact(
            net_staked=staking_data["net_staked"],
            total_supply=staking_data["total_supply"],
        )

        # 组装结果
        entry = {
            "ts": ts,
            "liquidity_score": liquidity_score,
            "regime": regime,
            "defi_cefi_spread": defi_cefi_spread,
            "stablecoin_pulse": stablecoin_pulse,
            "staking_flow_impact": staking_flow_impact,
        }

        # 落库
        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新流动性状态分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "liquidity_score": 0.0,
                "regime": "neutral",
                "defi_cefi_spread": 0.0,
                "stablecoin_pulse": 0.0,
                "staking_flow_impact": 0.0,
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "liquidity_score": state.get("liquidity_score", 0.0),
            "regime": state.get("regime", "neutral"),
            "defi_cefi_spread": state.get("defi_cefi_spread", 0.0),
            "stablecoin_pulse": state.get("stablecoin_pulse", 0.0),
            "staking_flow_impact": state.get("staking_flow_impact", 0.0),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
