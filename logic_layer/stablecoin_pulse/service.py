"""稳定币脉冲服务：编排净铸造脉冲、链迁移方向、扩张信号、BTC 相关性计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.stablecoin_pulse.calculator import StablecoinPulseCalculator
from logic_layer.stablecoin_pulse.repository import StablecoinPulseRepository


class StablecoinPulseService:
    """稳定币脉冲编排服务。

    职责：
    - 从 stablecoin_supply、chain_flows 读取市场数据
    - 调用 calculator 计算净铸造脉冲、链迁移、扩张信号
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = StablecoinPulseRepository(self.db)
        self.calculator = StablecoinPulseCalculator()
        # market_data DB 用于读取源数据
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建稳定币脉冲分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_mint_burn_volumes(self) -> tuple[list[float], list[float]]:
        """从 stablecoin_supply 加载铸造和销毁量。

        Returns
        -------
        tuple[list[float], list[float]]
            (mint_volumes, burn_volumes)
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT mint_amount, burn_amount
               FROM stablecoin_supply
               ORDER BY created_at DESC LIMIT 24""",
            (),
        )
        if not rows:
            return [], []

        mints = [float(r["mint_amount"]) for r in rows if r["mint_amount"]]
        burns = [float(r["burn_amount"]) for r in rows if r["burn_amount"]]
        return mints, burns

    def _load_chain_flows(self) -> dict[str, float]:
        """从 chain_flows 加载各链净流入。

        Returns
        -------
        dict[str, float]
            各链名称 -> 净流入量
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT chain, net_flow
               FROM chain_flows
               ORDER BY created_at DESC LIMIT 50""",
            (),
        )
        if not rows:
            return {}

        flows: dict[str, float] = {}
        for r in rows:
            chain = r["chain"]
            flows[chain] = flows.get(chain, 0.0) + float(r["net_flow"])
        return flows

    def _load_pulse_series(self) -> list[float]:
        """加载历史脉冲序列用于相关性计算。"""
        rows = self.db.fetch_all(
            """SELECT net_mint_pulse FROM stablecoin_pulse_states
               ORDER BY ts ASC LIMIT 30""",
            (),
        )
        return [float(r["net_mint_pulse"]) for r in rows if r["net_mint_pulse"]]

    def _load_btc_returns(self) -> list[float]:
        """加载 BTC 收益率序列。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT close_price FROM klines
               WHERE symbol = 'BTCUSDT'
               ORDER BY open_time ASC LIMIT 31""",
            (),
        )
        if len(rows) < 2:
            return []

        prices = [float(r["close_price"]) for r in rows]
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
        return returns

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部稳定币脉冲分析计算并落库。"""
        ts = self._utc_now_iso()

        # 加载源数据
        mint_volumes, burn_volumes = self._load_mint_burn_volumes()
        chain_flows = self._load_chain_flows()
        pulse_series = self._load_pulse_series()
        btc_returns = self._load_btc_returns()

        # 计算各指标
        net_mint_pulse = self.calculator.compute_net_mint_pulse(
            mint_volumes, burn_volumes
        )
        expansion_signal = self.calculator.classify_expansion_signal(net_mint_pulse)
        chain_migration_direction = self.calculator.compute_chain_migration(chain_flows)
        pulse_amplitude = abs(net_mint_pulse)
        btc_correlation = self.calculator.compute_btc_correlation(
            pulse_series, btc_returns
        )

        # 组装结果
        entry = {
            "ts": ts,
            "net_mint_pulse": net_mint_pulse,
            "chain_migration_direction": chain_migration_direction,
            "expansion_signal": expansion_signal,
            "pulse_amplitude": pulse_amplitude,
            "btc_correlation": btc_correlation,
        }

        # 落库
        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新稳定币脉冲分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "net_mint_pulse": 0.0,
                "expansion_signal": "neutral",
                "pulse_amplitude": 0.0,
                "chain_migration_direction": "unknown",
                "btc_correlation": 0.0,
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "net_mint_pulse": state.get("net_mint_pulse", 0.0),
            "expansion_signal": state.get("expansion_signal", "neutral"),
            "pulse_amplitude": state.get("pulse_amplitude", 0.0),
            "chain_migration_direction": state.get("chain_migration_direction", "unknown"),
            "btc_correlation": state.get("btc_correlation", 0.0),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
