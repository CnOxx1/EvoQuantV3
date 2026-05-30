import sys
import threading
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import EXCHANGE_DERIVATIVES_CONFIG
from database.db_manager import DBManager
from data_layer.exchange_data.basis import BasisCollector
from data_layer.exchange_data.funding import FundingRateCollector
from data_layer.exchange_data.kline import KlineCollector
from data_layer.exchange_data.liquidations import LiquidationsCollector
from data_layer.exchange_data.market_info import MarketInfoCollector
from data_layer.exchange_data.models import (
    BasisSnapshot,
    FundingRate,
    MarketInfo,
    OpenInterestSnapshot,
    OrderBook,
    OrderBookLevel,
    PositioningSnapshot,
    Ticker,
    TradeFlowBar,
)
from data_layer.exchange_data.open_interest import OpenInterestCollector
from data_layer.exchange_data.orderbook import OrderBookCollector
from data_layer.exchange_data.service import ExchangeDataService
from data_layer.exchange_data.ticker import TickerCollector
from data_layer.exchange_data.trades import TradesCollector
from data_layer.exchange_data.long_short_ratio import LongShortRatioCollector
from logic_layer.technical_indicators.repository import TechnicalIndicatorRepository


class StaticClientManager:
    def __init__(self, client):
        self.client = client
        self.calls: list[tuple[str, str]] = []

    def get_client(self, exchange_name, market_type="spot"):
        self.calls.append((exchange_name, market_type))
        if isinstance(self.client, dict):
            return self.client[market_type]
        return self.client


class BatchTickerClient:
    has = {"fetchTickers": True}

    def __init__(self):
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []

    def fetch_tickers(self, symbols):
        self.batch_calls.append(list(symbols))
        payload = {}
        for index, symbol in enumerate(symbols, start=1):
            payload[symbol] = {
                "symbol": symbol,
                "last": 100 + index,
                "open": 90 + index,
                "bid": 99 + index,
                "bidVolume": 10 + index,
                "ask": 101 + index,
                "askVolume": 20 + index,
                "previousClose": 95 + index,
                "high": 110 + index,
                "low": 80 + index,
                "vwap": 98 + index,
                "baseVolume": 1000 + index,
                "quoteVolume": 2000 + index,
                "change": 5 + index,
                "percentage": 6 + index,
                "timestamp": 1_700_000_000_000 + index,
            }
        return payload

    def fetch_ticker(self, symbol):
        self.single_calls.append(symbol)
        raise AssertionError("batch ticker path should not call fetch_ticker")


class PaginatedFundingClient:
    def __init__(self):
        self.history_calls: list[tuple[str, int | None, int | None]] = []
        self.base_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)

    def fetch_funding_rate_history(self, symbol, since=None, limit=None):
        self.history_calls.append((symbol, since, limit))
        if len(self.history_calls) == 1:
            return [
                {
                    "fundingRate": 0.001,
                    "markPrice": 100.0,
                    "indexPrice": 99.5,
                    "timestamp": self.base_timestamp,
                },
                {
                    "fundingRate": 0.002,
                    "markPrice": 101.0,
                    "indexPrice": 100.0,
                    "timestamp": self.base_timestamp + 1_000,
                },
            ]
        if len(self.history_calls) == 2:
            return [
                {
                    "fundingRate": 0.003,
                    "markPrice": 102.0,
                    "indexPrice": 101.0,
                    "timestamp": self.base_timestamp + 2_000,
                }
            ]
        return []


class RoutedTradesClient:
    def __init__(self, trades_by_symbol):
        self.trades_by_symbol = trades_by_symbol
        self.calls: list[tuple[str, int | None]] = []
        self.markets = {"ready": True}

    def load_markets(self, reload=False):
        return self.markets

    def fetch_trades(self, symbol, limit=None):
        self.calls.append((symbol, limit))
        return list(self.trades_by_symbol.get(symbol, []))


class SwapOpenInterestClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[str] = []
        self.markets = {"ready": True}

    def fetch_open_interest(self, symbol):
        self.calls.append(symbol)
        return dict(self.payload)


class CursorKlineClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, int | None, int | None]] = []

    def fetch_ohlcv(self, symbol, timeframe=None, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        return self.responses.pop(0)


class CachedMarketInfoClient:
    def __init__(self):
        self.load_calls: list[bool] = []
        self.markets = {
            "BTC/USDT": {
                "id": "BTCUSDT",
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "type": "spot",
                "active": True,
                "spot": True,
                "precision": {"price": 0.1, "amount": 0.001},
                "limits": {
                    "price": {"min": 1.0, "max": 1_000_000.0},
                    "amount": {"min": 0.001, "max": 100.0},
                    "cost": {"min": 10.0, "max": 1_000_000.0},
                },
                "maker": 0.001,
                "taker": 0.001,
                "info": {"source": "test"},
            }
        }

    def load_markets(self, reload=False):
        self.load_calls.append(bool(reload))
        return self.markets


def make_market_info() -> MarketInfo:
    return MarketInfo(
        symbol="BTC/USDT",
        exchange_symbol="BTCUSDT",
        base="BTC",
        quote="USDT",
        exchange="binance",
        market_type="spot",
        status="active",
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def test_exchange_service_shared_db_works_across_threads(tmp_path):
    db_path = str(tmp_path / "exchange_threadsafe.sqlite")
    service = ExchangeDataService(db=DBManager(db_path))
    service.init_storage()

    errors: list[str] = []

    def worker():
        try:
            service.market_info_collector.save_to_db([make_market_info()])
        except Exception as exc:  # pragma: no cover - explicit failure capture
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            service.db.close()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []

    verify_db = DBManager(db_path)
    row = verify_db.fetch_one("SELECT COUNT(*) AS count FROM market_info")
    assert row["count"] == 1
    verify_db.close()
    service.close()


def test_ticker_collector_prefers_batch_fetch(monkeypatch, tmp_path):
    client = BatchTickerClient()
    collector = TickerCollector(
        StaticClientManager(client),
        DBManager(str(tmp_path / "ticker_batch.sqlite")),
    )

    monkeypatch.setattr(
        "data_layer.exchange_data.ticker.TARGET_SYMBOLS",
        ["BTC/USDT", "ETH/USDT"],
    )

    tickers = collector.fetch_exchange_tickers("binance")

    assert len(tickers) == 2
    assert client.batch_calls == [["BTC/USDT", "ETH/USDT"]]
    assert client.single_calls == []


def test_ticker_collector_uses_datetime_when_timestamp_missing(monkeypatch, tmp_path):
    collector = TickerCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "ticker_datetime_fallback.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_ticker",
        lambda exchange_name, symbol: {
            "last": 100.0,
            "bid": 99.5,
            "ask": 100.5,
            "timestamp": None,
            "datetime": "2026-05-08T12:00:00Z",
        },
    )

    ticker = collector.fetch_ticker("binance", "BTC/USDT")

    assert ticker is not None
    assert ticker.timestamp == datetime(2026, 5, 8, 12, 0, 0)


def test_ticker_collector_skips_snapshot_without_event_time(monkeypatch, tmp_path):
    """当 ticker 缺少事件时间时，使用采集时刻作为 fallback（不再跳过）。"""
    collector = TickerCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "ticker_missing_time.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_ticker",
        lambda exchange_name, symbol: {
            "last": 100.0,
            "bid": 99.5,
            "ask": 100.5,
            "timestamp": None,
            "datetime": None,
        },
    )

    ticker = collector.fetch_ticker("binance", "BTC/USDT")

    # 不再返回 None，而是使用采集时刻作为 timestamp
    assert ticker is not None
    assert ticker.last_price == 100.0
    assert ticker.timestamp is not None


