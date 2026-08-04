#!/usr/bin/env python3
"""Populate multi-band history for PIT identification (runtime-only config patch).

Does NOT commit exchange-config changes. Prefer OKX (Binance/Bybit often blocked).
Focuses on paper assets and daily/hourly bars for a usable archive.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Unlock options/tokenomics collectors that require non-empty endpoint gates.
os.environ.setdefault("OPTIONS_VOL_SURFACE_URL", "https://www.deribit.com/api/v2/public/get_instruments?currency=BTC&kind=option&expired=false")
os.environ.setdefault("OPTIONS_POSITIONING_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_RELATIVE_VALUE_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_STRIKE_CONCENTRATION_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_GAMMA_EXPOSURE_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_FLOW_ACTIVITY_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_EXPIRY_STRUCTURE_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("OPTIONS_HEDGE_PRESSURE_URL", os.environ["OPTIONS_VOL_SURFACE_URL"])
os.environ.setdefault("TOKENOMICS_CIRCULATING_SUPPLY_URL", "https://api.coingecko.com/api/v3/ping")
os.environ.setdefault("TOKENOMICS_STAKING_RATIO_URL", "https://api.coingecko.com/api/v3/ping")

import config.settings as settings
import config.symbols as symbols
from pdf.sci.experiment_config import bootstrap_symbols

PAPER_SYMBOLS = bootstrap_symbols()


def patch_runtime_config() -> None:
    symbols.TARGET_EXCHANGES[:] = ["okx"]
    symbols.TARGET_SYMBOLS[:] = PAPER_SYMBOLS
    symbols.KLINE_TIMEFRAMES[:] = ["1h", "1d"]
    symbols.KLINE_BACKFILL_DAYS = 400
    settings.EXCHANGE_CONFIG["binance"]["enabled"] = False
    settings.EXCHANGE_CONFIG["bybit"]["enabled"] = False
    settings.EXCHANGE_CONFIG["okx"]["enabled"] = True
    print("Patched: exchanges=okx, symbols=", PAPER_SYMBOLS, "tf=", symbols.KLINE_TIMEFRAMES, "days=", symbols.KLINE_BACKFILL_DAYS)


def init_db() -> None:
    from database.router import DatabaseRouter, Domain

    r = DatabaseRouter()
    r.get_manager(Domain.EXCHANGE_DATA)
    r.get_manager(Domain.MARKET_DATA)
    r.get_analytics_db()
    print("DB schema ready")


def run_step(name: str, fn) -> None:
    print(f"\n=== {name} ===")
    try:
        fn()
        print(f"OK: {name}")
    except Exception as e:
        print(f"FAIL: {name}: {e}")
        traceback.print_exc()


def main() -> None:
    patch_runtime_config()
    init_db()

    def exchange_bootstrap():
        from data_layer.exchange_data.service import ExchangeDataService

        svc = ExchangeDataService()
        svc.bootstrap(include_backfill=True)

    def funding_backfill():
        from data_layer.exchange_data.service import ExchangeDataService

        ExchangeDataService().backfill_funding_history(days=90)

    def exchange_once():
        from data_layer.exchange_data.service import ExchangeDataService

        ExchangeDataService().collect_once(include_backfill=False)

    def macro_bootstrap():
        from data_layer.macro_data.service import MacroDataService

        MacroDataService().bootstrap()

    def news_once():
        from data_layer.news_data.service import NewsDataService

        NewsDataService().collect_once()

    def alt_bootstrap():
        from data_layer.alternative_data.service import AlternativeDataService

        AlternativeDataService().bootstrap()

    def onchain_once():
        from data_layer.onchain_data.service import OnchainDataService

        # built-in sources that do not need custom URLs
        OnchainDataService().collect_once(
            source_names=[
                "protocol_tvl",
                "network_usage",
                "dex_volume",
                "stablecoin_supply",
                "market_sentiment",
                "global_market",
                "defi_yields",
            ],
            lookback_hours=24 * 30,
        )

    def options_once():
        from data_layer.options_data.service import OptionsDataService

        OptionsDataService().collect_once(lookback_hours=72)

    def tokenomics_once():
        from data_layer.tokenomics_data.service import TokenomicsDataService

        TokenomicsDataService().collect_once(
            source_names=["circulating_supply", "staking_ratio"],
            lookback_hours=24 * 30,
        )

    def logic_once():
        from logic_layer.logic_pipeline.service import run_full_pipeline

        print(run_full_pipeline())

    def readiness_snapshot():
        from logic_layer.asset_readiness.service import AssetReadinessService

        svc = AssetReadinessService()
        bundle = svc.build_latest_context_bundle()
        svc.save_snapshot(bundle)
        print("readiness keys", list(bundle)[:8] if isinstance(bundle, dict) else type(bundle))

    def quality_audit():
        from data_layer.data_quality.audit import DataLayerAuditService

        DataLayerAuditService().save_market_world_audit_snapshot()

    run_step("exchange bootstrap (okx klines)", exchange_bootstrap)
    run_step("funding backfill 90d", funding_backfill)
    run_step("exchange once (latest context)", exchange_once)
    run_step("macro bootstrap", macro_bootstrap)
    run_step("news once", news_once)
    run_step("alternative bootstrap", alt_bootstrap)
    run_step("onchain once", onchain_once)
    run_step("options once", options_once)
    run_step("tokenomics once", tokenomics_once)
    run_step("logic pipeline once", logic_once)
    run_step("asset readiness snapshot", readiness_snapshot)
    run_step("data quality audit", quality_audit)

    # inventory
    from database.router import DatabaseRouter, Domain

    r = DatabaseRouter()
    ex = r.get_manager(Domain.EXCHANGE_DATA)
    mk = r.get_manager(Domain.MARKET_DATA)
    an = r.get_analytics_db()
    checks = [
        (ex, "klines"),
        (ex, "funding_rates"),
        (ex, "tickers"),
        (mk, "macro_timeseries"),
        (mk, "news_articles"),
        (mk, "onchain_timeseries"),
        (mk, "options_timeseries"),
        (mk, "tokenomics_timeseries"),
        (mk, "alternative_timeseries"),
        (an, "merged_klines"),
        (an, "asset_readiness_snapshots"),
        (an, "ai_market_context_snapshots"),
    ]
    print("\n=== archive counts ===")
    for db, table in checks:
        try:
            n = db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table:32s} {n}")
        except Exception as e:
            print(f"{table:32s} ERR {e}")


if __name__ == "__main__":
    main()
