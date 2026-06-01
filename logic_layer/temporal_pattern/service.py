"""时间模式分析服务：编排季节性、减半周期、资金费率周期计算。"""

from __future__ import annotations

from datetime import datetime, timezone

from config.symbols import TARGET_SYMBOLS
from database.db_manager import DBManager
from logic_layer.temporal_pattern.calculator import TemporalPatternCalculator
from logic_layer.temporal_pattern.repository import TemporalPatternRepository


class TemporalPatternService:
    """时间模式分析编排服务。

    职责：
    - 从 merged_klines / funding_rate_snapshots 读取原始数据
    - 调用 calculator 计算季节性、减半周期、资金费率周期
    - 通过 repository 落库
    """

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = TemporalPatternRepository(self.db)
        self.calculator = TemporalPatternCalculator()

    def init_storage(self):
        """创建时间模式分析所需的数据库表。"""
        self.repository.ensure_tables()

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def _load_klines(
        self, symbol: str, timeframe: str = "1h", limit: int = 720
    ) -> list[dict]:
        """从 merged_klines 加载 K 线数据。"""
        rows = self.db.fetch_all(
            """SELECT symbol, open_time, open, close, volume
               FROM merged_klines
               WHERE symbol = ? AND timeframe = ?
               ORDER BY open_time DESC LIMIT ?""",
            (symbol, timeframe, limit),
        )
        if not rows:
            return []
        result = [dict(r) for r in rows]
        result.reverse()
        return result

    def _load_funding_rates(
        self, symbol: str, limit: int = 200
    ) -> list[dict]:
        """从 funding_rate_snapshots 加载资金费率数据。"""
        rows = self.db.fetch_all(
            """SELECT symbol, funding_time, funding_rate
               FROM funding_rate_snapshots
               WHERE symbol = ?
               ORDER BY funding_time DESC LIMIT ?""",
            (symbol, limit),
        )
        if not rows:
            return []
        result = [dict(r) for r in rows]
        result.reverse()
        return result

    # ------------------------------------------------------------------
    # 计算编排
    # ------------------------------------------------------------------

    def compute_patterns(self, symbol: str) -> dict:
        """对单个 symbol 执行全部时间模式计算。"""
        ts = self._utc_now_iso()
        klines = self._load_klines(symbol)
        funding_rates = self._load_funding_rates(symbol)

        # 季节性计算
        hourly = self.calculator.compute_hourly_seasonality(klines)
        daily = self.calculator.compute_daily_seasonality(klines)
        monthly = self.calculator.compute_monthly_effect(klines)
        halving = self.calculator.compute_halving_cycle_phase()
        funding_cycle = self.calculator.compute_funding_cycle_pattern(
            funding_rates
        )

        # 构建 temporal_patterns 条目
        patterns: list[dict] = []

        # 小时季节性中偏离最大的
        if hourly:
            best_hour = max(hourly, key=lambda x: abs(x["avg_return"]))
            if best_hour["sample_count"] > 0:
                patterns.append({
                    "ts": ts, "symbol": symbol,
                    "pattern_type": "hourly_seasonality",
                    "pattern_value": best_hour["avg_return"],
                    "confidence": min(best_hour["sample_count"] / 30, 1.0),
                    "historical_avg": best_hour["avg_return"],
                    "current_deviation": 0.0,
                })

        # 星期效应中偏离最大的
        if daily:
            best_day = max(daily, key=lambda x: abs(x["avg_return"]))
            if best_day["sample_count"] > 0:
                patterns.append({
                    "ts": ts, "symbol": symbol,
                    "pattern_type": "daily_seasonality",
                    "pattern_value": best_day["avg_return"],
                    "confidence": min(best_day["sample_count"] / 4, 1.0),
                    "historical_avg": best_day["avg_return"],
                    "current_deviation": 0.0,
                })

        # 减半周期
        patterns.append({
            "ts": ts, "symbol": symbol,
            "pattern_type": "halving_cycle",
            "pattern_value": halving["cycle_progress_pct"],
            "confidence": 0.8,
            "historical_avg": 50.0,
            "current_deviation": halving["cycle_progress_pct"] - 50.0,
        })

        # 资金费率周期
        if funding_cycle:
            avg_rates = [fc["avg_rate"] for fc in funding_cycle if fc["sample_count"] > 0]
            if avg_rates:
                overall_avg = sum(avg_rates) / len(avg_rates)
                patterns.append({
                    "ts": ts, "symbol": symbol,
                    "pattern_type": "funding_cycle",
                    "pattern_value": overall_avg,
                    "confidence": min(
                        sum(fc["sample_count"] for fc in funding_cycle) / 60, 1.0
                    ),
                    "historical_avg": overall_avg,
                    "current_deviation": 0.0,
                })

        # 保存
        self.repository.save_patterns(patterns)

        # 构建 seasonal_profiles
        profiles: list[dict] = []
        for h in hourly:
            profiles.append({
                "symbol": symbol, "dimension": "return",
                "hour_of_day": h["hour_of_day"], "day_of_week": -1, "month": -1,
                "avg_value": h["avg_return"], "std_value": h["std_return"],
                "sample_count": h["sample_count"],
            })
        for d in daily:
            profiles.append({
                "symbol": symbol, "dimension": "return",
                "hour_of_day": -1, "day_of_week": d["day_of_week"], "month": -1,
                "avg_value": d["avg_return"], "std_value": d["std_return"],
                "sample_count": d["sample_count"],
            })
        for m in monthly:
            profiles.append({
                "symbol": symbol, "dimension": "return",
                "hour_of_day": -1, "day_of_week": -1, "month": m["month"],
                "avg_value": m["avg_return"], "std_value": m["std_return"],
                "sample_count": m["sample_count"],
            })
        self.repository.save_seasonal_profiles(profiles)

        return {
            "symbol": symbol,
            "patterns_count": len(patterns),
            "profiles_count": len(profiles),
            "halving": halving,
            "funding_cycle": funding_cycle,
        }

    # ------------------------------------------------------------------
    # 主编排
    # ------------------------------------------------------------------

    def run_all(self, symbols: list[str] | None = None) -> dict:
        """对所有目标 symbol 执行时间模式分析。"""
        if symbols is None:
            symbols = list(TARGET_SYMBOLS)
        results: dict = {}
        for symbol in symbols:
            results[symbol] = self.compute_patterns(symbol)
        return results

    def load_latest_context_bundle(self) -> dict:
        """加载最新时间模式分析结果，供 AI 上下文消费。"""
        halving = self.calculator.compute_halving_cycle_phase()
        context: dict = {
            "as_of": self._utc_now_iso(),
            "halving_cycle": halving,
            "patterns_by_symbol": {},
        }
        for symbol in TARGET_SYMBOLS:
            patterns = self.repository.load_latest_patterns(symbol)
            profiles = self.repository.load_seasonal_profile(symbol)
            if patterns or profiles:
                context["patterns_by_symbol"][symbol] = {
                    "patterns": patterns,
                    "seasonal_profiles": profiles,
                }
        return context

    def close(self):
        self.db.close()