def test_kline_incremental_fetch_uses_latest_db_cursor(tmp_path):
    db = DBManager(str(tmp_path / "kline_cursor.sqlite"))
    db.init_tables()

    latest_open_time = datetime(2026, 5, 5, 13, 14, 0)
    db.execute_many(
        """
        INSERT INTO klines (
            symbol, exchange, timeframe, open_time,
            open, high, low, close, volume
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                "1m",
                latest_open_time.isoformat(),
                100.0,
                101.0,
                99.0,
                100.5,
                12.0,
            )
        ],
    )
    db.commit()

    client = CursorKlineClient(
        responses=[
            [
                [1_746_452_280_000, 100.0, 101.0, 99.0, 100.5, 10.0],
                [1_746_452_340_000, 101.0, 102.0, 100.0, 101.5, 11.0],
                [1_746_452_400_000, 102.0, 103.0, 101.0, 102.5, 12.0],
            ]
        ]
    )
    collector = KlineCollector(StaticClientManager(client), db)

    klines = collector.fetch_incremental_klines("binance", "BTC/USDT", "1m")

    expected_since = int(
        (latest_open_time - timedelta(minutes=2))
        .replace(tzinfo=timezone.utc)
        .timestamp() * 1000
    )
    assert client.calls[0] == ("BTC/USDT", "1m", expected_since, collector.BATCH_LIMIT)
    assert len(klines) == 3

    db.close()


def test_kline_collector_skips_rows_with_missing_volume_instead_of_faking_zero(tmp_path):
    valid_row = [1_746_452_340_000, 101.0, 102.0, 100.0, 101.5, 11.0]
    client = CursorKlineClient(
        responses=[
            [
                [1_746_452_280_000, 100.0, 101.0, 99.0, 100.5, None],
                valid_row,
            ]
        ]
    )
    collector = KlineCollector(
        StaticClientManager(client),
        DBManager(str(tmp_path / "kline_missing_volume.sqlite")),
    )

    klines = collector.fetch_klines("binance", "BTC/USDT", "1m")

    assert len(klines) == 1
    assert klines[0].open_time == datetime.fromtimestamp(
        valid_row[0] / 1000,
        tz=timezone.utc,
    ).replace(tzinfo=None)
    assert klines[0].volume == 11.0


def test_funding_history_fetch_paginates_until_exhausted(tmp_path):
    client = PaginatedFundingClient()
    collector = FundingRateCollector(
        StaticClientManager(client),
        DBManager(str(tmp_path / "funding_history.sqlite")),
    )
    collector.HISTORY_BATCH_LIMIT = 2

    history = collector.fetch_funding_history("binance", "BTC/USDT", days=1)

    assert len(history) == 3
    assert client.history_calls[0][0] == "BTC/USDT:USDT"
    assert client.history_calls[0][2] == 2
    assert client.history_calls[1][1] == client.base_timestamp + 1_001


def test_funding_and_open_interest_use_swap_clients(tmp_path):
    funding_client = PaginatedFundingClient()
    open_interest_client = SwapOpenInterestClient(
        {
            "openInterestValue": 123456.0,
            "timestamp": 1_700_000_000_000,
        }
    )
    manager = StaticClientManager(
        {
            "spot": object(),
            "swap": funding_client,
        }
    )
    funding_collector = FundingRateCollector(
        manager,
        DBManager(str(tmp_path / "funding_swap.sqlite")),
    )
    funding_collector.HISTORY_BATCH_LIMIT = 2

    funding_collector.fetch_funding_history("binance", "BTC/USDT", days=1)

    assert ("binance", "swap") in manager.calls
    assert funding_client.history_calls[0][0] == "BTC/USDT:USDT"

    oi_manager = StaticClientManager(
        {
            "spot": object(),
            "swap": open_interest_client,
        }
    )
    open_interest_collector = OpenInterestCollector(
        oi_manager,
        DBManager(str(tmp_path / "oi_swap.sqlite")),
    )

    raw = open_interest_collector._fetch_open_interest("binance", "BTC/USDT")

    assert raw["openInterestValue"] == 123456.0
    assert ("binance", "swap") in oi_manager.calls
    assert open_interest_client.calls == ["BTC/USDT:USDT"]


def test_orderbook_collector_uses_datetime_when_timestamp_missing(monkeypatch, tmp_path):
    collector = OrderBookCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "orderbook_datetime_fallback.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_orderbook",
        lambda exchange_name, symbol, limit: {
            "bids": [[99.5, 2.0]],
            "asks": [[100.5, 3.0]],
            "timestamp": None,
            "datetime": "2026-05-08T12:00:00Z",
        },
    )

    orderbook = collector.fetch_orderbook("binance", "BTC/USDT", limit=5)

    assert orderbook is not None
    assert orderbook.timestamp == datetime(2026, 5, 8, 12, 0, 0)


def test_orderbook_collector_skips_snapshot_without_event_time(monkeypatch, tmp_path):
    collector = OrderBookCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "orderbook_missing_time.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_orderbook",
        lambda exchange_name, symbol, limit: {
            "bids": [[99.5, 2.0]],
            "asks": [[100.5, 3.0]],
            "timestamp": None,
            "datetime": None,
        },
    )

    orderbook = collector.fetch_orderbook("binance", "BTC/USDT", limit=5)

    assert orderbook is None


def test_orderbook_collector_warns_once_per_exchange_for_missing_event_time(monkeypatch, tmp_path):
    collector = OrderBookCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "orderbook_missing_time_once.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_orderbook",
        lambda exchange_name, symbol, limit: {
            "bids": [[99.5, 2.0]],
            "asks": [[100.5, 3.0]],
            "timestamp": None,
            "datetime": None,
        },
    )

    warning_messages: list[str] = []
    debug_messages: list[str] = []
    monkeypatch.setattr(
        "data_layer.exchange_data.orderbook.logger.warning",
        lambda message: warning_messages.append(message),
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.orderbook.logger.debug",
        lambda message: debug_messages.append(message),
    )

    first = collector.fetch_orderbook("binance", "BTC/USDT", limit=5)
    second = collector.fetch_orderbook("binance", "ETH/USDT", limit=5)

    assert first is None
    assert second is None
    assert len(warning_messages) == 1
    assert len(debug_messages) == 1
    assert "后续同类情况将仅记录 debug" in warning_messages[0]
    assert "[binance] ETH/USDT" in debug_messages[0]


def test_market_info_uses_cached_markets_until_forced(monkeypatch, tmp_path):
    client = CachedMarketInfoClient()
    collector = MarketInfoCollector(
        StaticClientManager(client),
        DBManager(str(tmp_path / "market_cache.sqlite")),
    )

    monkeypatch.setattr(
        "data_layer.exchange_data.market_info.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.market_info.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )

    first = collector.fetch_target_markets(force=False)
    second = collector.fetch_target_markets(force=False)
    third = collector.fetch_target_markets(force=True)

    assert len(first) == 1
    assert len(second) == 1
    assert len(third) == 1
    assert client.load_calls == [True, False, True]


def test_cleanup_historical_data_prunes_old_high_frequency_rows(monkeypatch, tmp_path):
    db = DBManager(str(tmp_path / "cleanup.sqlite"))
    service = ExchangeDataService(db=db)
    service.init_storage()

    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=40)).replace(tzinfo=None)
    new_timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

    db.execute_many(
        """
        INSERT INTO tickers (
            symbol, exchange, last_price, open_24h, bid, bid_volume,
            ask, ask_volume, previous_close, high_24h, low_24h,
            vwap_24h, volume_24h, quote_volume_24h,
            change_abs_24h, change_24h, mid_price, spread, spread_bps, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, old_timestamp.isoformat()),
            ("BTC/USDT", "binance", 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, new_timestamp.isoformat()),
        ],
    )
    db.execute_many(
        """
        INSERT INTO orderbook_snapshots (
            symbol, exchange, snapshot_depth, best_bid, best_ask,
            mid_price, spread, spread_bps, bid_depth_notional,
            ask_depth_notional, depth_imbalance, bids_json, asks_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 20, 1, 1, 1, 1, 1, 1, 1, 0, "[]", "[]", old_timestamp.isoformat()),
            ("BTC/USDT", "binance", 20, 1, 1, 1, 1, 1, 1, 1, 0, "[]", "[]", new_timestamp.isoformat()),
        ],
    )
    db.execute_many(
        """
        INSERT INTO funding_rates (
            symbol, exchange, funding_rate, mark_price,
            index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 0.001, 100, 99, None, old_timestamp.isoformat()),
            ("BTC/USDT", "binance", 0.001, 100, 99, None, new_timestamp.isoformat()),
        ],
    )
    db.commit()

    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DATA_RETENTION",
        {
            "ticker_days": 30,
            "orderbook_days": 14,
            "funding_days": 365,
            "cleanup_interval": 86400,
        },
    )

    deleted = service.cleanup_historical_data()

    assert deleted == {
        "tickers": 1,
        "orderbook_snapshots": 1,
        "funding_rates": 0,
        "trade_flow_bars": 0,
        "open_interest_snapshots": 0,
        "basis_snapshots": 0,
        "liquidation_bars": 0,
        "positioning_snapshots": 0,
    }
    assert db.fetch_one("SELECT COUNT(*) AS count FROM tickers")["count"] == 1
    assert db.fetch_one("SELECT COUNT(*) AS count FROM orderbook_snapshots")["count"] == 1
    assert db.fetch_one("SELECT COUNT(*) AS count FROM funding_rates")["count"] == 2

    service.close()


def test_exchange_scheduler_jobs_use_safe_runtime_defaults(tmp_path):
    service = ExchangeDataService(db=DBManager(str(tmp_path / "scheduler.sqlite")))
    scheduler = service.build_scheduler()

    assert isinstance(scheduler, BlockingScheduler)

    kline_1m_job = scheduler.get_job("kline_1m")
    kline_1d_job = scheduler.get_job("kline_1d")
    ticker_job = scheduler.get_job("ticker")
    orderbook_job = scheduler.get_job("orderbook")
    cleanup_job = scheduler.get_job("exchange_cleanup")

    assert kline_1m_job is not None
    assert kline_1m_job.max_instances == 1
    assert int(kline_1m_job.trigger.interval.total_seconds()) == 60

    assert kline_1d_job is not None
    assert int(kline_1d_job.trigger.interval.total_seconds()) == 86400

    assert ticker_job is not None
    assert ticker_job.coalesce is True
    assert ticker_job.max_instances == 1
    assert ticker_job.misfire_grace_time >= 15

    # 分层深度采集：检查 core tier 的 orderbook job
    orderbook_core_job = scheduler.get_job("orderbook_core")
    assert orderbook_core_job is not None
    assert orderbook_core_job.coalesce is True
    assert orderbook_core_job.max_instances == 1
    assert orderbook_core_job.misfire_grace_time >= 15

    assert cleanup_job is not None
    assert cleanup_job.coalesce is True
    assert cleanup_job.max_instances == 1

    service.close()


def test_exchange_source_coverage_marks_semantic_scope_and_unconfigured_sources(tmp_path):
    db = DBManager(str(tmp_path / "exchange_coverage.sqlite"))
    service = ExchangeDataService(db=db)
    service.init_storage()

    trade_collector = TradesCollector(StaticClientManager(None), db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    trade_collector.save_to_db(
        [
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="spot",
                interval="1m",
                open_time=now,
                trade_count=12,
                buy_trade_count=7,
                sell_trade_count=5,
                buy_notional=120000.0,
                sell_notional=80000.0,
                aggressive_buy_notional=120000.0,
                aggressive_sell_notional=80000.0,
                net_taker_notional=40000.0,
                cvd=40000.0,
                avg_trade_notional=16666.67,
                largest_trade_notional=50000.0,
            )
        ]
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="trade_flow",
        job_name="trade_flow_once",
        status="success",
        item_count=1,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )

    coverage = service.load_source_coverage(
        source_names=["trade_flow", "liquidations"],
    )
    coverage_map = {
        item["source_name"]: item
        for item in coverage["sources"]
    }

    assert coverage["source_count"] == 2
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 2
    assert coverage_map["trade_flow"]["health_status"] == "ready"
    assert coverage_map["trade_flow"]["semantic_scope"] == "spot_only"
    assert coverage_map["trade_flow"]["is_ready_for_ai"] is False
    assert coverage_map["trade_flow"]["quality_notes"]
    assert coverage_map["liquidations"]["configuration_ready"] is False
    assert coverage_map["liquidations"]["health_status"] == "unconfigured"
    assert coverage_map["liquidations"]["is_ready_for_ai"] is False

    service.close()


