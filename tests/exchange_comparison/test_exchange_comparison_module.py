import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from logic_layer.exchange_comparison.models import ExchangeComparisonConfig
from logic_layer.exchange_comparison.service import ExchangeComparisonService


def _insert_market_info(
    db: DBManager,
    symbol: str,
    exchange: str,
    taker_fee: float = 0.001,
    market_type: str = "spot",
):
    db.execute(
        """
        INSERT INTO market_info (
            symbol, exchange_symbol, base, quote, exchange, market_type,
            status, maker_fee, taker_fee, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            symbol.replace("/", ""),
            symbol.split("/")[0],
            symbol.split("/")[1],
            exchange,
            market_type,
            "active",
            taker_fee,
            taker_fee,
            datetime(2026, 5, 6, 12, 0, 0).isoformat(),
        ),
    )


def _insert_ticker(
    db: DBManager,
    symbol: str,
    exchange: str,
    last_price: float,
    bid: float,
    ask: float,
    quote_volume_24h: float,
    timestamp: datetime,
):
    mid_price = (bid + ask) / 2
    spread = ask - bid
    spread_bps = spread / mid_price * 10000
    db.execute(
        """
        INSERT INTO tickers (
            symbol, exchange, last_price, bid, ask, mid_price,
            spread, spread_bps, quote_volume_24h, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            exchange,
            last_price,
            bid,
            ask,
            mid_price,
            spread,
            spread_bps,
            quote_volume_24h,
            timestamp.isoformat(),
        ),
    )


def _insert_orderbook(
    db: DBManager,
    symbol: str,
    exchange: str,
    best_bid: float,
    best_ask: float,
    bid_depth_notional: float,
    ask_depth_notional: float,
    depth_imbalance: float,
    timestamp: datetime,
):
    mid_price = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    spread_bps = spread / mid_price * 10000
    db.execute(
        """
        INSERT INTO orderbook_snapshots (
            symbol, exchange, snapshot_depth, best_bid, best_ask, mid_price,
            spread, spread_bps, bid_depth_notional, ask_depth_notional,
            depth_imbalance, bids_json, asks_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            exchange,
            20,
            best_bid,
            best_ask,
            mid_price,
            spread,
            spread_bps,
            bid_depth_notional,
            ask_depth_notional,
            depth_imbalance,
            "[]",
            "[]",
            timestamp.isoformat(),
        ),
    )


def _insert_funding(
    db: DBManager,
    symbol: str,
    exchange: str,
    funding_rate: float,
    mark_price: float,
    index_price: float,
    timestamp: datetime,
):
    db.execute(
        """
        INSERT INTO funding_rates (
            symbol, exchange, funding_rate, mark_price, index_price, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            exchange,
            funding_rate,
            mark_price,
            index_price,
            timestamp.isoformat(),
        ),
    )


