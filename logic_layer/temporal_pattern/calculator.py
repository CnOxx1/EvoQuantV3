"""时间模式计算引擎：季节性、减半周期、资金费率周期。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone


class TemporalPatternCalculator:
    """纯计算逻辑，不依赖数据库。所有方法为静态方法。"""

    @staticmethod
    def _parse_hour(ts) -> int | None:
        if isinstance(ts, str) and len(ts) >= 13:
            return int(ts[11:13])
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(
                ts / 1000 if ts > 1e12 else ts, tz=timezone.utc
            ).hour
        return None

    @staticmethod
    def _parse_weekday(ts) -> int | None:
        if isinstance(ts, str) and len(ts) >= 10:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.weekday()
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(
                ts / 1000 if ts > 1e12 else ts, tz=timezone.utc
            )
            return dt.weekday()
        return None

    @staticmethod
    def _parse_month(ts) -> int | None:
        if isinstance(ts, str) and len(ts) >= 7:
            return int(ts[5:7])
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(
                ts / 1000 if ts > 1e12 else ts, tz=timezone.utc
            )
            return dt.month
        return None

    @staticmethod
    def _aggregate_bucket(data: list[dict]) -> dict:
        """对一组 {return, volume} 计算均值和标准差。"""
        if not data:
            return {
                "avg_return": 0.0, "avg_volume": 0.0,
                "std_return": 0.0, "sample_count": 0,
            }
        returns = [d["return"] for d in data]
        volumes = [d["volume"] for d in data]
        n = len(returns)
        avg_ret = sum(returns) / n
        avg_vol = sum(volumes) / n
        if n > 1:
            var = sum((r - avg_ret) ** 2 for r in returns) / (n - 1)
            std_ret = math.sqrt(var)
        else:
            std_ret = 0.0
        return {
            "avg_return": round(avg_ret, 8),
            "avg_volume": round(avg_vol, 2),
            "std_return": round(std_ret, 8),
            "sample_count": n,
        }

    # ------------------------------------------------------------------
    # 小时季节性
    # ------------------------------------------------------------------

    @staticmethod
    def compute_hourly_seasonality(klines: list[dict]) -> list[dict]:
        """按小时分组，计算平均收益率和成交量。

        Parameters
        ----------
        klines : list[dict]
            K线数据，需包含 open_time, open, close, volume 字段。

        Returns
        -------
        list[dict]
            每小时的季节性统计。
        """
        hourly: dict[int, list[dict]] = defaultdict(list)
        for k in klines:
            try:
                hour = TemporalPatternCalculator._parse_hour(
                    k.get("open_time", "")
                )
                if hour is None:
                    continue
                open_p = float(k.get("open", 0))
                close_p = float(k.get("close", 0))
                volume = float(k.get("volume", 0))
                if open_p > 0:
                    ret = (close_p - open_p) / open_p
                    hourly[hour].append({"return": ret, "volume": volume})
            except (ValueError, TypeError):
                continue

        results = []
        for hour in range(24):
            agg = TemporalPatternCalculator._aggregate_bucket(
                hourly.get(hour, [])
            )
            agg["hour_of_day"] = hour
            results.append(agg)
        return results

    # ------------------------------------------------------------------
    # 星期季节性
    # ------------------------------------------------------------------

    @staticmethod
    def compute_daily_seasonality(klines: list[dict]) -> list[dict]:
        """按星期几分组，计算平均收益率和成交量。

        Parameters
        ----------
        klines : list[dict]
            K线数据，需包含 open_time, open, close, volume 字段。

        Returns
        -------
        list[dict]
            每天的季节性统计。
        """
        daily: dict[int, list[dict]] = defaultdict(list)
        for k in klines:
            try:
                dow = TemporalPatternCalculator._parse_weekday(
                    k.get("open_time", "")
                )
                if dow is None:
                    continue
                open_p = float(k.get("open", 0))
                close_p = float(k.get("close", 0))
                volume = float(k.get("volume", 0))
                if open_p > 0:
                    ret = (close_p - open_p) / open_p
                    daily[dow].append({"return": ret, "volume": volume})
            except (ValueError, TypeError):
                continue

        results = []
        for dow in range(7):
            agg = TemporalPatternCalculator._aggregate_bucket(
                daily.get(dow, [])
            )
            agg["day_of_week"] = dow
            results.append(agg)
        return results

    # ------------------------------------------------------------------
    # 月份效应
    # ------------------------------------------------------------------

    @staticmethod
    def compute_monthly_effect(klines: list[dict]) -> list[dict]:
        """按月份分组，计算平均收益率和成交量。

        Parameters
        ----------
        klines : list[dict]
            K线数据，需包含 open_time, open, close, volume 字段。

        Returns
        -------
        list[dict]
            每月的季节性统计。
        """
        monthly: dict[int, list[dict]] = defaultdict(list)
        for k in klines:
            try:
                month = TemporalPatternCalculator._parse_month(
                    k.get("open_time", "")
                )
                if month is None:
                    continue
                open_p = float(k.get("open", 0))
                close_p = float(k.get("close", 0))
                volume = float(k.get("volume", 0))
                if open_p > 0:
                    ret = (close_p - open_p) / open_p
                    monthly[month].append({"return": ret, "volume": volume})
            except (ValueError, TypeError):
                continue

        results = []
        for month in range(1, 13):
            agg = TemporalPatternCalculator._aggregate_bucket(
                monthly.get(month, [])
            )
            agg["month"] = month
            results.append(agg)
        return results

    # ------------------------------------------------------------------
    # 减半周期
    # ------------------------------------------------------------------

    @staticmethod
    def compute_halving_cycle_phase() -> dict:
        """计算当前距下一次 BTC 减半的天数及历史周期阶段。

        下一次减半预计约为 2028 年 4 月（区块高度 1,050,000）。

        Returns
        -------
        dict
            {days_to_next_halving, cycle_progress_pct, phase}
        """
        # 上一次减半: 2024-04-20 (区块 840,000)
        last_halving = datetime(2024, 4, 20, tzinfo=timezone.utc)
        # 预计下一次减半: 约 2028-04-17
        next_halving = datetime(2028, 4, 17, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        cycle_duration = (next_halving - last_halving).days
        days_since = (now - last_halving).days
        days_to_next = (next_halving - now).days

        progress = days_since / cycle_duration if cycle_duration > 0 else 0.0
        progress = max(0.0, min(1.0, progress))

        # 历史阶段划分
        if progress < 0.25:
            phase = "post_halving_bull"
        elif progress < 0.50:
            phase = "mid_cycle_correction"
        elif progress < 0.75:
            phase = "accumulation"
        else:
            phase = "pre_halving_anticipation"

        return {
            "days_to_next_halving": max(0, days_to_next),
            "days_since_last_halving": max(0, days_since),
            "cycle_progress_pct": round(progress * 100, 2),
            "phase": phase,
            "next_halving_est": next_halving.strftime("%Y-%m-%d"),
        }

    # ------------------------------------------------------------------
    # 资金费率周期
    # ------------------------------------------------------------------

    @staticmethod
    def compute_funding_cycle_pattern(funding_rates: list[dict]) -> list[dict]:
        """分析 8h 结算周期的资金费率模式。

        Parameters
        ----------
        funding_rates : list[dict]
            资金费率数据，需包含 funding_time/timestamp, funding_rate 字段。

        Returns
        -------
        list[dict]
            每个 8h 结算时段的统计 [{settlement_hour, avg_rate, std_rate,
            positive_pct, sample_count}, ...]
        """
        # 标准结算时间: 00:00, 08:00, 16:00 UTC
        settlement_hours = [0, 8, 16]
        buckets: dict[int, list[float]] = {h: [] for h in settlement_hours}

        for fr in funding_rates:
            try:
                ts = fr.get("funding_time") or fr.get("timestamp", "")
                rate = float(fr.get("funding_rate", 0))
                if isinstance(ts, str) and len(ts) >= 13:
                    hour = int(ts[11:13])
                elif isinstance(ts, (int, float)):
                    hour = datetime.fromtimestamp(
                        ts / 1000 if ts > 1e12 else ts, tz=timezone.utc
                    ).hour
                else:
                    continue
                # 归入最近的结算时段
                nearest = min(settlement_hours, key=lambda h: abs(h - hour))
                buckets[nearest].append(rate)
            except (ValueError, TypeError):
                continue

        results = []
        for sh in settlement_hours:
            rates = buckets[sh]
            n = len(rates)
            if n == 0:
                results.append({
                    "settlement_hour": sh,
                    "avg_rate": 0.0,
                    "std_rate": 0.0,
                    "positive_pct": 0.0,
                    "sample_count": 0,
                })
                continue
            avg_rate = sum(rates) / n
            if n > 1:
                var = sum((r - avg_rate) ** 2 for r in rates) / (n - 1)
                std_rate = math.sqrt(var)
            else:
                std_rate = 0.0
            positive_pct = sum(1 for r in rates if r > 0) / n
            results.append({
                "settlement_hour": sh,
                "avg_rate": round(avg_rate, 8),
                "std_rate": round(std_rate, 8),
                "positive_pct": round(positive_pct, 4),
                "sample_count": n,
            })
        return results