def test_trades_collector_collects_spot_and_derivatives_trade_flow(monkeypatch, tmp_path):
    spot_client = RoutedTradesClient(
        {
            "BTC/USDT": [
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 100.0,
                    "amount": 1.0,
                    "cost": 100.0,
                    "side": "buy",
                }
            ]
        }
    )
    swap_client = RoutedTradesClient(
        {
            "BTC/USDT:USDT": [
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 101.0,
                    "amount": 2.0,
                    "cost": 202.0,
                    "side": "sell",
                }
            ]
        }
    )
    manager = StaticClientManager(
        {
            "spot": spot_client,
            "swap": swap_client,
        }
    )
    collector = TradesCollector(
        manager,
        DBManager(str(tmp_path / "dual_trade_flow.sqlite")),
    )

    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )

    bars = collector.fetch_trade_flow_bars()

    assert {bar.market_type for bar in bars} == {"spot", "linear_swap"}
    assert ("binance", "spot") in manager.calls
    assert ("binance", "swap") in manager.calls
    assert spot_client.calls[0][0] == "BTC/USDT"
    assert swap_client.calls[0][0] == "BTC/USDT:USDT"


def test_trades_collector_skips_incomplete_trades_instead_of_faking_sell_pressure(
    monkeypatch,
    tmp_path,
):
    spot_client = RoutedTradesClient(
        {
            "BTC/USDT": [
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 100.0,
                    "amount": 1.0,
                    "cost": 100.0,
                    "side": "buy",
                },
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 101.0,
                    "amount": 1.0,
                    "cost": 101.0,
                    "side": None,
                },
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 101.0,
                    "amount": 2.0,
                    "side": "sell",
                },
                {
                    "timestamp": 1_700_000_000_000,
                    "price": None,
                    "amount": None,
                    "cost": None,
                    "side": "buy",
                },
            ]
        }
    )
    manager = StaticClientManager(
        {
            "spot": spot_client,
            "swap": RoutedTradesClient({}),
        }
    )
    collector = TradesCollector(
        manager,
        DBManager(str(tmp_path / "trade_flow_quality.sqlite")),
    )

    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )

    bars = [
        bar
        for bar in collector.fetch_trade_flow_bars()
        if bar.market_type == "spot"
    ]

    assert len(bars) == 1
    bar = bars[0]
    assert bar.trade_count == 2
    assert bar.buy_trade_count == 1
    assert bar.sell_trade_count == 1
    assert bar.buy_notional == 100.0
    assert bar.sell_notional == 202.0
    assert bar.avg_trade_notional == 151.0
    assert bar.largest_trade_notional == 202.0

    payload = json.loads(bar.raw_payload_json)
    diagnostics = payload["diagnostics"]
    assert diagnostics["raw_trade_count"] == 4
    assert diagnostics["usable_trade_count"] == 2
    assert diagnostics["excluded_trade_count"] == 2
    assert diagnostics["excluded_missing_side_count"] == 1
    assert diagnostics["excluded_missing_notional_count"] == 1


def test_trades_collector_skips_bar_without_usable_trades(monkeypatch, tmp_path):
    spot_client = RoutedTradesClient(
        {
            "BTC/USDT": [
                {
                    "timestamp": 1_700_000_000_000,
                    "price": 100.0,
                    "amount": 1.0,
                    "cost": 100.0,
                    "side": None,
                },
                {
                    "timestamp": 1_700_000_000_000,
                    "price": None,
                    "amount": None,
                    "cost": None,
                    "side": "buy",
                },
            ]
        }
    )
    manager = StaticClientManager(
        {
            "spot": spot_client,
            "swap": RoutedTradesClient({}),
        }
    )
    collector = TradesCollector(
        manager,
        DBManager(str(tmp_path / "trade_flow_skip_invalid.sqlite")),
    )

    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.trades.collector.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )

    bars = [
        bar
        for bar in collector.fetch_trade_flow_bars()
        if bar.market_type == "spot"
    ]

    assert bars == []


def test_basis_collector_uses_basis_interval_config(tmp_path):
    db = DBManager(str(tmp_path / "basis_interval.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    funding_collector = FundingRateCollector(StaticClientManager(None), db)

    timestamp = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=1_000_000.0,
                change_24h=1.2,
                vwap_24h=99.5,
                timestamp=timestamp,
            )
        ]
    )
    funding_collector.save_to_db(
        [
            FundingRate(
                symbol="BTC/USDT",
                exchange="binance",
                funding_rate=0.001,
                mark_price=100.5,
                index_price=100.2,
                timestamp=timestamp,
            )
        ]
    )

    snapshots = BasisCollector(db).fetch_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].interval == EXCHANGE_DERIVATIVES_CONFIG["basis_interval"]

    db.close()


def test_basis_collector_normalizes_aware_next_funding_time(tmp_path):
    db = DBManager(str(tmp_path / "basis_timezone.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    timestamp = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=1_000_000.0,
                change_24h=1.2,
                vwap_24h=99.5,
                timestamp=timestamp,
            )
        ]
    )
    db.execute_many(
        """
        INSERT INTO latest_funding_rates (
            symbol, exchange, funding_rate, mark_price, index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                0.001,
                100.5,
                100.2,
                "2026-05-08T20:00:00+00:00",
                timestamp.isoformat(),
            )
        ],
    )
    db.commit()

    snapshots = BasisCollector(db).fetch_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].timestamp.tzinfo is None
    assert snapshots[0].next_funding_time is not None
    assert snapshots[0].next_funding_time.tzinfo is None
    assert snapshots[0].annualized_basis_bps is not None

    db.close()


def test_basis_collector_normalizes_aware_datetime_instance():
    normalized = BasisCollector._to_datetime(
        datetime(2026, 5, 8, 20, 0, 0, tzinfo=timezone.utc)
    )

    assert normalized == datetime(2026, 5, 8, 20, 0, 0)
    assert normalized.tzinfo is None


def test_basis_collector_degrades_bad_next_funding_time_without_crashing(tmp_path):
    db = DBManager(str(tmp_path / "basis_bad_time.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    timestamp = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=1_000_000.0,
                change_24h=1.2,
                vwap_24h=99.5,
                timestamp=timestamp,
            )
        ]
    )
    db.execute_many(
        """
        INSERT INTO latest_funding_rates (
            symbol, exchange, funding_rate, mark_price, index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                0.001,
                100.5,
                100.2,
                "not-a-real-timestamp",
                timestamp.isoformat(),
            )
        ],
    )
    db.commit()

    snapshots = BasisCollector(db).fetch_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].timestamp == timestamp
    assert snapshots[0].next_funding_time is None
    assert snapshots[0].basis_bps is not None
    assert snapshots[0].annualized_basis_bps is None

    db.close()


def test_basis_collector_skips_bad_funding_timestamp_instead_of_faking_now(tmp_path):
    db = DBManager(str(tmp_path / "basis_bad_funding_time.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    timestamp = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=1_000_000.0,
                change_24h=1.2,
                vwap_24h=99.5,
                timestamp=timestamp,
            )
        ]
    )
    db.execute_many(
        """
        INSERT INTO latest_funding_rates (
            symbol, exchange, funding_rate, mark_price, index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                0.001,
                100.5,
                100.2,
                "2026-05-08T20:00:00+00:00",
                "not-a-real-funding-time",
            )
        ],
    )
    db.commit()

    snapshots = BasisCollector(db).fetch_snapshots()

    assert snapshots == []
    db.close()


def test_basis_collector_persists_component_time_gap_diagnostics(tmp_path):
    db = DBManager(str(tmp_path / "basis_component_gap.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    ticker_timestamp = datetime(2026, 5, 8, 11, 40, 0)
    funding_timestamp = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=1_000_000.0,
                change_24h=1.2,
                vwap_24h=99.5,
                timestamp=ticker_timestamp,
            )
        ]
    )
    db.execute_many(
        """
        INSERT INTO latest_funding_rates (
            symbol, exchange, funding_rate, mark_price, index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                0.001,
                100.5,
                100.2,
                "2026-05-08T20:00:00+00:00",
                funding_timestamp.isoformat(),
            )
        ],
    )
    db.commit()

    snapshots = BasisCollector(db).fetch_snapshots()

    assert len(snapshots) == 1
    payload = json.loads(snapshots[0].raw_payload_json)
    diagnostics = payload["diagnostics"]
    assert diagnostics["ticker_timestamp"] == ticker_timestamp.isoformat()
    assert diagnostics["component_timestamp_gap_status"] == "wide"
    assert diagnostics["component_timestamp_gap_seconds"] == 1200.0
    assert diagnostics["annualization_status"] == "ok"
    db.close()


def test_open_interest_collector_enriches_change_metrics_from_history(tmp_path):
    db = DBManager(str(tmp_path / "open_interest_change.sqlite"))
    db.init_tables()
    collector = OpenInterestCollector(StaticClientManager(None), db)

    base_time = datetime(2026, 5, 8, 12, 0, 0)
    collector.save_to_db(
        [
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
                timestamp=base_time - timedelta(hours=24),
                open_interest_usd=80.0,
            ),
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
                timestamp=base_time - timedelta(hours=1),
                open_interest_usd=90.0,
            ),
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
                timestamp=base_time - timedelta(minutes=5),
                open_interest_usd=95.0,
            ),
        ]
    )
    collector.save_to_db(
        [
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
                timestamp=base_time,
                open_interest_usd=100.0,
            )
        ]
    )

    latest_row = db.fetch_one(
        """
        SELECT open_interest_change_5m, open_interest_change_1h, open_interest_change_24h
        FROM latest_open_interest_snapshots
        WHERE symbol = ? AND exchange = ?
        """,
        ("BTC/USDT", "binance"),
    )

    assert latest_row["open_interest_change_5m"] == 5.0
    assert latest_row["open_interest_change_1h"] == 10.0
    assert latest_row["open_interest_change_24h"] == 20.0

    db.close()


def test_funding_collector_normalizes_aware_next_funding_time(monkeypatch, tmp_path):
    collector = FundingRateCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "funding_next_time.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_funding_rate",
        lambda exchange_name, symbol: {
            "fundingRate": 0.001,
            "markPrice": 100.0,
            "indexPrice": 99.5,
            "fundingDatetime": "2026-05-08T20:00:00Z",
            "timestamp": 1_715_196_000_000,
        },
    )

    rate = collector.fetch_funding_rate("binance", "BTC/USDT")

    assert rate is not None
    assert rate.next_funding_time is not None
    assert rate.next_funding_time.tzinfo is None


