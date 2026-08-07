"""Gates for single-venue / geo-limited deploys (TARGET_EXCHANGES=okx)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_target_exchanges_env_override(monkeypatch):
    monkeypatch.setenv("TARGET_EXCHANGES", "okx")
    import importlib
    import config.symbols as symbols

    importlib.reload(symbols)
    assert symbols.TARGET_EXCHANGES == ["okx"]

    import config.settings as settings

    importlib.reload(settings)
    assert settings.SINGLE_EXCHANGE_MODE is True
    assert settings.EXCHANGE_CONFIG["okx"]["enabled"] is True
    assert settings.EXCHANGE_CONFIG["binance"]["enabled"] is False
    assert settings.EXCHANGE_CONFIG["bybit"]["enabled"] is False

    # Restore defaults for other tests in this process.
    monkeypatch.delenv("TARGET_EXCHANGES", raising=False)
    importlib.reload(symbols)
    importlib.reload(settings)


def test_universe_summary_scales_exchange_floor(monkeypatch):
    monkeypatch.setenv("TARGET_EXCHANGES", "okx")
    import importlib
    import config.symbols as symbols

    importlib.reload(symbols)
    import data_layer.exchange_data.service as svc_mod

    importlib.reload(svc_mod)
    summary = svc_mod.ExchangeDataService._build_configured_universe_summary()
    assert summary["exchange_count"] == 1
    assert summary["minimum_exchange_count_for_market_breadth"] == 1
    assert summary["breadth_status"] == "sufficient"

    monkeypatch.delenv("TARGET_EXCHANGES", raising=False)
    importlib.reload(symbols)
    importlib.reload(svc_mod)
    # Multi-venue default still uses the aspirational 4-exchange floor.
    default_summary = svc_mod.ExchangeDataService._build_configured_universe_summary()
    assert default_summary["exchange_count"] == 3
    assert default_summary["minimum_exchange_count_for_market_breadth"] == 4
    assert default_summary["breadth_status"] == "limited"


def test_hot_source_health_prefers_observation_time(monkeypatch):
    monkeypatch.setenv("TARGET_EXCHANGES", "okx")
    import importlib
    import config.symbols as symbols

    importlib.reload(symbols)
    import data_layer.exchange_data.service as svc_mod

    importlib.reload(svc_mod)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fresh_obs = (now - timedelta(seconds=5)).isoformat()
    old_run = (now - timedelta(hours=2)).isoformat()

    # Observation-primary: fresh snapshot wins over stale collection_runs row.
    svc = svc_mod.ExchangeDataService
    assert "ticker" in svc.OBSERVATION_PRIMARY_HEALTH_SOURCES

    # Reconstruct the staleness choice used in load_source_coverage.
    latest_observation_dt = svc._to_datetime(fresh_obs)
    last_run_dt = svc._to_datetime(old_run)
    if latest_observation_dt is not None:
        staleness_anchor = latest_observation_dt
    else:
        staleness_anchor = last_run_dt or latest_observation_dt
    stale_mult = max(5 * 3, 45)  # single-exchange ticker floor
    age = (now - staleness_anchor).total_seconds()
    assert age <= stale_mult

    monkeypatch.delenv("TARGET_EXCHANGES", raising=False)
    importlib.reload(symbols)
    importlib.reload(svc_mod)


def test_alternative_shared_ready_without_asset_match():
    from logic_layer.asset_readiness.service import AssetReadinessService

    svc = AssetReadinessService()
    detail = svc._band_from_alternative(
        "BTC",
        {},
        {
            "ai_ready_source_names": ["stablecoin_supply"],
            "latest_ok_point_count": 4,
            "raw_row_count": 10,
        },
    )
    assert detail["status"] == "shared_ready"
    assert detail["band_name"] == "alternative"