def _insert_indicator_context(
    db: DBManager,
    symbol: str,
    timeframe: str,
    open_time: datetime,
    close: float,
    rsi_14: float,
    macd_hist: float,
    atr_pct_14: float,
    volatility_20: float,
    adx_14: float,
    bb_width: float,
    price_zscore_20: float,
    volume_ratio_20: float,
    cross_exchange_last_price_range_bps: float,
    funding_basis_bps_mean: float,
    orderbook_total_depth_notional: float,
):
    db.execute(
        """
        INSERT INTO technical_indicators (
            symbol, timeframe, open_time, close, volume,
            rsi_14, macd_hist, atr_pct_14, volatility_20, adx_14,
            bb_width, price_zscore_20, volume_ratio_20,
            cross_exchange_last_price_range_bps,
            funding_basis_bps_mean, orderbook_total_depth_notional
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            timeframe,
            open_time.isoformat(),
            close,
            1000.0,
            rsi_14,
            macd_hist,
            atr_pct_14,
            volatility_20,
            adx_14,
            bb_width,
            price_zscore_20,
            volume_ratio_20,
            cross_exchange_last_price_range_bps,
            funding_basis_bps_mean,
            orderbook_total_depth_notional,
        ),
    )


def _build_service(tmp_path, config: ExchangeComparisonConfig) -> ExchangeComparisonService:
    service = ExchangeComparisonService(
        db=DBManager(str(tmp_path / "exchange_comparison.sqlite")),
        config=config,
    )
    service.init_storage()
    return service


def test_exchange_comparison_generates_actionable_snapshot_and_upserts(tmp_path):
    config = ExchangeComparisonConfig(
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        snapshot_lookback_seconds=1800,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        target_notional=1000.0,
        min_actionable_net_spread_bps=2.0,
        max_slippage_bps=25.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance")
    _insert_market_info(db, "BTC/USDT", "okx")
    _insert_ticker(db, "BTC/USDT", "binance", 101.1, 101.0, 101.2, 12_000_000, base_time)
    _insert_ticker(
        db,
        "BTC/USDT",
        "okx",
        99.9,
        99.8,
        100.0,
        10_000_000,
        base_time + timedelta(seconds=1),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "binance",
        101.0,
        101.2,
        50_000,
        45_000,
        0.05,
        base_time,
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "okx",
        99.8,
        100.0,
        60_000,
        58_000,
        0.03,
        base_time + timedelta(seconds=1),
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["exchange_a"] == "binance"
    assert row["exchange_b"] == "okx"
    assert row["best_buy_exchange"] == "okx"
    assert row["best_sell_exchange"] == "binance"
    assert row["signal_label"] == "tradable_spread"
    assert bool(row["is_actionable"]) is True
    assert row["opportunity_type"] == "sell_binance_buy_okx"
    assert row["net_cross_spread_max_bps"] > 60

    count = db.fetch_one(
        "SELECT COUNT(*) AS count FROM exchange_comparison_snapshots"
    )["count"]
    assert count == 1

    service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
    )
    count = db.fetch_one(
        "SELECT COUNT(*) AS count FROM exchange_comparison_snapshots"
    )["count"]
    assert count == 1
    service.close()


def test_exchange_comparison_marks_missing_orderbook_as_data_quality_warning(tmp_path):
    config = ExchangeComparisonConfig(
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        snapshot_lookback_seconds=1800,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance")
    _insert_market_info(db, "BTC/USDT", "okx")
    _insert_ticker(db, "BTC/USDT", "binance", 100.1, 100.0, 100.2, 8_000_000, base_time)
    _insert_ticker(
        db,
        "BTC/USDT",
        "okx",
        100.0,
        99.9,
        100.1,
        7_500_000,
        base_time + timedelta(seconds=1),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "binance",
        100.0,
        100.2,
        40_000,
        38_000,
        0.02,
        base_time - timedelta(seconds=30),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "okx",
        99.9,
        100.1,
        42_000,
        39_000,
        0.01,
        base_time + timedelta(seconds=1),
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["signal_label"] == "data_quality_warning"
    assert bool(row["is_actionable"]) is False
    assert "missing_orderbook_a" in row["data_quality_flag"]
    service.close()


def test_exchange_comparison_only_emits_canonical_exchange_pairs(tmp_path):
    config = ExchangeComparisonConfig(
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        snapshot_lookback_seconds=1800,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    exchanges = [
        ("binance", 100.0, 99.9, 100.1),
        ("bybit", 100.1, 100.0, 100.2),
        ("okx", 99.9, 99.8, 100.0),
    ]
    for index, (exchange, last_price, bid, ask) in enumerate(exchanges):
        tick_time = base_time + timedelta(seconds=index)
        _insert_market_info(db, "ETH/USDT", exchange)
        _insert_ticker(db, "ETH/USDT", exchange, last_price, bid, ask, 5_000_000, tick_time)
        _insert_orderbook(
            db,
            "ETH/USDT",
            exchange,
            bid,
            ask,
            55_000,
            57_000,
            0.01,
            tick_time,
        )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="ETH/USDT",
        as_of=base_time + timedelta(seconds=5),
    )

    assert len(frame) == 3
    pair_set = {
        (row.exchange_a, row.exchange_b)
        for row in frame.itertuples(index=False)
    }
    assert pair_set == {
        ("binance", "bybit"),
        ("binance", "okx"),
        ("bybit", "okx"),
    }
    assert all(left < right for left, right in pair_set)
    service.close()


def test_exchange_comparison_enriches_funding_and_indicator_context_for_ai(tmp_path):
    config = ExchangeComparisonConfig(
        market_type="swap",
        indicator_timeframe="1h",
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        funding_window_seconds=1800,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        max_funding_age_seconds=3600,
        max_indicator_age_seconds=7200,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance", market_type="swap")
    _insert_market_info(db, "BTC/USDT", "okx", market_type="swap")
    _insert_ticker(db, "BTC/USDT", "binance", 101.1, 101.0, 101.2, 12_000_000, base_time)
    _insert_ticker(
        db,
        "BTC/USDT",
        "okx",
        99.9,
        99.8,
        100.0,
        10_000_000,
        base_time + timedelta(seconds=1),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "binance",
        101.0,
        101.2,
        50_000,
        45_000,
        0.05,
        base_time,
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "okx",
        99.8,
        100.0,
        60_000,
        58_000,
        0.03,
        base_time + timedelta(seconds=1),
    )
    _insert_funding(db, "BTC/USDT", "binance", 0.0006, 101.0, 100.8, base_time)
    _insert_funding(db, "BTC/USDT", "okx", -0.0004, 100.0, 99.9, base_time + timedelta(seconds=2))
    _insert_indicator_context(
        db,
        "BTC/USDT",
        "1h",
        base_time - timedelta(hours=1),
        close=100.5,
        rsi_14=61.0,
        macd_hist=0.35,
        atr_pct_14=1.4,
        volatility_20=0.018,
        adx_14=29.0,
        bb_width=0.06,
        price_zscore_20=0.8,
        volume_ratio_20=1.2,
        cross_exchange_last_price_range_bps=18.0,
        funding_basis_bps_mean=4.0,
        orderbook_total_depth_notional=180_000.0,
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["funding_rate_a"] == 0.0006
    assert row["funding_rate_b"] == -0.0004
    assert row["funding_rate_diff_bps"] == 10.0
    assert row["context_timeframe"] == "1h"
    assert row["context_rsi_14"] == 61.0
    assert row["market_regime_label"] == "trend_up"
    assert row["funding_regime_label"] == "funding_direction_conflict"
    assert row["context_completeness_score"] == 100.0
    service.close()


def test_exchange_comparison_uses_latest_non_future_indicator_context(tmp_path):
    config = ExchangeComparisonConfig(
        indicator_timeframe="1h",
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        max_indicator_age_seconds=7200,
        include_funding_context=False,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance")
    _insert_market_info(db, "BTC/USDT", "okx")
    _insert_ticker(db, "BTC/USDT", "binance", 101.1, 101.0, 101.2, 12_000_000, base_time)
    _insert_ticker(
        db,
        "BTC/USDT",
        "okx",
        99.9,
        99.8,
        100.0,
        10_000_000,
        base_time + timedelta(seconds=1),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "binance",
        101.0,
        101.2,
        50_000,
        45_000,
        0.05,
        base_time,
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "okx",
        99.8,
        100.0,
        60_000,
        58_000,
        0.03,
        base_time + timedelta(seconds=1),
    )
    _insert_indicator_context(
        db,
        "BTC/USDT",
        "1h",
        base_time - timedelta(hours=1),
        close=100.5,
        rsi_14=61.0,
        macd_hist=0.35,
        atr_pct_14=1.4,
        volatility_20=0.018,
        adx_14=29.0,
        bb_width=0.06,
        price_zscore_20=0.8,
        volume_ratio_20=1.2,
        cross_exchange_last_price_range_bps=18.0,
        funding_basis_bps_mean=4.0,
        orderbook_total_depth_notional=180_000.0,
    )
    _insert_indicator_context(
        db,
        "BTC/USDT",
        "1h",
        base_time + timedelta(hours=1),
        close=101.5,
        rsi_14=88.0,
        macd_hist=1.35,
        atr_pct_14=3.4,
        volatility_20=0.058,
        adx_14=49.0,
        bb_width=0.16,
        price_zscore_20=2.8,
        volume_ratio_20=3.2,
        cross_exchange_last_price_range_bps=48.0,
        funding_basis_bps_mean=14.0,
        orderbook_total_depth_notional=280_000.0,
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
        persist=False,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["context_rsi_14"] == 61.0
    assert row["context_macd_hist"] == 0.35
    assert row["market_regime_label"] == "trend_up"
    assert "missing_indicator_context" not in row["data_quality_flag"]
    service.close()


def test_exchange_comparison_drops_stale_indicator_context_instead_of_reusing_old_row(tmp_path):
    config = ExchangeComparisonConfig(
        indicator_timeframe="1h",
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        max_indicator_age_seconds=7200,
        include_funding_context=False,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance")
    _insert_market_info(db, "BTC/USDT", "okx")
    _insert_ticker(db, "BTC/USDT", "binance", 101.1, 101.0, 101.2, 12_000_000, base_time)
    _insert_ticker(
        db,
        "BTC/USDT",
        "okx",
        99.9,
        99.8,
        100.0,
        10_000_000,
        base_time + timedelta(seconds=1),
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "binance",
        101.0,
        101.2,
        50_000,
        45_000,
        0.05,
        base_time,
    )
    _insert_orderbook(
        db,
        "BTC/USDT",
        "okx",
        99.8,
        100.0,
        60_000,
        58_000,
        0.03,
        base_time + timedelta(seconds=1),
    )
    _insert_indicator_context(
        db,
        "BTC/USDT",
        "1h",
        base_time - timedelta(hours=5),
        close=95.5,
        rsi_14=41.0,
        macd_hist=-0.35,
        atr_pct_14=1.4,
        volatility_20=0.018,
        adx_14=19.0,
        bb_width=0.06,
        price_zscore_20=-0.8,
        volume_ratio_20=0.9,
        cross_exchange_last_price_range_bps=12.0,
        funding_basis_bps_mean=2.0,
        orderbook_total_depth_notional=80_000.0,
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
        persist=False,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert pd.isna(row["context_timeframe"])
    assert row["context_completeness_score"] == 0.0
    assert row["market_regime_label"] == "unknown"
    assert "missing_indicator_context" in row["data_quality_flag"]
    service.close()


def test_exchange_comparison_prefers_latest_timestamp_over_latest_insert_id(tmp_path):
    config = ExchangeComparisonConfig(
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        snapshot_lookback_seconds=1800,
        max_ticker_age_seconds=120,
        max_orderbook_age_seconds=120,
        include_indicator_context=False,
        target_notional=1000.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "ETH/USDT", "binance")
    _insert_market_info(db, "ETH/USDT", "okx")
    _insert_ticker(db, "ETH/USDT", "binance", 100.2, 100.1, 100.3, 5_000_000, base_time)
    _insert_ticker(
        db,
        "ETH/USDT",
        "binance",
        99.0,
        98.9,
        99.1,
        5_100_000,
        base_time - timedelta(seconds=30),
    )
    _insert_ticker(db, "ETH/USDT", "okx", 100.0, 99.9, 100.1, 4_800_000, base_time)
    _insert_orderbook(
        db,
        "ETH/USDT",
        "binance",
        100.1,
        100.3,
        40_000,
        41_000,
        0.01,
        base_time,
    )
    _insert_orderbook(
        db,
        "ETH/USDT",
        "okx",
        99.9,
        100.1,
        42_000,
        39_000,
        0.01,
        base_time,
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="ETH/USDT",
        as_of=base_time + timedelta(seconds=5),
        persist=False,
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["last_price_a"] == 100.2
    assert row["ticker_timestamp_a"] == base_time
    service.close()


def test_exchange_comparison_can_build_from_latest_snapshot_tables(tmp_path):
    config = ExchangeComparisonConfig(
        compare_window_seconds=5,
        orderbook_window_seconds=5,
        snapshot_lookback_seconds=1800,
        max_ticker_age_seconds=60,
        max_orderbook_age_seconds=60,
        target_notional=1000.0,
        min_actionable_net_spread_bps=2.0,
        max_slippage_bps=25.0,
    )
    service = _build_service(tmp_path, config)
    db = service.db
    base_time = datetime(2026, 5, 6, 12, 0, 0)

    _insert_market_info(db, "BTC/USDT", "binance")
    _insert_market_info(db, "BTC/USDT", "okx")
    db.execute(
        """
        INSERT INTO latest_tickers (
            symbol, exchange, last_price, bid, ask, mid_price,
            spread_bps, quote_volume_24h, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT", "binance", 101.1, 101.0, 101.2, 101.1, 19.78, 12_000_000, base_time.isoformat()),
    )
    db.execute(
        """
        INSERT INTO latest_tickers (
            symbol, exchange, last_price, bid, ask, mid_price,
            spread_bps, quote_volume_24h, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT", "okx", 99.9, 99.8, 100.0, 99.9, 20.02, 10_000_000, (base_time + timedelta(seconds=1)).isoformat()),
    )
    db.execute(
        """
        INSERT INTO latest_orderbook_snapshots (
            symbol, exchange, snapshot_depth, best_bid, best_ask, mid_price,
            spread, spread_bps, bid_depth_notional, ask_depth_notional,
            depth_imbalance, bids_json, asks_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT", "binance", 20, 101.0, 101.2, 101.1, 0.2, 19.78, 50_000, 45_000, 0.05, "[]", "[]", base_time.isoformat()),
    )
    db.execute(
        """
        INSERT INTO latest_orderbook_snapshots (
            symbol, exchange, snapshot_depth, best_bid, best_ask, mid_price,
            spread, spread_bps, bid_depth_notional, ask_depth_notional,
            depth_imbalance, bids_json, asks_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BTC/USDT", "okx", 20, 99.8, 100.0, 99.9, 0.2, 20.02, 60_000, 58_000, 0.03, "[]", "[]", (base_time + timedelta(seconds=1)).isoformat()),
    )
    db.commit()

    frame = service.build_latest_snapshots(
        symbol="BTC/USDT",
        as_of=base_time + timedelta(seconds=5),
    )

    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["best_buy_exchange"] == "okx"
    assert row["best_sell_exchange"] == "binance"
    assert row["signal_label"] == "tradable_spread"
    assert bool(row["is_actionable"]) is True
    service.close()
