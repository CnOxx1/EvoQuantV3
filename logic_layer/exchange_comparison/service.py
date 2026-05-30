from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from database.db_manager import DBManager
from logic_layer.exchange_comparison.aligner import SnapshotAligner
from logic_layer.exchange_comparison.comparator import ExchangeComparator
from logic_layer.exchange_comparison.models import ExchangeComparisonConfig
from logic_layer.exchange_comparison.repository import ExchangeComparisonRepository


class ExchangeComparisonService:
    """交易所对比模块统一编排入口。"""

    def __init__(
        self,
        db: DBManager | None = None,
        repository: ExchangeComparisonRepository | None = None,
        aligner: SnapshotAligner | None = None,
        comparator: ExchangeComparator | None = None,
        config: ExchangeComparisonConfig | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.repository = repository or ExchangeComparisonRepository(self.db)
        self.aligner = aligner or SnapshotAligner()
        self.comparator = comparator or ExchangeComparator()
        self.config = config or ExchangeComparisonConfig()

    def init_storage(self):
        self.db.init_tables()

    def build_latest_snapshots(
        self,
        symbol: Optional[str] = None,
        persist: bool = True,
        as_of: Optional[datetime] = None,
        config: ExchangeComparisonConfig | None = None,
    ) -> pd.DataFrame:
        active_config = config or self.config
        tickers = self.repository.fetch_latest_ticker_snapshots(symbol)
        if tickers.empty:
            logger.warning("未获取到 ticker 快照，无法生成交易所对比结果")
            return pd.DataFrame()

        orderbooks = self.repository.fetch_orderbook_candidates(
            symbol=symbol,
            lookback_seconds=active_config.snapshot_lookback_seconds,
        )
        market_info = self.repository.fetch_market_info(
            symbol=symbol,
            market_type=active_config.market_type,
        )
        funding_rates = (
            self.repository.fetch_funding_candidates(
                symbol=symbol,
                lookback_seconds=max(
                    active_config.max_funding_age_seconds,
                    active_config.funding_window_seconds,
                ),
            )
            if active_config.include_funding_context
            else pd.DataFrame()
        )
        indicator_context = (
            self.repository.fetch_indicator_context(
                symbol=symbol,
                timeframe=active_config.indicator_timeframe,
                as_of=as_of,
                lookback_seconds=active_config.max_indicator_age_seconds,
            )
            if active_config.include_indicator_context
            else pd.DataFrame()
        )

        aligned = self.aligner.align(
            tickers=tickers,
            orderbooks=orderbooks,
            market_info=market_info,
            funding_rates=funding_rates,
            indicator_context=indicator_context,
            config=active_config,
        )
        comparisons = self.comparator.compare(
            aligned_snapshots=aligned,
            config=active_config,
            as_of=as_of,
        )

        if persist and not comparisons.empty:
            self.repository.save_comparison_snapshots(comparisons)

        logger.info(f"已生成 {len(comparisons)} 条交易所对比快照")
        return comparisons

    def refresh_latest(
        self,
        symbol: Optional[str] = None,
        as_of: Optional[datetime] = None,
        config: ExchangeComparisonConfig | None = None,
    ) -> pd.DataFrame:
        return self.build_latest_snapshots(
            symbol=symbol,
            persist=True,
            as_of=as_of,
            config=config,
        )

    def close(self):
        self.db.close()
