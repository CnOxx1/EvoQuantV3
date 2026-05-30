"""时间切片查询编排服务。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from database.db_manager import DBManager
from logic_layer.time_slice.models import DomainSlice, FeatureHistory, TimeSlice, TimeSliceRange
from logic_layer.time_slice.repository import TimeSliceRepository

logger = logging.getLogger(__name__)


class TimeSliceService:
    """时间切片查询入口 — 查看任意历史时刻的全市场特征快照。"""

    DOMAINS = (
        "klines",
        "technical_indicators",
        "feature_standardization",
        "cross_asset",
        "portfolio_risk",
        "macro_context",
        "market_breadth",
        "asset_readiness",
        "ai_market_context",
        "exchange_comparison",
    )

    # 各域数据的正常更新间隔（秒），超过则标记为 stale
    STALENESS_THRESHOLDS: dict[str, int] = {
        "klines": 3600,
        "technical_indicators": 3600,
        "feature_standardization": 7200,
        "cross_asset": 7200,
        "portfolio_risk": 7200,
        "macro_context": 86400,
        "market_breadth": 7200,
        "asset_readiness": 7200,
        "ai_market_context": 7200,
        "exchange_comparison": 3600,
    }

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter
            self.db = DatabaseRouter().get_analytics_db()
        self.repository = TimeSliceRepository(self.db)

    def init_storage(self):
        """无需建表 — 纯只读模块。"""

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def _normalize_timestamp(ts: str | datetime) -> str:
        if isinstance(ts, datetime):
            return ts.strftime("%Y-%m-%dT%H:%M:%S")
        return ts

    @staticmethod
    def _parse_iso(ts: str) -> datetime:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"无法解析时间戳: {ts}")

    # ------------------------------------------------------------------
    # 核心入口
    # ------------------------------------------------------------------

    def get_slice_at(
        self,
        timestamp: str | datetime,
        symbols: list[str] | None = None,
        domains: list[str] | None = None,
        timeframe: str = "1h",
    ) -> TimeSlice:
        """获取指定时刻的完整市场快照。"""
        ts_str = self._normalize_timestamp(timestamp)
        requested_dt = self._parse_iso(ts_str)
        target_domains = domains or list(self.DOMAINS)

        domain_slices: dict[str, DomainSlice] = {}
        for domain in target_domains:
            if domain not in self.DOMAINS:
                continue
            domain_slices[domain] = self._build_domain_slice(
                domain, ts_str, symbols, timeframe, requested_dt
            )

        # 覆盖摘要
        ready_count = sum(1 for d in domain_slices.values() if d.status == "ready")
        stale_count = sum(1 for d in domain_slices.values() if d.status == "stale")
        missing_count = sum(1 for d in domain_slices.values() if d.status == "missing")

        overall = "ready" if missing_count == 0 and stale_count == 0 else (
            "partial" if ready_count > 0 else "unavailable"
        )

        return TimeSlice(
            requested_at=ts_str,
            generated_at=self._utc_now_iso(),
            symbols=symbols or [],
            domains=domain_slices,
            coverage_summary={
                "domains_requested": len(target_domains),
                "domains_ready": ready_count,
                "domains_stale": stale_count,
                "domains_missing": missing_count,
                "overall_freshness": overall,
            },
        )

    def get_slices_range(
        self,
        start: str | datetime,
        end: str | datetime,
        interval_seconds: int = 3600,
        symbols: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> TimeSliceRange:
        """获取时间范围内的多个切片。"""
        start_str = self._normalize_timestamp(start)
        end_str = self._normalize_timestamp(end)
        start_dt = self._parse_iso(start_str)
        end_dt = self._parse_iso(end_str)

        slices: list[TimeSlice] = []
        current = start_dt
        while current <= end_dt:
            ts = current.strftime("%Y-%m-%dT%H:%M:%S")
            slices.append(self.get_slice_at(ts, symbols=symbols, domains=domains))
            current += timedelta(seconds=interval_seconds)

        return TimeSliceRange(
            start=start_str,
            end=end_str,
            interval_seconds=interval_seconds,
            slice_count=len(slices),
            slices=slices,
        )

    # ------------------------------------------------------------------
    # 域分发
    # ------------------------------------------------------------------

    def _build_domain_slice(
        self,
        domain: str,
        timestamp: str,
        symbols: list[str] | None,
        timeframe: str,
        requested_dt: datetime,
    ) -> DomainSlice:
        """按域名分发到对应的查询方法。"""
        dispatch = {
            "klines": self._slice_klines,
            "technical_indicators": self._slice_technical_indicators,
            "feature_standardization": self._slice_feature_standardization,
            "cross_asset": self._slice_cross_asset,
            "portfolio_risk": self._slice_portfolio_risk,
            "macro_context": self._slice_macro_context,
            "market_breadth": self._slice_market_breadth,
            "asset_readiness": self._slice_asset_readiness,
            "ai_market_context": self._slice_ai_market_context,
            "exchange_comparison": self._slice_exchange_comparison,
        }
        handler = dispatch.get(domain)
        if not handler:
            return DomainSlice(domain=domain, status="missing")
        try:
            return handler(timestamp, symbols, timeframe, requested_dt)
        except Exception as e:
            logger.warning("域 %s 查询失败: %s", domain, e)
            return DomainSlice(domain=domain, status="missing")

    def _compute_staleness_and_status(
        self, domain: str, data_ts_str: str | None, requested_dt: datetime
    ) -> tuple[str, float | None]:
        """计算 staleness 并返回 (status, staleness_seconds)。"""
        if not data_ts_str:
            return "missing", None
        data_dt = self._parse_iso(data_ts_str)
        staleness = (requested_dt - data_dt).total_seconds()
        threshold = self.STALENESS_THRESHOLDS.get(domain, 7200)
        status = "ready" if staleness <= threshold else "stale"
        return status, staleness

    # ------------------------------------------------------------------
    # 各域切片构建
    # ------------------------------------------------------------------

    def _slice_klines(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        rows = self.repository.fetch_klines_at(timestamp, symbols, timeframe)
        if not rows:
            return DomainSlice(domain="klines", status="missing")
        data_ts = rows[0].get("open_time")
        status, staleness = self._compute_staleness_and_status("klines", data_ts, requested_dt)
        payload = {r["symbol"]: r for r in rows}
        return DomainSlice(
            domain="klines", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=payload,
        )

    def _slice_technical_indicators(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        rows = self.repository.fetch_technical_indicators_at(timestamp, symbols, timeframe)
        if not rows:
            return DomainSlice(domain="technical_indicators", status="missing")
        data_ts = rows[0].get("open_time")
        status, staleness = self._compute_staleness_and_status(
            "technical_indicators", data_ts, requested_dt
        )
        payload = {r["symbol"]: r for r in rows}
        return DomainSlice(
            domain="technical_indicators", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=payload,
        )

    def _slice_feature_standardization(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        result = self.repository.fetch_feature_std_bundle_at(timestamp)
        if not result:
            return DomainSlice(domain="feature_standardization", status="missing")
        data_ts = result["snapshot_time"]
        status, staleness = self._compute_staleness_and_status(
            "feature_standardization", data_ts, requested_dt
        )
        payload = result["bundle"]
        # 按 symbols 过滤
        if symbols and "assets" in payload:
            payload["assets"] = [
                a for a in payload["assets"] if a.get("symbol") in symbols
            ]
        return DomainSlice(
            domain="feature_standardization", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=payload,
        )

    def _slice_cross_asset(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        correlation = self.repository.fetch_correlation_at(timestamp)
        rs = self.repository.fetch_relative_strength_at(timestamp, symbols)
        rotation = self.repository.fetch_sector_rotation_at(timestamp)
        fund_flow = self.repository.fetch_fund_flow_at(timestamp)
        if not correlation and not rs and not rotation and not fund_flow:
            return DomainSlice(domain="cross_asset", status="missing")
        data_ts = (correlation or {}).get("snapshot_time")
        status, staleness = self._compute_staleness_and_status("cross_asset", data_ts, requested_dt)
        return DomainSlice(
            domain="cross_asset", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness,
            payload={
                "correlation": correlation,
                "relative_strength": rs,
                "sector_rotation": rotation,
                "fund_flow": fund_flow,
            },
        )

    def _slice_portfolio_risk(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        row = self.repository.fetch_portfolio_risk_at(timestamp)
        if not row:
            return DomainSlice(domain="portfolio_risk", status="missing")
        data_ts = row.get("snapshot_time")
        status, staleness = self._compute_staleness_and_status(
            "portfolio_risk", data_ts, requested_dt
        )
        return DomainSlice(
            domain="portfolio_risk", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=row,
        )

    def _slice_macro_context(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        rows = self.repository.fetch_macro_context_at(timestamp)
        if not rows:
            return DomainSlice(domain="macro_context", status="missing")
        data_ts = rows[0].get("snapshot_time")
        status, staleness = self._compute_staleness_and_status(
            "macro_context", data_ts, requested_dt
        )
        return DomainSlice(
            domain="macro_context", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness,
            payload={"factors": rows},
        )

    def _slice_market_breadth(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        row = self.repository.fetch_market_breadth_at(timestamp)
        if not row:
            return DomainSlice(domain="market_breadth", status="missing")
        data_ts = row.get("snapshot_time")
        status, staleness = self._compute_staleness_and_status(
            "market_breadth", data_ts, requested_dt
        )
        return DomainSlice(
            domain="market_breadth", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=row,
        )

    def _slice_asset_readiness(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        row = self.repository.fetch_asset_readiness_at(timestamp)
        if not row:
            return DomainSlice(domain="asset_readiness", status="missing")
        data_ts = row.get("snapshot_time")
        status, staleness = self._compute_staleness_and_status(
            "asset_readiness", data_ts, requested_dt
        )
        return DomainSlice(
            domain="asset_readiness", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=row,
        )

    def _slice_ai_market_context(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        entity_keys = None
        if symbols:
            entity_keys = [s.split("/")[0] for s in symbols]
        rows = self.repository.fetch_ai_context_at(timestamp, entity_keys)
        if not rows:
            return DomainSlice(domain="ai_market_context", status="missing")
        data_ts = rows[0].get("snapshot_time")
        status, staleness = self._compute_staleness_and_status(
            "ai_market_context", data_ts, requested_dt
        )
        return DomainSlice(
            domain="ai_market_context", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness,
            payload={"entities": rows},
        )

    def _slice_exchange_comparison(
        self, timestamp: str, symbols: list[str] | None, timeframe: str, requested_dt: datetime
    ) -> DomainSlice:
        rows = self.repository.fetch_exchange_comparison_at(timestamp, symbols)
        if not rows:
            return DomainSlice(domain="exchange_comparison", status="missing")
        data_ts = rows[0].get("timestamp")
        status, staleness = self._compute_staleness_and_status(
            "exchange_comparison", data_ts, requested_dt
        )
        payload = {}
        for r in rows:
            sym = r.get("symbol", "unknown")
            payload.setdefault(sym, []).append(r)
        return DomainSlice(
            domain="exchange_comparison", status=status,
            data_timestamp=data_ts, staleness_seconds=staleness, payload=payload,
        )

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------
    # 特征历史序列查询
    # ------------------------------------------------------------------

    def get_feature_history(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        features: list[str] | None = None,
        source: str = "technical_indicators",
        timeframe: str = "1h",
    ) -> FeatureHistory:
        """获取指定资产的特征连续历史序列。

        Args:
            symbol: 资产代码 (e.g. "BTC/USDT")
            start: 起始时间
            end: 结束时间
            features: 需要的特征列表（为空则返回全部）
            source: 数据源 ("klines" | "technical_indicators" | "feature_standardization")
            timeframe: K 线周期
        """
        start_str = self._normalize_timestamp(start)
        end_str = self._normalize_timestamp(end)

        if source == "klines":
            rows = self.repository.fetch_klines_history(symbol, start_str, end_str, timeframe)
            time_col = "open_time"
        elif source == "technical_indicators":
            rows = self.repository.fetch_technical_indicators_history(
                symbol, start_str, end_str, features, timeframe
            )
            time_col = "open_time"
        elif source == "feature_standardization":
            rows = self.repository.fetch_feature_std_history(symbol, start_str, end_str)
            time_col = "snapshot_time"
        else:
            rows = []
            time_col = "timestamp"

        # 构建 series: feature_name -> [{timestamp, value}, ...]
        series: dict[str, list[dict]] = {}
        if rows:
            exclude_cols = {time_col, "symbol", "timeframe", "id"}
            available_features = [
                k for k in rows[0].keys() if k not in exclude_cols
            ]
            target_features = features if features else available_features

            for feat in target_features:
                if feat in (rows[0] if rows else {}):
                    series[feat] = [
                        {"timestamp": r.get(time_col), "value": r.get(feat)}
                        for r in rows
                    ]

        return FeatureHistory(
            symbol=symbol,
            features=list(series.keys()),
            start=start_str,
            end=end_str,
            point_count=len(rows),
            series=series,
        )