def test_funding_collector_skips_snapshot_without_timestamp(monkeypatch, tmp_path):
    collector = FundingRateCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "funding_missing_timestamp.sqlite")),
    )
    monkeypatch.setattr(
        collector,
        "_fetch_funding_rate",
        lambda exchange_name, symbol: {
            "fundingRate": 0.001,
            "markPrice": 100.0,
            "indexPrice": 99.5,
            "fundingDatetime": "2026-05-08T20:00:00Z",
            "timestamp": None,
        },
    )

    rate = collector.fetch_funding_rate("binance", "BTC/USDT")

    assert rate is None


def test_funding_history_skips_rows_without_valid_timestamp(monkeypatch, tmp_path):
    collector = FundingRateCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "funding_history_missing_timestamp.sqlite")),
    )
    collector.HISTORY_BATCH_LIMIT = 3
    responses = [
        [
            {
                "fundingRate": 0.001,
                "markPrice": 100.0,
                "indexPrice": 99.5,
                "timestamp": 1_700_000_000_000,
            },
            {
                "fundingRate": 0.002,
                "markPrice": 101.0,
                "indexPrice": 100.0,
                "timestamp": None,
            },
            {
                "fundingRate": 0.003,
                "markPrice": 102.0,
                "indexPrice": 101.0,
                "timestamp": "bad",
            },
        ],
        [],
    ]

    monkeypatch.setattr(
        collector,
        "_fetch_funding_history",
        lambda exchange_name, symbol, since=None, limit=None: responses.pop(0),
    )

    history = collector.fetch_funding_history("binance", "BTC/USDT", days=1)

    assert len(history) == 1
    assert history[0].funding_rate == 0.001
    assert history[0].timestamp == datetime(2023, 11, 14, 22, 13, 20)


def test_open_interest_fetch_snapshots_skips_missing_timestamp_and_normalizes_aware_time(
    monkeypatch,
    tmp_path,
):
    collector = OpenInterestCollector(
        StaticClientManager(None),
        DBManager(str(tmp_path / "open_interest_fetch.sqlite")),
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.open_interest.collector.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.open_interest.collector.TARGET_SYMBOLS",
        ["BTC/USDT", "ETH/USDT"],
    )
    payloads = {
        "BTC/USDT": {
            "timestamp": "2026-05-08T12:00:00Z",
            "openInterestAmount": 12.0,
            "openInterestValue": 1200.0,
        },
        "ETH/USDT": {
            "openInterestAmount": 8.0,
            "openInterestValue": 800.0,
        },
    }
    monkeypatch.setattr(
        collector,
        "_fetch_open_interest",
        lambda exchange_name, symbol: payloads[symbol],
    )

    snapshots = collector.fetch_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].symbol == "BTC/USDT"
    assert snapshots[0].timestamp.tzinfo is None
    assert snapshots[0].timestamp.isoformat() == "2026-05-08T12:00:00"


def test_long_short_ratio_fetch_snapshots_skips_bad_timestamp_and_normalizes_aware_time(
    monkeypatch,
    tmp_path,
):
    collector = LongShortRatioCollector(DBManager(str(tmp_path / "positioning_fetch.sqlite")))
    monkeypatch.setattr(
        collector.client,
        "fetch_items",
        lambda url, params=None: [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "timestamp": "2026-05-08T12:00:00Z",
                "long_short_ratio": 1.2,
            },
            {
                "symbol": "ETH/USDT",
                "exchange": "okx",
                "timestamp": "bad-timestamp",
                "long_short_ratio": 0.9,
            },
        ],
    )

    snapshots = collector.fetch_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].exchange == "binance"
    assert snapshots[0].timestamp.tzinfo is None
    assert snapshots[0].timestamp.isoformat() == "2026-05-08T12:00:00"


def test_liquidations_fetch_bars_skips_bad_open_time_and_normalizes_aware_time(
    monkeypatch,
    tmp_path,
):
    collector = LiquidationsCollector(DBManager(str(tmp_path / "liquidations_fetch.sqlite")))
    monkeypatch.setattr(
        collector.client,
        "fetch_items",
        lambda url, params=None: [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "open_time": "2026-05-08T12:00:00Z",
                "total_liquidation_notional": 150000.0,
            },
            {
                "symbol": "ETH/USDT",
                "exchange": "okx",
                "open_time": None,
                "total_liquidation_notional": 80000.0,
            },
        ],
    )

    bars = collector.fetch_bars()

    assert len(bars) == 1
    assert bars[0].exchange == "binance"
    assert bars[0].open_time.tzinfo is None
    assert bars[0].open_time.isoformat() == "2026-05-08T12:00:00"


def test_liquidations_fetch_bars_preserves_missing_metrics_as_none(
    monkeypatch,
    tmp_path,
):
    collector = LiquidationsCollector(DBManager(str(tmp_path / "liquidations_none.sqlite")))
    monkeypatch.setattr(
        collector.client,
        "fetch_items",
        lambda url, params=None: [
            {
                "symbol": "BTC/USDT",
                "exchange": "binance",
                "open_time": "2026-05-08T12:00:00Z",
                "long_liquidation_notional": None,
                "short_liquidation_notional": None,
                "total_liquidation_notional": None,
                "max_single_liquidation_notional": None,
            }
        ],
    )

    bars = collector.fetch_bars()

    assert len(bars) == 1
    assert bars[0].long_liquidation_notional is None
    assert bars[0].short_liquidation_notional is None
    assert bars[0].total_liquidation_notional is None
    assert bars[0].max_single_liquidation_notional is None


