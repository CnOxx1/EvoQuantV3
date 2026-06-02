"""深度 regime 服务：编排盘口深度结构分类、墙位强度、滑点预估、背离计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from database.db_manager import DBManager
from logic_layer.depth_regime.calculator import DepthRegimeCalculator
from logic_layer.depth_regime.repository import DepthRegimeRepository


class DepthRegimeService:
    """深度 regime 编排服务。

    职责：
    - 从 orderbook_snapshots、klines 读取市场数据
    - 调用 calculator 计算 regime 分类、墙强度、滑点
    - 通过 repository 落库到 analytics DB
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = DepthRegimeRepository(self.db)
        self.calculator = DepthRegimeCalculator()
        self._market_db: DBManager | None = None

    def _get_market_db(self) -> DBManager:
        """懒加载 market_data 数据库连接。"""
        if self._market_db is None:
            from database.router import DatabaseRouter
            self._market_db = DatabaseRouter().get_market_data_db()
        return self._market_db

    def init_storage(self):
        """创建深度 regime 分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_orderbook_data(self, symbol: str = "BTCUSDT") -> dict:
        """从 orderbook_snapshots 加载盘口数据。

        Returns
        -------
        dict
            包含 bid_depth, ask_depth, imbalance, bid_levels, ask_levels
        """
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT bid_depth_total, ask_depth_total, bid_levels, ask_levels
               FROM orderbook_snapshots
               WHERE symbol = ?
               ORDER BY created_at DESC LIMIT 1""",
            (symbol,),
        )
        if not rows:
            return {
                "bid_depth": 0.0, "ask_depth": 0.0,
                "imbalance": 0.0, "bid_levels": [], "ask_levels": [],
            }

        r = rows[0]
        bid_depth = float(r.get("bid_depth_total") or 0)
        ask_depth = float(r.get("ask_depth_total") or 0)
        total = bid_depth + ask_depth
        imbalance = (
            (bid_depth - ask_depth) / total if total > 0 else 0.0
        )
        return {
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "imbalance": imbalance,
            "bid_levels": [],
            "ask_levels": [],
        }

    def _load_wall_data(self, symbol: str = "BTCUSDT") -> dict:
        """加载挂单墙数据。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT side, wall_size, avg_level_size, persistence_count
               FROM orderbook_walls
               WHERE symbol = ?
               ORDER BY created_at DESC LIMIT 2""",
            (symbol,),
        )
        result = {
            "bid_wall_size": 0.0, "ask_wall_size": 0.0,
            "avg_level_size": 1.0,
            "bid_persistence": 0, "ask_persistence": 0,
        }
        for r in rows:
            side = r.get("side", "")
            if side == "bid":
                result["bid_wall_size"] = float(r.get("wall_size") or 0)
                result["bid_persistence"] = int(r.get("persistence_count") or 0)
            elif side == "ask":
                result["ask_wall_size"] = float(r.get("wall_size") or 0)
                result["ask_persistence"] = int(r.get("persistence_count") or 0)
            result["avg_level_size"] = float(r.get("avg_level_size") or 1)
        return result

    def _load_price_change(self, symbol: str = "BTCUSDT") -> float:
        """加载最近价格变化率。"""
        market_db = self._get_market_db()
        rows = market_db.fetch_all(
            """SELECT close_price FROM klines
               WHERE symbol = ?
               ORDER BY open_time DESC LIMIT 2""",
            (symbol,),
        )
        if len(rows) < 2:
            return 0.0
        curr = float(rows[0]["close_price"])
        prev = float(rows[1]["close_price"])
        if prev <= 0:
            return 0.0
        return (curr - prev) / prev

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def run_all(self, symbol: str = "BTCUSDT") -> dict:
        """执行全部深度 regime 分析计算并落库。"""
        ts = self._utc_now_iso()

        ob_data = self._load_orderbook_data(symbol)
        wall_data = self._load_wall_data(symbol)
        price_change = self._load_price_change(symbol)

        regime = self.calculator.classify_regime(
            ob_data["bid_depth"], ob_data["ask_depth"], ob_data["imbalance"]
        )
        bid_wall_strength = self.calculator.compute_wall_strength(
            wall_data["bid_wall_size"],
            wall_data["avg_level_size"],
            wall_data["bid_persistence"],
        )
        ask_wall_strength = self.calculator.compute_wall_strength(
            wall_data["ask_wall_size"],
            wall_data["avg_level_size"],
            wall_data["ask_persistence"],
        )

        # 滑点估算（简化：基于总深度线性分配）
        total_depth = ob_data["ask_depth"]
        slippage_10k = self.calculator.estimate_slippage(
            10_000, [(1.0, total_depth)] if total_depth > 0 else []
        )
        slippage_100k = self.calculator.estimate_slippage(
            100_000, [(1.0, total_depth)] if total_depth > 0 else []
        )
        slippage_1m = self.calculator.estimate_slippage(
            1_000_000, [(1.0, total_depth)] if total_depth > 0 else []
        )

        # 深度变化近似为失衡度变化
        depth_change = -ob_data["imbalance"]
        divergence = self.calculator.compute_depth_price_divergence(
            depth_change, price_change
        )

        entry = {
            "ts": ts,
            "symbol": symbol,
            "regime": regime,
            "bid_wall_strength": bid_wall_strength,
            "ask_wall_strength": ask_wall_strength,
            "slippage_10k": slippage_10k,
            "slippage_100k": slippage_100k,
            "slippage_1m": slippage_1m,
            "depth_price_divergence": divergence,
        }

        self.repository.save_state(entry)
        return entry

    def load_latest_context_bundle(self) -> dict:
        """加载最新深度 regime 分析结果，供 AI 上下文消费。"""
        state = self.repository.load_latest_state()
        if not state:
            return {
                "as_of": self._utc_now_iso(),
                "regime": "unknown",
                "bid_wall_strength": 0.0,
                "ask_wall_strength": 0.0,
                "slippage_10k": 0.0,
                "slippage_100k": 0.0,
                "slippage_1m": 0.0,
                "depth_price_divergence": 0.0,
            }
        return {
            "as_of": state.get("ts", self._utc_now_iso()),
            "regime": state.get("regime", "unknown"),
            "bid_wall_strength": state.get("bid_wall_strength", 0.0),
            "ask_wall_strength": state.get("ask_wall_strength", 0.0),
            "slippage_10k": state.get("slippage_10k", 0.0),
            "slippage_100k": state.get("slippage_100k", 0.0),
            "slippage_1m": state.get("slippage_1m", 0.0),
            "depth_price_divergence": state.get("depth_price_divergence", 0.0),
        }

    def close(self):
        """关闭数据库连接。"""
        self.db.close()
        if self._market_db is not None:
            self._market_db.close()
