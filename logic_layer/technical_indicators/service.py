from __future__ import annotations

from typing import Optional

import pandas as pd

from database.db_manager import DBManager
from logic_layer.technical_indicators.aggregator import MultiExchangeKlineAggregator
from logic_layer.technical_indicators.calculator import TechnicalIndicatorCalculator
from logic_layer.technical_indicators.enricher import MarketFeatureEnricher
from logic_layer.technical_indicators.repository import TechnicalIndicatorRepository
from logic_layer.technical_indicators.utils import bars_to_timedelta


class TechnicalIndicatorService:
    """技术指标模块统一服务入口。"""

    INDICATOR_LOOKBACK_BARS = 200

    def __init__(
        self,
        db: DBManager | None = None,
        repository: TechnicalIndicatorRepository | None = None,
        aggregator: MultiExchangeKlineAggregator | None = None,
        calculator: TechnicalIndicatorCalculator | None = None,
        enricher: MarketFeatureEnricher | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.repository = repository or TechnicalIndicatorRepository(self.db)
        self.aggregator = aggregator or MultiExchangeKlineAggregator()
        self.calculator = calculator or TechnicalIndicatorCalculator()
        self.enricher = enricher or MarketFeatureEnricher()

    def init_storage(self):
        try:
            self.db.init_tables()
        except Exception:
            # analytics DB may have VIEWs for exchange_data tables;
            # CREATE INDEX on VIEWs raises OperationalError — safe to skip.
            pass

    def merge_klines(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        since_days: Optional[int] = None,
        full_refresh: bool = False,
    ):
        targets = self._resolve_targets("klines", symbol, timeframe)
        merged_frames: list[pd.DataFrame] = []
        skipped = 0

        for target_symbol, target_timeframe in targets:
            # 增量跳过：无新 klines 时直接跳过
            if not full_refresh and since_days is None:
                latest_raw = self._as_utc_timestamp(
                    self.repository.fetch_latest_open_time(
                        "klines", target_symbol, target_timeframe
                    )
                )
                latest_merged = self._as_utc_timestamp(
                    self.repository.fetch_latest_open_time(
                        "merged_klines", target_symbol, target_timeframe
                    )
                )
                if (
                    latest_raw is not None
                    and latest_merged is not None
                    and latest_raw <= latest_merged
                ):
                    skipped += 1
                    continue

            since_time = self._resolve_merge_since_time(
                target_symbol,
                target_timeframe,
                since_days,
                full_refresh,
            )
            raw_klines = self.repository.fetch_raw_klines(
                target_symbol,
                target_timeframe,
                since_time=since_time,
            )
            merged = self.aggregator.merge(raw_klines.to_dict("records"))
            self.repository.save_merged_klines(merged)
            if not merged.empty:
                merged_frames.append(merged)

        if skipped > 0:
            from loguru import logger
            logger.debug("merge_klines 跳过 {} 个无新数据的 target", skipped)

        return self._concat_frames(merged_frames)

    def calculate_indicators(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        since_days: Optional[int] = None,
        full_refresh: bool = False,
    ):
        targets = self._resolve_targets("merged_klines", symbol, timeframe)
        indicator_frames: list[pd.DataFrame] = []
        skipped = 0

        for target_symbol, target_timeframe in targets:
            # 增量跳过：merged_klines 无更新时跳过指标计算
            if not full_refresh and since_days is None:
                latest_merged = self._as_utc_timestamp(
                    self.repository.fetch_latest_open_time(
                        "merged_klines", target_symbol, target_timeframe
                    )
                )
                latest_indicator = self._as_utc_timestamp(
                    self.repository.fetch_latest_open_time(
                        "technical_indicators", target_symbol, target_timeframe
                    )
                )
                if (
                    latest_merged is not None
                    and latest_indicator is not None
                    and latest_merged <= latest_indicator
                ):
                    skipped += 1
                    continue

            calculation_start = self._resolve_indicator_start_time(
                target_symbol,
                target_timeframe,
                since_days,
                full_refresh,
            )
            merged = self.repository.fetch_merged_klines(
                target_symbol,
                target_timeframe,
                since_time=calculation_start,
            )
            indicators = self.calculator.calculate(merged)
            if indicators.empty:
                continue

            indicators = self._enrich_market_context(
                target_symbol,
                indicators,
                since_time=calculation_start,
            )

            if since_days is not None:
                cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=since_days)
                indicators = indicators[indicators["open_time"] >= cutoff]

            self.repository.save_technical_indicators(indicators)
            indicator_frames.append(indicators)

        if skipped > 0:
            from loguru import logger
            logger.debug("calculate_indicators 跳过 {} 个无新数据的 target", skipped)

        return self._concat_frames(indicator_frames)

    def refresh_all(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        since_days: Optional[int] = None,
        full_refresh: bool = False,
    ):
        self.merge_klines(symbol, timeframe, since_days, full_refresh=full_refresh)
        return self.calculate_indicators(
            symbol,
            timeframe,
            since_days,
            full_refresh=full_refresh,
        )

    def _resolve_targets(
        self,
        source_table: str,
        symbol: Optional[str],
        timeframe: Optional[str],
    ) -> list[tuple[str, str]]:
        if symbol and timeframe:
            return [(symbol, timeframe)]

        targets = self.repository.fetch_targets(source_table)
        if symbol:
            targets = [target for target in targets if target[0] == symbol]
        if timeframe:
            targets = [target for target in targets if target[1] == timeframe]
        return targets

    @staticmethod
    def _as_utc_timestamp(value: object | None) -> Optional[pd.Timestamp]:
        """将数据库返回的时间值规范为 UTC-aware Timestamp。"""
        if value is None:
            return None
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _resolve_merge_since_time(
        self,
        symbol: str,
        timeframe: str,
        since_days: Optional[int],
        full_refresh: bool,
    ) -> Optional[pd.Timestamp]:
        if since_days is not None:
            return pd.Timestamp.utcnow() - pd.Timedelta(days=since_days)
        if full_refresh:
            return None

        latest_open_time = self.repository.fetch_latest_open_time(
            "merged_klines",
            symbol,
            timeframe,
        )
        if latest_open_time is None:
            return None
        return self._as_utc_timestamp(latest_open_time)

    def _resolve_indicator_start_time(
        self,
        symbol: str,
        timeframe: str,
        since_days: Optional[int],
        full_refresh: bool,
    ) -> Optional[pd.Timestamp]:
        if since_days is not None:
            base_time = pd.Timestamp.utcnow() - pd.Timedelta(days=since_days)
            return base_time - bars_to_timedelta(timeframe, self.INDICATOR_LOOKBACK_BARS)
        if full_refresh:
            return None

        latest_open_time = self.repository.fetch_latest_open_time(
            "technical_indicators",
            symbol,
            timeframe,
        )
        if latest_open_time is None:
            return None
        latest_open_time = self._as_utc_timestamp(latest_open_time)
        return latest_open_time - bars_to_timedelta(
            timeframe,
            self.INDICATOR_LOOKBACK_BARS,
        )

    def _enrich_market_context(
        self,
        symbol: str,
        indicators: pd.DataFrame,
        since_time: Optional[pd.Timestamp] = None,
    ) -> pd.DataFrame:
        tickers = self.repository.fetch_ticker_snapshots(symbol, since_time=since_time)
        funding_rates = self.repository.fetch_funding_snapshots(symbol, since_time=since_time)
        orderbooks = self.repository.fetch_orderbook_snapshots(symbol, since_time=since_time)
        return self.enricher.enrich(indicators, tickers, funding_rates, orderbooks)

    @staticmethod
    def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
        valid_frames = [frame for frame in frames if not frame.empty]
        if not valid_frames:
            return pd.DataFrame()
        return pd.concat(valid_frames, ignore_index=True)

    def close(self):
        self.db.close()