def test_latest_context_tables_keep_newest_snapshot_when_older_data_arrives(tmp_path):
    db = DBManager(str(tmp_path / "latest_context.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    funding_collector = FundingRateCollector(StaticClientManager(None), db)
    orderbook_collector = OrderBookCollector(StaticClientManager(None), db)

    newer = datetime(2026, 5, 6, 12, 0, 5)
    older = datetime(2026, 5, 6, 11, 59, 55)

    ticker_collector.save_to_db([
        Ticker(
            symbol="BTC/USDT",
            exchange="binance",
            last_price=101.0,
            bid=100.9,
            ask=101.1,
            mid_price=101.0,
            spread=0.2,
            spread_bps=19.8,
            quote_volume_24h=10_000_000,
            change_24h=2.5,
            vwap_24h=100.2,
            timestamp=newer,
        )
    ])
    ticker_collector.save_to_db([
        Ticker(
            symbol="BTC/USDT",
            exchange="binance",
            last_price=99.0,
            bid=98.9,
            ask=99.1,
            mid_price=99.0,
            spread=0.2,
            spread_bps=20.2,
            quote_volume_24h=8_000_000,
            change_24h=-1.0,
            vwap_24h=99.5,
            timestamp=older,
        )
    ])

    funding_collector.save_to_db([
        FundingRate(
            symbol="BTC/USDT",
            exchange="binance",
            funding_rate=0.0015,
            mark_price=101.0,
            index_price=100.8,
            timestamp=newer,
        )
    ])
    funding_collector.save_to_db([
        FundingRate(
            symbol="BTC/USDT",
            exchange="binance",
            funding_rate=0.0005,
            mark_price=99.0,
            index_price=98.8,
            timestamp=older,
        )
    ])

    orderbook_collector.save_to_db([
        OrderBook(
            symbol="BTC/USDT",
            exchange="binance",
            snapshot_depth=20,
            bids=[OrderBookLevel(price=100.9, amount=2.0)],
            asks=[OrderBookLevel(price=101.1, amount=2.5)],
            best_bid=100.9,
            best_ask=101.1,
            mid_price=101.0,
            spread=0.2,
            spread_bps=19.8,
            bid_depth_notional=40_000,
            ask_depth_notional=42_000,
            depth_imbalance=-0.02439,
            timestamp=newer,
        )
    ])
    orderbook_collector.save_to_db([
        OrderBook(
            symbol="BTC/USDT",
            exchange="binance",
            snapshot_depth=20,
            bids=[OrderBookLevel(price=98.9, amount=2.0)],
            asks=[OrderBookLevel(price=99.1, amount=2.5)],
            best_bid=98.9,
            best_ask=99.1,
            mid_price=99.0,
            spread=0.2,
            spread_bps=20.2,
            bid_depth_notional=38_000,
            ask_depth_notional=39_000,
            depth_imbalance=-0.01299,
            timestamp=older,
        )
    ])

    latest_ticker = db.fetch_one(
        "SELECT last_price, timestamp FROM latest_tickers WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )
    latest_funding = db.fetch_one(
        "SELECT funding_rate, timestamp FROM latest_funding_rates WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )
    latest_orderbook = db.fetch_one(
        "SELECT mid_price, timestamp FROM latest_orderbook_snapshots WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )

    assert latest_ticker["last_price"] == 101.0
    assert latest_ticker["timestamp"] == newer.isoformat()
    assert latest_funding["funding_rate"] == 0.0015
    assert latest_funding["timestamp"] == newer.isoformat()
    assert latest_orderbook["mid_price"] == 101.0
    assert latest_orderbook["timestamp"] == newer.isoformat()
    assert db.fetch_one("SELECT COUNT(*) AS count FROM tickers")["count"] == 2
    assert db.fetch_one("SELECT COUNT(*) AS count FROM funding_rates")["count"] == 2
    assert db.fetch_one("SELECT COUNT(*) AS count FROM orderbook_snapshots")["count"] == 2

    db.close()


def test_init_tables_backfills_latest_context_tables_from_history(tmp_path):
    db = DBManager(str(tmp_path / "latest_sync.sqlite"))
    db.init_tables()

    older = datetime(2026, 5, 6, 11, 59, 0)
    newer = datetime(2026, 5, 6, 12, 1, 0)

    db.execute_many(
        """
        INSERT INTO tickers (
            symbol, exchange, last_price, open_24h, bid, bid_volume,
            ask, ask_volume, previous_close, high_24h, low_24h,
            vwap_24h, volume_24h, quote_volume_24h,
            change_abs_24h, change_24h, mid_price, spread, spread_bps, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 99.0, None, 98.9, None, 99.1, None, None, None, None, None, None, None, None, None, 99.0, 0.2, 20.2, older.isoformat()),
            ("BTC/USDT", "binance", 102.0, None, 101.9, None, 102.1, None, None, None, None, None, None, None, None, None, 102.0, 0.2, 19.6, newer.isoformat()),
        ],
    )
    db.execute_many(
        """
        INSERT INTO funding_rates (
            symbol, exchange, funding_rate, mark_price,
            index_price, next_funding_time, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 0.0008, 99.0, 98.7, None, older.isoformat()),
            ("BTC/USDT", "binance", 0.0018, 102.0, 101.8, None, newer.isoformat()),
        ],
    )
    db.execute_many(
        """
        INSERT INTO orderbook_snapshots (
            symbol, exchange, snapshot_depth, best_bid, best_ask,
            mid_price, spread, spread_bps, bid_depth_notional,
            ask_depth_notional, depth_imbalance, bids_json, asks_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("BTC/USDT", "binance", 20, 98.9, 99.1, 99.0, 0.2, 20.2, 38_000, 39_000, -0.01299, "[]", "[]", older.isoformat()),
            ("BTC/USDT", "binance", 20, 101.9, 102.1, 102.0, 0.2, 19.6, 43_000, 44_000, -0.01149, "[]", "[]", newer.isoformat()),
        ],
    )
    db.commit()

    db.init_tables()

    latest_ticker = db.fetch_one(
        "SELECT last_price, timestamp FROM latest_tickers WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )
    latest_funding = db.fetch_one(
        "SELECT funding_rate, timestamp FROM latest_funding_rates WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )
    latest_orderbook = db.fetch_one(
        "SELECT mid_price, timestamp FROM latest_orderbook_snapshots WHERE symbol = ? AND exchange = ?",
        ("BTC/USDT", "binance"),
    )

    assert latest_ticker["last_price"] == 102.0
    assert latest_ticker["timestamp"] == newer.isoformat()
    assert latest_funding["funding_rate"] == 0.0018
    assert latest_funding["timestamp"] == newer.isoformat()
    assert latest_orderbook["mid_price"] == 102.0
    assert latest_orderbook["timestamp"] == newer.isoformat()

    db.close()


def test_latest_context_bundle_flags_spot_only_trade_flow(tmp_path):
    db = DBManager(str(tmp_path / "trade_flow_scope.sqlite"))
    db.init_tables()
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    trade_collector = TradesCollector(StaticClientManager(None), db)
    service = ExchangeDataService(db=db)

    now = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=101.0,
                bid=100.9,
                ask=101.1,
                mid_price=101.0,
                spread=0.2,
                spread_bps=19.8,
                quote_volume_24h=10_000_000,
                change_24h=2.5,
                vwap_24h=100.2,
                timestamp=now,
            )
        ]
    )
    trade_collector.save_to_db(
        [
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="spot",
                interval="1m",
                open_time=now,
                trade_count=10,
                buy_trade_count=6,
                sell_trade_count=4,
                buy_notional=60000.0,
                sell_notional=40000.0,
                aggressive_buy_notional=60000.0,
                aggressive_sell_notional=40000.0,
                net_taker_notional=20000.0,
                cvd=20000.0,
                avg_trade_notional=10000.0,
                largest_trade_notional=18000.0,
            )
        ]
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]

    assert bundle["configured_universe_summary"] == {
        "scope_kind": "filtered",
        "tracked_symbols": ["BTC/USDT"],
        "tracked_exchanges": ["binance", "okx", "bybit"],
        "asset_count": 1,
        "exchange_count": 3,
        "minimum_asset_count_for_market_breadth": 6,
        "minimum_exchange_count_for_market_breadth": 4,
        "breadth_status": "filtered",
        "is_market_breadth_sufficient": None,
    }
    assert symbol_entry["trade_flow_scope"] == "spot_only"
    assert "trade_flow_spot_only" in symbol_entry["data_quality_flags"]
    assert symbol_entry["trade_flow"] == symbol_entry["trade_flow_spot"]
    assert symbol_entry["trade_flow_spot"] == []
    assert symbol_entry["trade_flow_derivatives"] == []
    assert symbol_entry["row_count"] == 0
    assert symbol_entry["raw_row_count"] == 2
    assert symbol_entry["raw_source_counts"]["ticker"] == 1
    assert symbol_entry["raw_source_counts"]["trade_flow"] == 1
    assert "trade_flow" in symbol_entry["ai_excluded_source_names"]
    assert any(
        "当前只覆盖现货成交流" in note
        for note in symbol_entry["quality_notes"]
    )

    service.close()


def test_latest_context_bundle_prefers_derivatives_trade_flow_when_available(tmp_path):
    db = DBManager(str(tmp_path / "trade_flow_mixed_scope.sqlite"))
    db.init_tables()
    trade_collector = TradesCollector(StaticClientManager(None), db)
    service = ExchangeDataService(db=db)

    now = datetime(2026, 5, 8, 12, 0, 0)
    trade_collector.save_to_db(
        [
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="spot",
                interval="1m",
                open_time=now,
                trade_count=10,
                buy_trade_count=6,
                sell_trade_count=4,
                buy_notional=60000.0,
                sell_notional=40000.0,
                aggressive_buy_notional=60000.0,
                aggressive_sell_notional=40000.0,
                net_taker_notional=20000.0,
                cvd=20000.0,
                avg_trade_notional=10000.0,
                largest_trade_notional=18000.0,
            ),
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval="1m",
                open_time=now,
                trade_count=8,
                buy_trade_count=3,
                sell_trade_count=5,
                buy_notional=30000.0,
                sell_notional=70000.0,
                aggressive_buy_notional=30000.0,
                aggressive_sell_notional=70000.0,
                net_taker_notional=-40000.0,
                cvd=-40000.0,
                avg_trade_notional=12500.0,
                largest_trade_notional=25000.0,
            ),
        ]
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]

    assert symbol_entry["trade_flow_scope"] == "mixed"
    assert symbol_entry["trade_flow"] == []
    assert symbol_entry["trade_flow_spot"] == []
    assert symbol_entry["trade_flow_derivatives"] == []
    assert symbol_entry["row_count"] == 0
    assert symbol_entry["raw_row_count"] == 2
    assert symbol_entry["raw_source_counts"]["trade_flow"] == 2
    assert "trade_flow" in symbol_entry["ai_excluded_source_names"]
    assert "trade_flow_spot_only" not in symbol_entry["data_quality_flags"]

    coverage = service.load_source_coverage(source_names=["trade_flow"])
    assert coverage["sources"][0]["semantic_scope"] == "mixed"
    assert coverage["sources"][0]["latest_market_type_count"] == 2
    assert coverage["sources"][0]["latest_derivatives_pair_count"] == 1

    service.close()


def test_exchange_source_ready_for_ai_requires_full_non_stale_coverage(tmp_path, monkeypatch):
    db = DBManager(str(tmp_path / "exchange_ready_for_ai.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_SYMBOLS",
        ["BTC/USDT"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=10_000_000,
                timestamp=now,
            )
        ]
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="ticker",
        job_name="ticker_once",
        status="success",
        item_count=1,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )

    coverage = service.load_source_coverage(source_names=["ticker"])
    source = coverage["sources"][0]

    assert coverage["ready_source_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 1
    assert coverage["not_ready_for_ai_source_count"] == 0
    assert source["health_status"] == "ready"
    assert source["is_ready_for_ai"] is True
    assert source["latest_non_stale_coverage_ratio"] == 1.0
    assert source["data_quality_flags"] == []
    service.close()


def test_latest_context_bundle_exposes_exchange_quality_diagnostics(tmp_path, monkeypatch):
    db = DBManager(str(tmp_path / "exchange_bundle_quality.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    orderbook_collector = OrderBookCollector(StaticClientManager(None), db)
    funding_collector = FundingRateCollector(StaticClientManager(None), db)
    trade_collector = TradesCollector(StaticClientManager(None), db)
    open_interest_collector = OpenInterestCollector(StaticClientManager(None), db)
    basis_collector = BasisCollector(db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "liquidation_url": "https://real-source.example/liquidations",
            "long_short_ratio_url": "https://real-source.example/positioning",
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_time = now - timedelta(minutes=20)

    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=100.2,
                ask=100.1,
                mid_price=100.15,
                spread=-0.1,
                spread_bps=-9.98,
                quote_volume_24h=20_000_000,
                change_24h=1.2,
                vwap_24h=99.8,
                timestamp=now,
            ),
            Ticker(
                symbol="BTC/USDT",
                exchange="okx",
                last_price=101.0,
                bid=100.9,
                ask=101.1,
                mid_price=101.0,
                spread=0.2,
                spread_bps=19.8,
                quote_volume_24h=18_000_000,
                change_24h=1.1,
                vwap_24h=100.0,
                timestamp=now,
            ),
        ]
    )
    orderbook_collector.save_to_db(
        [
            OrderBook(
                symbol="BTC/USDT",
                exchange="binance",
                snapshot_depth=20,
                bids=[OrderBookLevel(price=100.2, amount=1.0)],
                asks=[OrderBookLevel(price=100.1, amount=1.2)],
                best_bid=100.2,
                best_ask=100.1,
                mid_price=100.15,
                spread=-0.1,
                spread_bps=-9.98,
                bid_depth_notional=None,
                ask_depth_notional=120000.0,
                depth_imbalance=None,
                timestamp=stale_time,
            )
        ]
    )
    funding_collector.save_to_db(
        [
            FundingRate(
                symbol="BTC/USDT",
                exchange="binance",
                funding_rate=0.001,
                mark_price=None,
                index_price=99.8,
                timestamp=now,
            ),
            FundingRate(
                symbol="BTC/USDT",
                exchange="okx",
                funding_rate=0.0015,
                mark_price=102.5,
                index_price=101.3,
                timestamp=now,
            ),
        ]
    )
    trade_collector.save_to_db(
        [
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="spot",
                interval="1m",
                open_time=now,
                trade_count=10,
                buy_trade_count=6,
                sell_trade_count=4,
                buy_notional=50000.0,
                sell_notional=30000.0,
                aggressive_buy_notional=50000.0,
                aggressive_sell_notional=30000.0,
                net_taker_notional=20000.0,
                cvd=20000.0,
                avg_trade_notional=8000.0,
                largest_trade_notional=15000.0,
            )
        ]
    )
    open_interest_collector.save_to_db(
        [
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval="5m",
                timestamp=stale_time,
                open_interest_contracts=1200.0,
                open_interest_usd=1200000.0,
                raw_payload_json='{"source":"real"}',
            )
        ]
    )
    basis_collector.save_to_db(
        [
            BasisSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval="5m",
                timestamp=now,
                spot_price=None,
                mark_price=100.8,
                index_price=100.1,
                basis_abs=None,
                basis_bps=None,
                annualized_basis_bps=None,
                funding_rate=0.001,
                raw_payload_json=json.dumps(
                    {
                        "source": "real",
                        "diagnostics": {
                            "ticker_timestamp_status": "missing",
                            "component_timestamp_gap_status": "missing_ticker_timestamp",
                            "component_timestamp_gap_seconds": None,
                            "annualization_status": "missing_next_funding_time",
                            "next_funding_time_status": "missing",
                        },
                    }
                ),
            ),
            BasisSnapshot(
                symbol="BTC/USDT",
                exchange="okx",
                market_type="linear_swap",
                interval="5m",
                timestamp=now,
                spot_price=101.0,
                mark_price=102.8,
                index_price=101.5,
                basis_abs=1.8,
                basis_bps=178.2,
                annualized_basis_bps=4000.0,
                funding_rate=0.0015,
                raw_payload_json=json.dumps(
                    {
                        "source": "real",
                        "diagnostics": {
                            "ticker_timestamp_status": "ok",
                            "ticker_timestamp": now.isoformat(),
                            "component_timestamp_gap_status": "wide",
                            "component_timestamp_gap_seconds": 240.0,
                            "annualization_status": "ok",
                            "next_funding_time_status": "ok",
                        },
                    }
                ),
            ),
        ]
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]
    coverage_summary = symbol_entry["coverage_summary"]
    diagnostics = symbol_entry["cross_exchange_diagnostics"]

    assert coverage_summary["expected_exchange_count"] == 3
    assert coverage_summary["configured_section_coverage_ratio"] < 1.0
    assert "orderbook" in coverage_summary["missing_sections"]
    assert "liquidations" in coverage_summary["missing_sections"]
    assert coverage_summary["section_statuses"]["spot"]["coverage_ratio"] == 0.6667
    assert coverage_summary["section_statuses"]["orderbook"]["exchange_count"] == 0
    assert coverage_summary["section_statuses"]["orderbook"]["stale_exchange_count"] == 0
    assert diagnostics["spot_last_price_range_bps"] is not None
    assert diagnostics["spot_last_price_range_bps"] > 90.0
    assert diagnostics["max_derivatives_core_time_gap_seconds"] == 1200.0
    assert "spot_cross_exchange_validation_weak" not in symbol_entry["data_quality_flags"]
    assert "cross_exchange_last_price_dispersion_high" in symbol_entry["data_quality_flags"]
    assert "missing_orderbook_for_some_spot_exchanges" in symbol_entry["data_quality_flags"]
    assert "missing_funding_for_some_spot_exchanges" not in symbol_entry["data_quality_flags"]
    assert "missing_trade_flow_derivatives_for_some_funding_exchanges" in symbol_entry["data_quality_flags"]
    assert "missing_open_interest_for_some_funding_exchanges" in symbol_entry["data_quality_flags"]
    assert "missing_basis_for_some_funding_exchanges" in symbol_entry["data_quality_flags"]
    assert "basis_missing_spot_price" in symbol_entry["data_quality_flags"]
    assert "basis_missing_ticker_timestamp" in symbol_entry["data_quality_flags"]
    assert "basis_component_time_gap_wide" in symbol_entry["data_quality_flags"]
    assert "basis_annualization_unavailable_present" in symbol_entry["data_quality_flags"]
    assert "derivatives_core_time_gap_wide" in symbol_entry["data_quality_flags"]
    assert "funding_missing_mark_or_index_price" in symbol_entry["data_quality_flags"]
    assert "ticker_crossed_market_present" in symbol_entry["data_quality_flags"]
    assert "orderbook_crossed_book_present" in symbol_entry["data_quality_flags"]
    assert "orderbook_missing_depth_notional" in symbol_entry["data_quality_flags"]
    assert "orderbook" in symbol_entry["ai_excluded_source_names"]
    assert symbol_entry["raw_source_counts"]["orderbook"] == 1
    assert symbol_entry["source_counts"].get("orderbook") is None
    assert len(symbol_entry["basis"]) == 0
    assert len(symbol_entry["raw_basis"]) == 2
    assert symbol_entry["source_counts"].get("basis") is None
    assert symbol_entry["raw_source_counts"]["basis"] == 2
    assert symbol_entry["basis_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["basis_quality_summary"]["raw_row_count"] == 2
    assert symbol_entry["basis_quality_summary"]["visible_row_count"] == 0
    assert symbol_entry["basis_quality_summary"]["missing_ticker_timestamp_count"] == 1
    assert symbol_entry["basis_quality_summary"]["wide_component_gap_count"] == 1
    assert symbol_entry["basis_quality_summary"]["annualization_unavailable_count"] == 1
    assert symbol_entry["derivatives_core_alignment"]["status"] == "wide"
    assert symbol_entry["derivatives_core_alignment"]["wide_exchange_count"] == 1
    assert symbol_entry["derivatives_core_alignment"]["wide_exchange_names"] == ["binance"]
    assert symbol_entry["derivatives_core_alignment"]["partial_exchange_names"] == ["okx"]
    assert bundle["basis_quality_summary"]["raw_row_count"] == 2
    assert bundle["basis_quality_summary"]["visible_row_count"] == 0
    assert any("orderbook 缺少部分已有 spot 行情的交易所快照" in note for note in symbol_entry["quality_notes"])
    assert any("跨交易所离散度达到" in note for note in symbol_entry["quality_notes"])
    assert any("basis 中存在缺少或无法解析 ticker 时间戳" in note for note in symbol_entry["quality_notes"])
    assert any("basis 中存在现货与 funding 组件时间差过大" in note for note in symbol_entry["quality_notes"])
    assert any("basis 中存在无法可靠年化" in note for note in symbol_entry["quality_notes"])
    assert any("funding / open_interest / basis 在部分交易所不处于同一时间切片" in note for note in symbol_entry["quality_notes"])

    service.close()


def test_latest_context_bundle_keeps_incomplete_derivatives_rows_only_in_raw_views(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_raw_only_derivatives.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    open_interest_collector = OpenInterestCollector(StaticClientManager(None), db)
    positioning_collector = LongShortRatioCollector(db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "long_short_ratio_url": "https://real-source.example/positioning",
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    open_interest_collector.save_to_db(
        [
            OpenInterestSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                interval=EXCHANGE_DERIVATIVES_CONFIG["open_interest_interval"],
                timestamp=now,
                open_interest_contracts=None,
                open_interest_usd=None,
                raw_payload_json='{"source":"real"}',
            )
        ]
    )
    positioning_collector.save_to_db(
        [
            PositioningSnapshot(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="linear_swap",
                ratio_scope="accounts",
                interval=EXCHANGE_DERIVATIVES_CONFIG["positioning_interval"],
                timestamp=now,
                long_ratio=0.61,
                short_ratio=None,
                long_short_ratio=None,
                top_trader_long_ratio=None,
                top_trader_short_ratio=None,
                raw_payload_json='{"source":"real"}',
            )
        ]
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]
    source_health = {
        row["source_name"]: row
        for row in bundle["source_health"]
    }

    assert symbol_entry["source_counts"].get("open_interest") is None
    assert symbol_entry["raw_source_counts"]["open_interest"] == 1
    assert symbol_entry["open_interest"] == []
    assert len(symbol_entry["raw_open_interest"]) == 1
    assert symbol_entry["open_interest_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["open_interest_quality_summary"]["missing_value_count"] == 1
    assert "open_interest_missing_value" in symbol_entry["data_quality_flags"]

    assert symbol_entry["source_counts"].get("long_short_ratio") is None
    assert symbol_entry["raw_source_counts"]["long_short_ratio"] == 1
    assert symbol_entry["positioning"] == []
    assert len(symbol_entry["raw_positioning"]) == 1
    assert symbol_entry["positioning_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["positioning_quality_summary"]["incomplete_metric_count"] == 1
    assert symbol_entry["positioning_quality_summary"]["incomplete_accounts_metric_count"] == 1
    assert "positioning_incomplete_metrics_present" in symbol_entry["data_quality_flags"]

    assert bundle["open_interest_quality_summary"]["raw_row_count"] == 1
    assert bundle["open_interest_quality_summary"]["visible_row_count"] == 0
    assert bundle["positioning_quality_summary"]["raw_row_count"] == 1
    assert bundle["positioning_quality_summary"]["visible_row_count"] == 0
    assert "open_interest_missing_value" in source_health["open_interest"]["data_quality_flags"]
    assert (
        "positioning_incomplete_metrics_present"
        in source_health["long_short_ratio"]["data_quality_flags"]
    )
    assert any("raw_open_interest" in note for note in symbol_entry["quality_notes"])
    assert any("raw_positioning" in note for note in symbol_entry["quality_notes"])

    service.close()


def test_latest_context_bundle_keeps_incomplete_liquidations_only_in_raw_views(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_raw_only_liquidations.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "liquidation_url": "https://real-source.example/liquidations",
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute_many(
        """
        INSERT INTO latest_liquidation_bars (
            symbol, exchange, market_type, interval, open_time,
            long_liquidation_notional, short_liquidation_notional,
            long_liquidation_count, short_liquidation_count,
            total_liquidation_notional, max_single_liquidation_notional,
            collected_at, raw_payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                "linear_swap",
                EXCHANGE_DERIVATIVES_CONFIG["liquidation_bar_interval"],
                now.isoformat(),
                None,
                None,
                3,
                None,
                None,
                None,
                now.isoformat(),
                '{"source":"real"}',
            )
        ],
    )
    db.commit()

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]
    source_health = {
        row["source_name"]: row
        for row in bundle["source_health"]
    }

    assert symbol_entry["source_counts"].get("liquidations") is None
    assert symbol_entry["raw_source_counts"]["liquidations"] == 1
    assert symbol_entry["liquidations"] == []
    assert len(symbol_entry["raw_liquidations"]) == 1
    assert symbol_entry["liquidations_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["liquidations_quality_summary"]["incomplete_metric_count"] == 1
    assert "liquidations_incomplete_metrics_present" in symbol_entry["data_quality_flags"]
    assert bundle["liquidations_quality_summary"]["raw_row_count"] == 1
    assert bundle["liquidations_quality_summary"]["visible_row_count"] == 0
    assert (
        "liquidations_incomplete_metrics_present"
        in source_health["liquidations"]["data_quality_flags"]
    )
    assert any("raw_liquidations" in note for note in symbol_entry["quality_notes"])

    service.close()


def test_latest_context_bundle_keeps_real_zero_liquidations_visible(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_zero_liquidations.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "liquidation_url": "https://real-source.example/liquidations",
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.execute_many(
        """
        INSERT INTO latest_liquidation_bars (
            symbol, exchange, market_type, interval, open_time,
            long_liquidation_notional, short_liquidation_notional,
            long_liquidation_count, short_liquidation_count,
            total_liquidation_notional, max_single_liquidation_notional,
            collected_at, raw_payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "BTC/USDT",
                "binance",
                "linear_swap",
                EXCHANGE_DERIVATIVES_CONFIG["liquidation_bar_interval"],
                now.isoformat(),
                0.0,
                0.0,
                0,
                0,
                0.0,
                0.0,
                now.isoformat(),
                '{"source":"real"}',
            )
        ],
    )
    db.commit()

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]

    assert symbol_entry["source_counts"]["liquidations"] == 1
    assert symbol_entry["raw_source_counts"]["liquidations"] == 1
    assert len(symbol_entry["liquidations"]) == 1
    assert symbol_entry["liquidations_quality_summary"]["status"] == "ready"
    assert symbol_entry["liquidations"][0]["total_liquidation_notional"] == 0.0
    assert "liquidations_incomplete_metrics_present" not in symbol_entry["data_quality_flags"]
    assert "liquidations_missing_metrics" not in symbol_entry["data_quality_flags"]

    service.close()


def test_latest_context_bundle_keeps_weak_spot_and_orderbook_rows_only_in_raw_views(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_raw_only_spot_orderbook.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    orderbook_collector = OrderBookCollector(StaticClientManager(None), db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=None,
                bid=None,
                ask=None,
                timestamp=now,
            )
        ]
    )
    orderbook_collector.save_to_db(
        [
            OrderBook(
                symbol="BTC/USDT",
                exchange="binance",
                snapshot_depth=20,
                bids=[],
                asks=[],
                best_bid=None,
                best_ask=None,
                bid_depth_notional=0.0,
                ask_depth_notional=0.0,
                timestamp=now,
            )
        ]
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]
    source_health = {
        row["source_name"]: row
        for row in bundle["source_health"]
    }

    assert symbol_entry["spot"] == []
    assert len(symbol_entry["raw_spot"]) == 1
    assert symbol_entry["spot_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["spot_quality_summary"]["missing_core_price_count"] == 1
    assert symbol_entry["source_counts"].get("ticker") is None
    assert symbol_entry["raw_source_counts"]["ticker"] == 1
    assert "spot_missing_core_price" in symbol_entry["data_quality_flags"]

    assert symbol_entry["orderbook"] == []
    assert len(symbol_entry["raw_orderbook"]) == 1
    assert symbol_entry["orderbook_quality_summary"]["status"] == "raw_only"
    assert symbol_entry["orderbook_quality_summary"]["missing_top_of_book_count"] == 1
    assert symbol_entry["source_counts"].get("orderbook") is None
    assert symbol_entry["raw_source_counts"]["orderbook"] == 1
    assert "orderbook_missing_top_of_book" in symbol_entry["data_quality_flags"]

    assert bundle["spot_quality_summary"]["raw_row_count"] == 1
    assert bundle["spot_quality_summary"]["visible_row_count"] == 0
    assert bundle["orderbook_quality_summary"]["raw_row_count"] == 1
    assert bundle["orderbook_quality_summary"]["visible_row_count"] == 0

    assert source_health["ticker"]["latest_pair_count"] == 0
    assert source_health["ticker"]["is_ready_for_ai"] is False
    assert "spot_missing_core_price" in source_health["ticker"]["data_quality_flags"]
    assert source_health["orderbook"]["latest_pair_count"] == 0
    assert source_health["orderbook"]["is_ready_for_ai"] is False
    assert (
        "orderbook_missing_top_of_book"
        in source_health["orderbook"]["data_quality_flags"]
    )
    assert any("raw_spot" in note for note in symbol_entry["quality_notes"])
    assert any("raw_orderbook" in note for note in symbol_entry["quality_notes"])

    service.close()


def test_latest_context_bundle_keeps_partial_but_usable_spot_and_orderbook_visible(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_partial_spot_orderbook.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    orderbook_collector = OrderBookCollector(StaticClientManager(None), db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=None,
                ask=None,
                timestamp=now,
            )
        ]
    )
    orderbook_collector.save_to_db(
        [
            OrderBook(
                symbol="BTC/USDT",
                exchange="binance",
                snapshot_depth=20,
                bids=[OrderBookLevel(price=99.9, amount=1.0)],
                asks=[OrderBookLevel(price=100.1, amount=1.2)],
                best_bid=99.9,
                best_ask=100.1,
                bid_depth_notional=0.0,
                ask_depth_notional=0.0,
                timestamp=now,
            )
        ]
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="ticker",
        job_name="ticker_once",
        status="success",
        item_count=1,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="orderbook",
        job_name="orderbook_once",
        status="success",
        item_count=1,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )

    bundle = service.load_latest_market_context_bundle(symbols=["BTC/USDT"])
    symbol_entry = bundle["symbols"][0]
    source_health = {
        row["source_name"]: row
        for row in bundle["source_health"]
    }

    assert len(symbol_entry["spot"]) == 1
    assert len(symbol_entry["raw_spot"]) == 1
    assert symbol_entry["spot_quality_summary"]["status"] == "ready"
    assert symbol_entry["spot_quality_summary"]["last_price_only_count"] == 1
    assert "spot_bid_ask_missing_present" in symbol_entry["data_quality_flags"]
    assert symbol_entry["source_counts"]["ticker"] == 1

    assert len(symbol_entry["orderbook"]) == 1
    assert len(symbol_entry["raw_orderbook"]) == 1
    assert symbol_entry["orderbook_quality_summary"]["status"] == "ready"
    assert symbol_entry["orderbook_quality_summary"]["top_of_book_only_count"] == 1
    assert symbol_entry["source_counts"]["orderbook"] == 1

    assert source_health["ticker"]["latest_pair_count"] == 1
    assert source_health["ticker"]["is_ready_for_ai"] is True
    assert "spot_bid_ask_missing_present" in source_health["ticker"]["data_quality_flags"]
    assert source_health["orderbook"]["latest_pair_count"] == 1
    assert source_health["orderbook"]["is_ready_for_ai"] is True

    service.close()


def test_liquidations_repair_restores_unknown_metrics_from_raw_payload(
    tmp_path,
    monkeypatch,
):
    db = DBManager(str(tmp_path / "exchange_liquidations_repair.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.TARGET_EXCHANGES",
        ["binance"],
    )
    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "liquidation_url": "https://real-source.example/liquidations",
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    interval = EXCHANGE_DERIVATIVES_CONFIG["liquidation_bar_interval"]
    incomplete_raw_payload = json.dumps(
        {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "long_liquidation_count": 3,
        },
        ensure_ascii=False,
    )
    zero_raw_payload = json.dumps(
        {
            "symbol": "ETH/USDT",
            "exchange": "binance",
            "long_liquidation_notional": 0.0,
            "short_liquidation_notional": 0.0,
            "long_liquidation_count": 0,
            "short_liquidation_count": 0,
            "total_liquidation_notional": 0.0,
            "max_single_liquidation_notional": 0.0,
        },
        ensure_ascii=False,
    )
    polluted_row = (
        "BTC/USDT",
        "binance",
        "linear_swap",
        interval,
        now.isoformat(),
        0.0,
        0.0,
        3,
        0,
        0.0,
        0.0,
        now.isoformat(),
        incomplete_raw_payload,
    )
    real_zero_row = (
        "ETH/USDT",
        "binance",
        "linear_swap",
        interval,
        now.isoformat(),
        0.0,
        0.0,
        0,
        0,
        0.0,
        0.0,
        now.isoformat(),
        zero_raw_payload,
    )
    db.execute_many(
        """
        INSERT INTO latest_liquidation_bars (
            symbol, exchange, market_type, interval, open_time,
            long_liquidation_notional, short_liquidation_notional,
            long_liquidation_count, short_liquidation_count,
            total_liquidation_notional, max_single_liquidation_notional,
            collected_at, raw_payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [polluted_row, real_zero_row],
    )
    db.execute_many(
        """
        INSERT INTO liquidation_bars (
            symbol, exchange, market_type, interval, open_time,
            long_liquidation_notional, short_liquidation_notional,
            long_liquidation_count, short_liquidation_count,
            total_liquidation_notional, max_single_liquidation_notional,
            collected_at, raw_payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [polluted_row],
    )
    db.commit()

    before_bundle = service.load_latest_market_context_bundle(
        symbols=["BTC/USDT", "ETH/USDT"]
    )
    before_symbols = {
        row["symbol"]: row
        for row in before_bundle["symbols"]
    }
    assert len(before_symbols["BTC/USDT"]["liquidations"]) == 1

    repair_summary = service.repair_liquidation_semantics_from_raw_payload()

    assert repair_summary == {
        "history_rows_repaired": 1,
        "latest_rows_repaired": 1,
    }

    repaired_latest_row = db.fetch_one(
        """
        SELECT
            long_liquidation_notional,
            short_liquidation_notional,
            long_liquidation_count,
            short_liquidation_count,
            total_liquidation_notional,
            max_single_liquidation_notional
        FROM latest_liquidation_bars
        WHERE symbol = ? AND exchange = ?
        """,
        ("BTC/USDT", "binance"),
    )
    assert repaired_latest_row["long_liquidation_notional"] is None
    assert repaired_latest_row["short_liquidation_notional"] is None
    assert repaired_latest_row["long_liquidation_count"] == 3
    assert repaired_latest_row["short_liquidation_count"] is None
    assert repaired_latest_row["total_liquidation_notional"] is None
    assert repaired_latest_row["max_single_liquidation_notional"] is None

    after_bundle = service.load_latest_market_context_bundle(
        symbols=["BTC/USDT", "ETH/USDT"]
    )
    after_symbols = {
        row["symbol"]: row
        for row in after_bundle["symbols"]
    }
    btc_entry = after_symbols["BTC/USDT"]
    eth_entry = after_symbols["ETH/USDT"]

    assert btc_entry["liquidations"] == []
    assert len(btc_entry["raw_liquidations"]) == 1
    assert btc_entry["liquidations_quality_summary"]["status"] == "raw_only"
    assert "liquidations_incomplete_metrics_present" in btc_entry["data_quality_flags"]

    assert len(eth_entry["liquidations"]) == 1
    assert eth_entry["liquidations"][0]["total_liquidation_notional"] == 0.0
    assert eth_entry["liquidations_quality_summary"]["status"] == "ready"

    service.close()


def test_exchange_source_coverage_reports_undercoverage_and_stale_pairs(tmp_path, monkeypatch):
    db = DBManager(str(tmp_path / "exchange_coverage_quality.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)
    trade_collector = TradesCollector(StaticClientManager(None), db)

    monkeypatch.setattr(
        "data_layer.exchange_data.service.EXCHANGE_DERIVATIVES_CONFIG",
        {
            **EXCHANGE_DERIVATIVES_CONFIG,
            "liquidation_url": None,
            "long_short_ratio_url": None,
        },
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_time = now - timedelta(seconds=45)

    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=15_000_000,
                timestamp=stale_time,
            ),
            Ticker(
                symbol="BTC/USDT",
                exchange="okx",
                last_price=100.3,
                bid=100.2,
                ask=100.4,
                mid_price=100.3,
                spread=0.2,
                spread_bps=19.94,
                quote_volume_24h=13_000_000,
                timestamp=now,
            ),
            Ticker(
                symbol="ETH/USDT",
                exchange="binance",
                last_price=2500.0,
                bid=2499.0,
                ask=2501.0,
                mid_price=2500.0,
                spread=2.0,
                spread_bps=8.0,
                quote_volume_24h=11_000_000,
                timestamp=now,
            ),
        ]
    )
    trade_collector.save_to_db(
        [
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="binance",
                market_type="spot",
                interval="1m",
                open_time=now,
                trade_count=10,
                buy_trade_count=6,
                sell_trade_count=4,
                buy_notional=50000.0,
                sell_notional=30000.0,
                aggressive_buy_notional=50000.0,
                aggressive_sell_notional=30000.0,
                net_taker_notional=20000.0,
                cvd=20000.0,
                avg_trade_notional=8000.0,
                largest_trade_notional=15000.0,
            ),
            TradeFlowBar(
                symbol="BTC/USDT",
                exchange="okx",
                market_type="linear_swap",
                interval="1m",
                open_time=now,
                trade_count=9,
                buy_trade_count=4,
                sell_trade_count=5,
                buy_notional=45000.0,
                sell_notional=55000.0,
                aggressive_buy_notional=45000.0,
                aggressive_sell_notional=55000.0,
                net_taker_notional=-10000.0,
                cvd=-10000.0,
                avg_trade_notional=10000.0,
                largest_trade_notional=20000.0,
            ),
        ]
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="ticker",
        job_name="ticker_once",
        status="success",
        item_count=3,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )
    service.db.record_collection_run(
        module_name="exchange_data",
        source_name="trade_flow",
        job_name="trade_flow_once",
        status="success",
        item_count=2,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
    )

    coverage = service.load_source_coverage(
        source_names=["ticker", "trade_flow", "liquidations"],
    )
    coverage_map = {
        item["source_name"]: item
        for item in coverage["sources"]
    }

    ticker_coverage = coverage_map["ticker"]
    assert ticker_coverage["is_ready_for_ai"] is False
    assert ticker_coverage["latest_coverage_ratio"] == 0.0556
    assert ticker_coverage["latest_missing_pair_count"] == 51
    assert ticker_coverage["latest_undercovered_symbol_count"] == 2
    assert ticker_coverage["latest_missing_symbol_count"] == 16
    assert ticker_coverage["latest_stale_pair_count"] == 1
    assert ticker_coverage["latest_non_stale_pair_count"] == 2
    assert ticker_coverage["latest_non_stale_coverage_ratio"] == 0.037
    assert "exchange_coverage_incomplete" in ticker_coverage["data_quality_flags"]
    assert "stale_pairs_present" in ticker_coverage["data_quality_flags"]
    assert ticker_coverage["coverage_gaps"]
    assert any("最新快照仍有目标 symbol 未覆盖全部目标交易所" in note for note in ticker_coverage["quality_notes"])

    trade_flow_coverage = coverage_map["trade_flow"]
    assert trade_flow_coverage["is_ready_for_ai"] is False
    assert trade_flow_coverage["semantic_scope"] == "mixed"
    assert trade_flow_coverage["latest_spot_pair_count"] == 1
    assert trade_flow_coverage["latest_derivatives_pair_count"] == 1
    assert trade_flow_coverage["latest_spot_coverage_ratio"] == 0.0185
    assert trade_flow_coverage["latest_derivatives_coverage_ratio"] == 0.0185
    assert trade_flow_coverage["latest_spot_missing_pair_count"] == 53
    assert trade_flow_coverage["latest_derivatives_missing_pair_count"] == 53
    assert trade_flow_coverage["latest_spot_undercovered_symbol_count"] == 1
    assert trade_flow_coverage["latest_derivatives_undercovered_symbol_count"] == 1
    assert "exchange_coverage_incomplete" in trade_flow_coverage["data_quality_flags"]
    assert "trade_flow_derivatives_coverage_incomplete" in trade_flow_coverage["data_quality_flags"]
    assert trade_flow_coverage["spot_coverage_gaps"]
    assert trade_flow_coverage["derivatives_coverage_gaps"]

    liquidations_coverage = coverage_map["liquidations"]
    assert liquidations_coverage["configuration_ready"] is False
    assert liquidations_coverage["health_status"] == "unconfigured"
    assert liquidations_coverage["is_ready_for_ai"] is False
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 3

    service.close()


def test_latest_market_context_bundle_flags_default_market_breadth_limits(tmp_path):
    db = DBManager(str(tmp_path / "exchange_breadth_bundle.sqlite"))
    db.init_tables()
    service = ExchangeDataService(db=db)
    ticker_collector = TickerCollector(StaticClientManager(None), db)

    now = datetime(2026, 5, 8, 12, 0, 0)
    ticker_collector.save_to_db(
        [
            Ticker(
                symbol="BTC/USDT",
                exchange="binance",
                last_price=100.0,
                bid=99.9,
                ask=100.1,
                mid_price=100.0,
                spread=0.2,
                spread_bps=20.0,
                quote_volume_24h=10_000_000,
                timestamp=now,
            )
        ]
    )

    bundle = service.load_latest_market_context_bundle()
    symbol_entry = {
        item["symbol"]: item
        for item in bundle["symbols"]
    }["BTC/USDT"]

    from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES
    assert bundle["configured_universe_summary"] == {
        "scope_kind": "default",
        "tracked_symbols": TARGET_SYMBOLS,
        "tracked_exchanges": TARGET_EXCHANGES,
        "asset_count": len(TARGET_SYMBOLS),
        "exchange_count": len(TARGET_EXCHANGES),
        "minimum_asset_count_for_market_breadth": 6,
        "minimum_exchange_count_for_market_breadth": 4,
        "breadth_status": "limited",
        "is_market_breadth_sufficient": False,
    }
    assert "exchange_configured_market_breadth_limited" in symbol_entry["data_quality_flags"]
    assert any(
        f"默认市场宇宙只覆盖 {len(TARGET_SYMBOLS)} 个资产、{len(TARGET_EXCHANGES)} 家交易所" in note
        for note in symbol_entry["quality_notes"]
    )

    service.close()


def test_technical_indicator_repository_limits_context_scan_to_incremental_window(tmp_path):
    db = DBManager(str(tmp_path / "technical_context.sqlite"))
    db.init_tables()

    rows = [
        ("BTC/USDT", "binance", 100.0, datetime(2026, 5, 6, 11, 55, 0)),
        ("BTC/USDT", "binance", 101.0, datetime(2026, 5, 6, 12, 5, 0)),
        ("BTC/USDT", "binance", 102.0, datetime(2026, 5, 6, 12, 10, 0)),
        ("BTC/USDT", "okx", 99.5, datetime(2026, 5, 6, 12, 6, 0)),
        ("BTC/USDT", "okx", 100.5, datetime(2026, 5, 6, 12, 11, 0)),
    ]
    db.execute_many(
        """
        INSERT INTO tickers (
            symbol, exchange, last_price, bid, ask, mid_price, spread, spread_bps, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                symbol,
                exchange,
                last_price,
                last_price - 0.1,
                last_price + 0.1,
                last_price,
                0.2,
                20.0,
                timestamp.isoformat(),
            )
            for symbol, exchange, last_price, timestamp in rows
        ],
    )
    db.commit()

    repository = TechnicalIndicatorRepository(db)
    frame = repository.fetch_ticker_snapshots(
        symbol="BTC/USDT",
        since_time=datetime(2026, 5, 6, 12, 7, 0),
    )

    assert frame.to_dict("records") == [
        {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "last_price": 101.0,
            "mid_price": 101.0,
            "spread_bps": 20.0,
            "quote_volume_24h": None,
            "change_24h": None,
            "vwap_24h": None,
            "timestamp": datetime(2026, 5, 6, 12, 5, 0).isoformat(),
        },
        {
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "last_price": 102.0,
            "mid_price": 102.0,
            "spread_bps": 20.0,
            "quote_volume_24h": None,
            "change_24h": None,
            "vwap_24h": None,
            "timestamp": datetime(2026, 5, 6, 12, 10, 0).isoformat(),
        },
        {
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "last_price": 99.5,
            "mid_price": 99.5,
            "spread_bps": 20.0,
            "quote_volume_24h": None,
            "change_24h": None,
            "vwap_24h": None,
            "timestamp": datetime(2026, 5, 6, 12, 6, 0).isoformat(),
        },
        {
            "symbol": "BTC/USDT",
            "exchange": "okx",
            "last_price": 100.5,
            "mid_price": 100.5,
            "spread_bps": 20.0,
            "quote_volume_24h": None,
            "change_24h": None,
            "vwap_24h": None,
            "timestamp": datetime(2026, 5, 6, 12, 11, 0).isoformat(),
        },
    ]

    db.close()
