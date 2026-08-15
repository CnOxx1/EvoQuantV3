from __future__ import annotations

from unittest.mock import patch

from config.symbols import DEFAULT_TARGET_SYMBOLS, TARGET_ASSET_CODES
from data_layer.cefi_lending_rate.service import TARGET_ASSETS as LENDING_ASSETS
from data_layer.cex_orderbook_depth.service import DEFAULT_SYMBOLS as DEPTH_SYMBOLS
from data_layer.orderflow_data.service import TARGET_SYMBOLS as ORDERFLOW_SYMBOLS
from data_layer.perpetual_basis_curve.service import TARGET_SYMBOLS as BASIS_SYMBOLS
from data_layer.social_sentiment_data.service import TARGET_SYMBOLS as SENTIMENT_DATA_SYMBOLS
from data_layer.whale_tracker_data.service import TARGET_SYMBOLS as WHALE_SYMBOLS
from logic_layer.anomaly_detection.service import TARGET_SYMBOLS as ANOMALY_SYMBOLS
from logic_layer.cross_venue_arbitrage.service import CrossVenueArbService
from logic_layer.funding_rate_model.service import TARGET_SYMBOLS as FUNDING_SYMBOLS
from logic_layer.liquidation_cascade.service import LiquidationCascadeService
from logic_layer.liquidity_analysis.service import TARGET_SYMBOLS as LIQUIDITY_SYMBOLS
from logic_layer.logic_pipeline.service import _make_ai_market_context
from logic_layer.onchain_lead_lag.service import OnchainLeadLagService
from logic_layer.regime_detection.service import TARGET_SYMBOLS as REGIME_SYMBOLS
from logic_layer.sentiment_signal.service import TARGET_SYMBOLS as SIGNAL_SYMBOLS
from logic_layer.volatility_forecast.service import TARGET_SYMBOLS as VOLATILITY_SYMBOLS


PAIR_SYMBOL_SERVICES = [DEPTH_SYMBOLS, BASIS_SYMBOLS]
ASSET_CODE_SERVICES = [
    LENDING_ASSETS,
    ORDERFLOW_SYMBOLS,
    SENTIMENT_DATA_SYMBOLS,
    WHALE_SYMBOLS,
    ANOMALY_SYMBOLS,
    FUNDING_SYMBOLS,
    LIQUIDITY_SYMBOLS,
    REGIME_SYMBOLS,
    SIGNAL_SYMBOLS,
    VOLATILITY_SYMBOLS,
    CrossVenueArbService.SYMBOLS,
    LiquidationCascadeService.SYMBOLS,
    OnchainLeadLagService.SYMBOLS,
]


def test_default_monitoring_pairs_are_btc_and_eth_only():
    assert DEFAULT_TARGET_SYMBOLS == ["BTC/USDT", "ETH/USDT"]
    assert TARGET_ASSET_CODES == ["BTC", "ETH"]


def test_asset_code_monitoring_services_follow_unified_default():
    assert all(symbols == ["BTC", "ETH"] for symbols in ASSET_CODE_SERVICES)


def test_pair_monitoring_services_follow_unified_default():
    assert all(symbols == ["BTCUSDT", "ETHUSDT"] for symbols in PAIR_SYMBOL_SERVICES)


def test_ai_market_context_pipeline_uses_btc_and_eth_only():
    runner = _make_ai_market_context()

    with patch("logic_layer.ai_market_context.service.AIMarketContextService") as service_class:
        service = service_class.return_value
        runner()

    assert service.build_latest_snapshots.call_args.kwargs["entity_keys"] == ["BTC", "ETH"]
    service.close.assert_called_once()
