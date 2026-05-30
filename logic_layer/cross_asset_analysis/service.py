"""跨资产分析服务：编排相关性、相对强弱、板块轮动、资金流向计算。"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from config.symbols import (
    SECTOR_DEFINITIONS,
    SYMBOL_UNIVERSE,
    TARGET_SYMBOLS,
    get_symbol_sector,
    get_symbol_tier,
)
from database.db_manager import DBManager
from logic_layer.cross_asset_analysis.calculator import CrossAssetCalculator
from logic_layer.cross_asset_analysis.repository import CrossAssetRepository


class CrossAssetAnalysisService:
    """跨资产分析编排服务。

    职责：
    - 从 merged_klines / trade_flow_bars / open_interest_snapshots 读取原始数据
    - 调用 calculator 计算相关性矩阵、相对强弱、板块轮动、资金流向
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = CrossAssetRepository(self.db)
        self.calculator = CrossAssetCalculator()

    def init_storage(self):
        """创建跨资产分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_close_series(
        self, timeframe: str = "1h", window_hours: int = 168
    ) -> dict[str, list[float]]:
        """从 merged_klines 加载收盘价序列（默认 7 天 1h = 168 根）。"""
        rows = self.db.fetch_all(
            """SELECT symbol, close, open_time
               FROM merged_klines
               WHERE timeframe = ?
               ORDER BY symbol, open_time DESC""",
            (timeframe,),
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
        return series

    def _load_returns(self) -> dict[str, dict[str, float | None]]:
        """从 merged_klines 1h 计算 1d/3d/7d 收益率。"""
        series = self._load_close_series(timeframe="1h", window_hours=168)
        returns: dict[str, dict[str, float | None]] = {}
        for sym, prices in series.items():
            n = len(prices)
            r1d = ((prices[-1] / prices[-24]) - 1) if n >= 24 else None
            r3d = ((prices[-1] / prices[-72]) - 1) if n >= 72 else None
            r7d = ((prices[-1] / prices[0]) - 1) if n >= 2 else None
            returns[sym] = {"1d": r1d, "3d": r3d, "7d": r7d}
        return returns

    def _load_fund_flow_data(self) -> dict[str, dict]:
        """从 latest_trade_flow_bars + latest_open_interest_snapshots 聚合资金流向。"""
        # 最近 1h 和 24h 的 net_taker_notional 聚合
        flow_rows = self.db.fetch_all(
            """SELECT symbol, interval, net_taker_notional,
                      aggressive_buy_notional, aggressive_sell_notional
               FROM latest_trade_flow_bars
               WHERE market_type IN ('swap', 'linear_swap')
               ORDER BY symbol""",
            (),
        )
        oi_rows = self.db.fetch_all(
            """SELECT symbol, interval, timestamp,
                      open_interest_usd
               FROM latest_open_interest_snapshots
               WHERE market_type IN ('swap', 'linear_swap')
               ORDER BY symbol""",
            (),
        )
        # 按 symbol 聚合
        flow_by_sym: dict[str, dict] = {}
        for row in flow_rows:
            sym = row["symbol"]
            entry = flow_by_sym.setdefault(sym, {})
            interval = row["interval"]
            net = float(row["net_taker_notional"] or 0)
            buy = float(row["aggressive_buy_notional"] or 0)
            sell = float(row["aggressive_sell_notional"] or 0)
            if interval == "1h":
                entry["net_taker_1h"] = net
                entry["buy_1h"] = buy
                entry["sell_1h"] = sell
            elif interval == "1d":
                entry["net_taker_24h"] = net
                entry["buy_24h"] = buy
                entry["sell_24h"] = sell

        oi_by_sym: dict[str, dict] = {}
        for row in oi_rows:
            sym = row["symbol"]
            oi_by_sym.setdefault(sym, {})[row["interval"]] = float(
                row["open_interest_usd"] or 0
            )

        return {"flow": flow_by_sym, "oi": oi_by_sym}

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_correlation(self, window_hours: int = 168) -> dict | None:
        """计算并保存相关性矩阵快照。"""
        series = self._load_close_series(timeframe="1h", window_hours=window_hours)
        # 至少需要 2 个有足够数据的 symbol
        valid = {s: p for s, p in series.items() if len(p) >= 24}
        if len(valid) < 2:
            return None

        # 对齐长度
        min_len = min(len(p) for p in valid.values())
        aligned = {s: p[-min_len:] for s, p in valid.items()}

        matrix = self.calculator.compute_correlation_matrix(aligned)
        symbols = sorted(aligned.keys())

        # 统计
        corr_values = []
        for i, sa in enumerate(symbols):
            for j, sb in enumerate(symbols):
                if j > i:
                    corr_values.append(matrix[sa][sb])

        avg_corr = sum(corr_values) / len(corr_values) if corr_values else 0.0
        max_corr = max(corr_values) if corr_values else 0.0
        min_corr = min(corr_values) if corr_values else 0.0

        snapshot_time = self._utc_now_iso()
        self.repository.save_correlation_snapshot(
            snapshot_time=snapshot_time,
            window_hours=window_hours,
            matrix=matrix,
            symbols=symbols,
            avg_correlation=round(avg_corr, 4),
            max_correlation=round(max_corr, 4),
            min_correlation=round(min_corr, 4),
        )
        return {
            "snapshot_time": snapshot_time,
            "window_hours": window_hours,
            "symbol_count": len(symbols),
            "avg_correlation": round(avg_corr, 4),
            "max_correlation": round(max_corr, 4),
            "min_correlation": round(min_corr, 4),
        }

    def compute_relative_strength(self) -> list[dict] | None:
        """计算并保存相对强弱排名。"""
        returns = self._load_returns()
        if not returns:
            return None
        entries = self.calculator.compute_relative_strength(returns)
        snapshot_time = self._utc_now_iso()
        # 补充 sector/tier/asset 信息
        for entry in entries:
            sym = entry["symbol"]
            entry["snapshot_time"] = snapshot_time
            entry["asset"] = sym.replace("/USDT", "")
            entry["sector"] = get_symbol_sector(sym)
            tier = get_symbol_tier(sym)
            entry["tier"] = tier.value if tier else None
            entry["volume_change_7d_pct"] = None  # 暂无成交量变化
        self.repository.save_relative_strength(entries)
        return entries

    def compute_sector_rotation(self) -> list[dict] | None:
        """计算并保存板块轮动。"""
        returns = self._load_returns()
        series = self._load_close_series(timeframe="1h", window_hours=168)
        fund_data = self._load_fund_flow_data()
        if not returns:
            return None

        sector_data: dict[str, dict] = {}
        for sector, symbols in SECTOR_DEFINITIONS.items():
            sector_returns = []
            sector_vols = []
            sector_flow = 0.0
            sector_oi = 0.0
            for sym in symbols:
                r7d = (returns.get(sym) or {}).get("7d")
                if r7d is not None:
                    sector_returns.append(r7d)
                # 波动率从价格序列
                prices = series.get(sym, [])
                if len(prices) >= 2:
                    log_rets = [
                        math.log(prices[i] / prices[i - 1])
                        for i in range(1, len(prices))
                        if prices[i - 1] > 0
                    ]
                    if log_rets:
                        mean_r = sum(log_rets) / len(log_rets)
                        var = sum((r - mean_r) ** 2 for r in log_rets) / len(log_rets)
                        sector_vols.append(math.sqrt(var))
                # 资金流
                flow_entry = fund_data["flow"].get(sym, {})
                sector_flow += flow_entry.get("net_taker_24h", 0)

            avg_ret = sum(sector_returns) / len(sector_returns) if sector_returns else 0
            avg_vol = sum(sector_vols) / len(sector_vols) if sector_vols else 0

            sector_data[sector] = {
                "return_7d": avg_ret,
                "volatility_7d": avg_vol,
                "net_flow_24h": sector_flow,
                "oi_change_24h": None,
                "constituent_count": len(symbols),
            }

        entries = self.calculator.compute_sector_rotation(sector_data)
        snapshot_time = self._utc_now_iso()
        for entry in entries:
            entry["snapshot_time"] = snapshot_time
        self.repository.save_sector_rotation(entries)
        return entries

    def compute_fund_flow(self) -> list[dict] | None:
        """计算并保存聚合资金流向（按 total / tier / sector 维度）。"""
        fund_data = self._load_fund_flow_data()
        flow_map = fund_data["flow"]
        if not flow_map:
            return None

        snapshot_time = self._utc_now_iso()
        entries: list[dict] = []

        # 全市场汇总
        total_net_1h = sum(e.get("net_taker_1h", 0) for e in flow_map.values())
        total_net_24h = sum(e.get("net_taker_24h", 0) for e in flow_map.values())
        total_buy_24h = sum(e.get("buy_24h", 0) for e in flow_map.values())
        total_sell_24h = sum(e.get("sell_24h", 0) for e in flow_map.values())
        total_volume = total_buy_24h + total_sell_24h
        entries.append({
            "snapshot_time": snapshot_time,
            "scope": "total",
            "net_taker_flow_1h": round(total_net_1h, 2),
            "net_taker_flow_24h": round(total_net_24h, 2),
            "oi_change_1h": None,
            "oi_change_24h": None,
            "aggressive_buy_share": (
                round(total_buy_24h / total_volume, 4) if total_volume > 0 else None
            ),
        })

        # 按 tier 聚合
        from config.symbols import SymbolTier, symbols_by_tier
        for tier in SymbolTier:
            tier_syms = symbols_by_tier(tier)
            net_1h = sum(flow_map.get(s, {}).get("net_taker_1h", 0) for s in tier_syms)
            net_24h = sum(flow_map.get(s, {}).get("net_taker_24h", 0) for s in tier_syms)
            buy_24h = sum(flow_map.get(s, {}).get("buy_24h", 0) for s in tier_syms)
            sell_24h = sum(flow_map.get(s, {}).get("sell_24h", 0) for s in tier_syms)
            vol = buy_24h + sell_24h
            entries.append({
                "snapshot_time": snapshot_time,
                "scope": f"tier:{tier.value}",
                "net_taker_flow_1h": round(net_1h, 2),
                "net_taker_flow_24h": round(net_24h, 2),
                "oi_change_1h": None,
                "oi_change_24h": None,
                "aggressive_buy_share": (
                    round(buy_24h / vol, 4) if vol > 0 else None
                ),
            })

        # 按 sector 聚合
        for sector, syms in SECTOR_DEFINITIONS.items():
            net_1h = sum(flow_map.get(s, {}).get("net_taker_1h", 0) for s in syms)
            net_24h = sum(flow_map.get(s, {}).get("net_taker_24h", 0) for s in syms)
            buy_24h = sum(flow_map.get(s, {}).get("buy_24h", 0) for s in syms)
            sell_24h = sum(flow_map.get(s, {}).get("sell_24h", 0) for s in syms)
            vol = buy_24h + sell_24h
            entries.append({
                "snapshot_time": snapshot_time,
                "scope": f"sector:{sector}",
                "net_taker_flow_1h": round(net_1h, 2),
                "net_taker_flow_24h": round(net_24h, 2),
                "oi_change_1h": None,
                "oi_change_24h": None,
                "aggressive_buy_share": (
                    round(buy_24h / vol, 4) if vol > 0 else None
                ),
            })

        self.repository.save_fund_flow(entries)
        return entries

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """执行全部跨资产分析计算并落库。"""
        results: dict = {}
        results["correlation"] = self.compute_correlation(window_hours=168)
        results["relative_strength"] = self.compute_relative_strength()
        results["sector_rotation"] = self.compute_sector_rotation()
        results["fund_flow"] = self.compute_fund_flow()
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新跨资产分析结果，供 AI 上下文消费。"""
        correlation = self.repository.load_latest_correlation(window_hours=168)
        return {
            "as_of": self._utc_now_iso(),
            "correlation": correlation,
            "correlation_regime": self._classify_correlation_regime(correlation),
        }

    @staticmethod
    def _classify_correlation_regime(correlation: dict | None) -> str:
        """根据平均相关性判定市场相关性 regime。"""
        if not correlation:
            return "unknown"
        avg = correlation.get("avg_correlation", 0)
        if avg > 0.7:
            return "high_correlation"
        elif avg > 0.4:
            return "moderate_correlation"
        elif avg > 0.1:
            return "low_correlation"
        else:
            return "decorrelated"

    def close(self):
        self.db.close()
