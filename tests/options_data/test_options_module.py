import sys
from pathlib import Path
from unittest.mock import patch

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.options_data.service import OptionsDataService


OPTIONS_CONFIG_PATCH = {
    "enable_vol_surface": True,
    "enable_relative_value": True,
    "enable_strike_concentration": True,
    "enable_gamma_exposure": True,
    "enable_flow_activity": True,
    "enable_expiry_structure": True,
    "enable_hedge_pressure": True,
    "enable_positioning": True,
    "vol_surface_url": "https://example.test/options/vol-surface",
    "relative_value_url": "https://example.test/options/relative-value",
    "strike_concentration_url": "https://example.test/options/strike-concentration",
    "gamma_exposure_url": "https://example.test/options/gamma-exposure",
    "flow_activity_url": "https://example.test/options/flow-activity",
    "expiry_structure_url": "https://example.test/options/expiry-structure",
    "hedge_pressure_url": "https://example.test/options/hedge-pressure",
    "positioning_url": "https://example.test/options/positioning",
    "asset_entity_keys": "BTC,ETH",
    "default_interval": "1h",
    "default_lookback_hours": 72,
    "vol_surface_interval_seconds": 3600,
    "relative_value_interval_seconds": 3600,
    "strike_concentration_interval_seconds": 3600,
    "gamma_exposure_interval_seconds": 3600,
    "flow_activity_interval_seconds": 3600,
    "expiry_structure_interval_seconds": 3600,
    "hedge_pressure_interval_seconds": 3600,
    "positioning_interval_seconds": 3600,
}


class StaticOptionsClient:
    DEFAULT_VENUES = ("Deribit", "OKX", "Binance")

    @classmethod
    def _attach_default_venues(cls, row: dict) -> dict:
        payload = dict(row)
        if (
            "venue" not in payload
            and "venues" not in payload
            and "exchange" not in payload
        ):
            payload["venues"] = list(cls.DEFAULT_VENUES)
        return payload

    @staticmethod
    def _filter(rows: list[dict], entity_keys: list[str] | None) -> list[dict]:
        rows = [StaticOptionsClient._attach_default_venues(row) for row in rows]
        if not entity_keys:
            return rows
        allowed = {item.strip().upper() for item in entity_keys if item.strip()}
        return [
            row
            for row in rows
            if str(row["entity_key"]).strip().upper() in allowed
        ]

    def fetch_surface_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-SURFACE",
                "terms": [
                    {"tenor": "7d", "atm_iv": 0.62},
                    {
                        "tenor": "30d",
                        "atm_iv": 0.58,
                        "risk_reversal_25d": -0.03,
                        "butterfly_25d": 0.012,
                    },
                ],
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-SURFACE",
                "terms": [
                    {"tenor": "7d", "atm_iv": 0.71},
                    {
                        "tenor": "30d",
                        "atm_iv": 0.66,
                        "risk_reversal_25d": -0.05,
                        "butterfly_25d": 0.018,
                    },
                ],
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_positioning_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-OI",
                "call_open_interest_notional_30d": 1_400_000_000,
                "put_open_interest_notional_30d": 1_050_000_000,
                "total_open_interest_notional_30d": 2_450_000_000,
                "total_open_interest_notional_all": 3_100_000_000,
                "near_expiry_open_interest_notional": 550_000_000,
                "largest_expiry_open_interest_notional": 950_000_000,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-OI",
                "call_open_interest_notional_30d": 850_000_000,
                "put_open_interest_notional_30d": 935_000_000,
                "total_open_interest_notional_30d": 1_785_000_000,
                "total_open_interest_notional_all": 2_050_000_000,
                "near_expiry_open_interest_notional": 280_000_000,
                "largest_expiry_open_interest_notional": 620_000_000,
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_relative_value_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-RV",
                "realized_vol_7d": 0.49,
                "realized_vol_30d": 0.52,
                "atm_iv_7d": 0.62,
                "atm_iv_30d": 0.58,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-RV",
                "realized_vol_7d": 0.63,
                "realized_vol_30d": 0.61,
                "atm_iv_7d": 0.71,
                "atm_iv_30d": 0.66,
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_strike_concentration_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-STRIKE",
                "spot_price": 100000.0,
                "max_pain_price": 98500.0,
                "largest_call_wall_strike": 105000.0,
                "largest_put_wall_strike": 96000.0,
                "total_open_interest_notional": 3_100_000_000.0,
                "top_strike_open_interest_notional": 775_000_000.0,
                "near_expiry_total_open_interest_notional": 900_000_000.0,
                "near_expiry_top_strike_open_interest_notional": 315_000_000.0,
                "atm_band_open_interest_notional": 1_302_000_000.0,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-STRIKE",
                "spot_price": 2500.0,
                "max_pain_price": 2525.0,
                "largest_call_wall_strike": 2800.0,
                "largest_put_wall_strike": 2325.0,
                "total_open_interest_notional": 2_050_000_000.0,
                "top_strike_open_interest_notional": 369_000_000.0,
                "near_expiry_total_open_interest_notional": 620_000_000.0,
                "near_expiry_top_strike_open_interest_notional": 136_400_000.0,
                "atm_band_open_interest_notional": 697_000_000.0,
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_gamma_exposure_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-GAMMA",
                "spot_price": 100000.0,
                "net_gamma_exposure": 45_000_000.0,
                "gross_gamma_exposure": 120_000_000.0,
                "gamma_flip_price": 99200.0,
                "call_gamma_wall_strike": 103000.0,
                "put_gamma_wall_strike": 97000.0,
                "top_gamma_strike_exposure": 36_000_000.0,
                "near_expiry_gamma_exposure": 66_000_000.0,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-GAMMA",
                "spot_price": 2500.0,
                "net_gamma_exposure": -18_000_000.0,
                "gross_gamma_exposure": 72_000_000.0,
                "gamma_flip_price": 2575.0,
                "call_gamma_wall_strike": 2750.0,
                "put_gamma_wall_strike": 2380.0,
                "top_gamma_strike_exposure": 14_400_000.0,
                "near_expiry_gamma_exposure": 28_800_000.0,
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_flow_activity_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-FLOW",
                "total_premium_notional": 120_000_000.0,
                "call_buyer_initiated_premium": 42_000_000.0,
                "put_buyer_initiated_premium": 18_000_000.0,
                "call_seller_initiated_premium": 12_000_000.0,
                "put_seller_initiated_premium": 9_000_000.0,
                "opening_premium_notional": 78_000_000.0,
                "near_expiry_premium_notional": 66_000_000.0,
                "block_trade_premium_notional": 24_000_000.0,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-FLOW",
                "total_premium_notional": 90_000_000.0,
                "call_buyer_initiated_premium": 18_000_000.0,
                "put_buyer_initiated_premium": 31_500_000.0,
                "call_seller_initiated_premium": 13_500_000.0,
                "put_seller_initiated_premium": 9_000_000.0,
                "opening_premium_notional": 45_000_000.0,
                "near_expiry_premium_notional": 27_000_000.0,
                "block_trade_premium_notional": 31_500_000.0,
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_expiry_structure_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-EXPIRY",
                "total_open_interest_notional": 3_200_000_000.0,
                "gross_gamma_exposure": 120_000_000.0,
                "total_premium_notional": 120_000_000.0,
                "expiry_buckets": [
                    {
                        "bucket": "7d",
                        "open_interest_notional": 960_000_000.0,
                        "gamma_exposure": 60_000_000.0,
                        "premium_notional": 54_000_000.0,
                    },
                    {
                        "bucket": "30d",
                        "open_interest_notional": 1_120_000_000.0,
                        "gamma_exposure": 36_000_000.0,
                        "premium_notional": 40_800_000.0,
                    },
                    {
                        "bucket": "90d_plus",
                        "open_interest_notional": 480_000_000.0,
                        "gamma_exposure": 12_000_000.0,
                        "premium_notional": 9_600_000.0,
                    },
                    {
                        "bucket": "other",
                        "open_interest_notional": 640_000_000.0,
                        "gamma_exposure": 12_000_000.0,
                        "premium_notional": 15_600_000.0,
                    },
                ],
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-EXPIRY",
                "total_open_interest_notional": 2_400_000_000.0,
                "gross_gamma_exposure": 72_000_000.0,
                "total_premium_notional": 90_000_000.0,
                "expiry_buckets": [
                    {
                        "bucket": "7d",
                        "open_interest_notional": 360_000_000.0,
                        "gamma_exposure": 14_400_000.0,
                        "premium_notional": 18_000_000.0,
                    },
                    {
                        "bucket": "30d",
                        "open_interest_notional": 720_000_000.0,
                        "gamma_exposure": 25_920_000.0,
                        "premium_notional": 32_400_000.0,
                    },
                    {
                        "bucket": "90d_plus",
                        "open_interest_notional": 720_000_000.0,
                        "gamma_exposure": 10_800_000.0,
                        "premium_notional": 13_500_000.0,
                    },
                    {
                        "bucket": "other",
                        "open_interest_notional": 600_000_000.0,
                        "gamma_exposure": 20_880_000.0,
                        "premium_notional": 26_100_000.0,
                    },
                ],
            },
        ]
        return self._filter(rows, entity_keys)

    def fetch_hedge_pressure_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = [
            {
                "entity_key": "BTC",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "BTC-OPTION-HEDGE",
                "spot_price": 100000.0,
                "gross_gamma_exposure": 120_000_000.0,
                "total_charm_exposure": 30_000_000.0,
                "total_color_exposure": 18_000_000.0,
                "vanna_exposure": 18_000_000.0,
                "charm_exposure": -9_000_000.0,
                "volga_exposure": 10_800_000.0,
                "vomma_exposure": 13_200_000.0,
                "color_exposure": -7_200_000.0,
                "vanna_flip_price": 101500.0,
                "charm_flip_price": 98800.0,
                "near_expiry_charm_exposure": 21_000_000.0,
                "near_expiry_color_exposure": 12_600_000.0,
            },
            {
                "entity_key": "ETH",
                "observation_time": "2026-05-08T08:00:00+00:00",
                "interval": interval or "1h",
                "quality_flag": "ok",
                "source_symbol": "ETH-OPTION-HEDGE",
                "spot_price": 2500.0,
                "gross_gamma_exposure": 72_000_000.0,
                "total_charm_exposure": 24_000_000.0,
                "total_color_exposure": 21_600_000.0,
                "vanna_exposure": -14_400_000.0,
                "charm_exposure": 10_800_000.0,
                "volga_exposure": -11_520_000.0,
                "vomma_exposure": -14_400_000.0,
                "color_exposure": 18_000_000.0,
                "vanna_flip_price": 2440.0,
                "charm_flip_price": 2510.0,
                "near_expiry_charm_exposure": 12_000_000.0,
                "near_expiry_color_exposure": 16_200_000.0,
            },
        ]
        return self._filter(rows, entity_keys)


class PartialVenueSurfaceOptionsClient(StaticOptionsClient):
    def fetch_surface_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = super().fetch_surface_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        for row in rows:
            row["venues"] = ["Deribit"]
        return rows


class PartialQualitySurfaceOptionsClient(StaticOptionsClient):
    def fetch_surface_snapshots(
        self,
        source,
        entity_keys=None,
        interval=None,
        lookback_hours=None,
    ) -> list[dict]:
        rows = super().fetch_surface_snapshots(
            source,
            entity_keys=entity_keys,
            interval=interval,
            lookback_hours=lookback_hours,
        )
        if rows:
            rows[0]["quality_flag"] = "partial"
        return rows


def test_init_storage_creates_options_tables_and_catalog(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_init.sqlite")),
        )
        service.init_storage()

        tables = {
            row["name"]
            for row in service.db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        factor_count = service.db.fetch_one(
            "SELECT COUNT(*) AS count FROM options_factor_catalog"
        )["count"]

        assert "options_factor_catalog" in tables
        assert "options_timeseries" in tables
        assert "latest_options_timeseries" in tables
        assert factor_count == 55
        service.close()


def test_collect_once_persists_options_points(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_collect.sqlite")),
        )
        service.init_storage()

        summary = service.collect_once(interval="1h", lookback_hours=24)

        history_count = service.db.fetch_one(
            "SELECT COUNT(*) AS count FROM options_timeseries"
        )["count"]
        latest_count = service.db.fetch_one(
            "SELECT COUNT(*) AS count FROM latest_options_timeseries"
        )["count"]
        btc_term_structure = service.db.fetch_one(
            """
            SELECT value
            FROM latest_options_timeseries
            WHERE entity_key = 'BTC' AND factor_id = 'options_iv_term_structure_7d_30d'
            """
        )["value"]
        btc_net_call_flow_ratio = service.db.fetch_one(
            """
            SELECT value
            FROM latest_options_timeseries
            WHERE entity_key = 'BTC' AND factor_id = 'options_net_call_premium_flow_ratio'
            """
        )["value"]
        btc_oi_share_7d = service.db.fetch_one(
            """
            SELECT value
            FROM latest_options_timeseries
            WHERE entity_key = 'BTC' AND factor_id = 'options_oi_share_7d'
            """
        )["value"]
        btc_vanna_ratio = service.db.fetch_one(
            """
            SELECT value
            FROM latest_options_timeseries
            WHERE entity_key = 'BTC' AND factor_id = 'options_vanna_exposure_ratio'
            """
        )["value"]
        eth_color_ratio = service.db.fetch_one(
            """
            SELECT value
            FROM latest_options_timeseries
            WHERE entity_key = 'ETH' AND factor_id = 'options_color_exposure_ratio'
            """
        )["value"]

        assert summary == {
            "vol_surface_points": 10,
            "relative_value_points": 8,
            "strike_concentration_points": 12,
            "gamma_exposure_points": 14,
            "flow_activity_points": 14,
            "expiry_structure_points": 14,
            "hedge_pressure_points": 28,
            "positioning_points": 10,
            "total_points": 110,
        }
        assert history_count == 110
        assert latest_count == 110
        assert round(float(btc_term_structure), 6) == 0.04
        assert round(float(btc_net_call_flow_ratio), 6) == 0.25
        assert round(float(btc_oi_share_7d), 6) == 0.3
        assert round(float(btc_vanna_ratio), 6) == 0.15
        assert round(float(eth_color_ratio), 6) == 0.25
        service.close()


def test_load_latest_context_bundle_groups_options_signals(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_bundle.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        bundle = service.load_latest_context_bundle(entity_keys=["BTC", "ETH"])

        assert bundle["row_count"] == 110
        assert bundle["entity_count"] == 2
        assert bundle["source_counts"] == {
            "vol_surface": 10,
            "relative_value": 8,
            "strike_concentration": 12,
            "gamma_exposure": 14,
            "flow_activity": 14,
            "expiry_structure": 14,
            "hedge_pressure": 28,
            "positioning": 10,
        }
        assert bundle["leaders"]["highest_atm_iv_30d"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_put_skewed"]["entity_key"] == "ETH"
        assert bundle["leaders"]["closest_max_pain_to_spot"]["entity_key"] == "ETH"
        assert bundle["leaders"]["richest_iv_vs_rv_30d"]["entity_key"] == "BTC"
        assert bundle["leaders"]["cheapest_iv_vs_rv_30d"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_positive_net_gamma_ratio"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_negative_net_gamma_ratio"]["entity_key"] == "ETH"
        assert bundle["leaders"]["closest_gamma_flip_to_spot"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_call_buyer_dominated"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_put_buyer_dominated"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_bullish_net_call_flow"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_bearish_net_put_flow"]["entity_key"] == "ETH"
        assert bundle["leaders"]["highest_oi_share_7d"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_oi_share_90d_plus"]["entity_key"] == "ETH"
        assert bundle["leaders"]["highest_gamma_share_7d"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_gamma_share_30d"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_positive_vanna_ratio"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_negative_vanna_ratio"]["entity_key"] == "ETH"
        assert bundle["leaders"]["closest_vanna_flip_to_spot"]["entity_key"] == "BTC"
        assert bundle["leaders"]["closest_charm_flip_to_spot"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_positive_volga_ratio"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_negative_volga_ratio"]["entity_key"] == "ETH"
        assert bundle["leaders"]["most_positive_vomma_ratio"]["entity_key"] == "BTC"
        assert bundle["leaders"]["most_negative_vomma_ratio"]["entity_key"] == "ETH"
        assert bundle["leaders"]["largest_abs_color_ratio"]["entity_key"] == "ETH"
        assert bundle["leaders"]["highest_near_expiry_color_share"]["entity_key"] == "ETH"
        assert bundle["leaders"]["largest_total_oi_notional"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_top_strike_oi_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_top_gamma_strike_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_near_expiry_top_strike_oi_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_near_expiry_gamma_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_premium_flow_share_7d"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_premium_flow_share_30d"]["entity_key"] == "ETH"
        assert bundle["leaders"]["highest_near_expiry_charm_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_opening_flow_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_near_expiry_flow_share"]["entity_key"] == "BTC"
        assert bundle["leaders"]["highest_block_trade_flow_share"]["entity_key"] == "ETH"
        assert bundle["leaders"]["highest_put_call_oi_ratio"]["entity_key"] == "ETH"
        assert bundle["sources"]["vol_surface"]["iv_leaders"][0]["entity_key"] == "ETH"
        assert bundle["sources"]["relative_value"]["rich_iv_leaders"][0]["entity_key"] == "BTC"
        assert bundle["sources"]["strike_concentration"]["pin_risk_watchlist"][0]["entity_key"] == "BTC"
        assert bundle["sources"]["gamma_exposure"]["regime_watchlist"][0]["entity_key"] == "BTC"
        assert bundle["sources"]["flow_activity"]["flow_watchlist"][0]["entity_key"] == "BTC"
        assert bundle["sources"]["expiry_structure"]["expiry_watchlist"][0]["entity_key"] == "BTC"
        assert bundle["sources"]["hedge_pressure"]["hedge_watchlist"][0]["entity_key"] == "ETH"
        assert round(
            float(bundle["sources"]["hedge_pressure"]["hedge_watchlist"][0]["color_exposure_ratio"]),
            6,
        ) == 0.25
        assert bundle["sources"]["positioning"]["oi_leaders"][0]["entity_key"] == "BTC"
        assert bundle["configured_universe_summary"] == {
            "scope_kind": "filtered",
            "tracked_entity_keys": ["BTC", "ETH"],
            "asset_entity_count": 2,
            "minimum_asset_entity_count_for_market_breadth": 6,
            "breadth_status": "filtered",
            "is_market_breadth_sufficient": None,
        }
        assert bundle["data_quality_flags"] == []
        assert bundle["quality_notes"] == []

        service.close()


def test_load_latest_context_bundle_marks_incomplete_asset_universe(tmp_path):
    config_patch = {
        **OPTIONS_CONFIG_PATCH,
        "asset_entity_keys": "BTC,ETH,SOL,SUI",
    }
    with patch.dict("config.settings.OPTIONS_CONFIG", config_patch, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_bundle_universe.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        bundle = service.load_latest_context_bundle()

        assert bundle["row_count"] == 0
        assert bundle["raw_row_count"] == 110
        assert bundle["entity_count"] == 0
        assert bundle["raw_entity_count"] == 2
        assert bundle["source_counts"] == {}
        assert bundle["raw_source_counts"] == {
            "hedge_pressure": 28,
            "expiry_structure": 14,
            "flow_activity": 14,
            "gamma_exposure": 14,
            "strike_concentration": 12,
            "positioning": 10,
            "vol_surface": 10,
            "relative_value": 8,
        }
        assert bundle["ai_ready_source_names"] == []
        assert bundle["ai_excluded_source_names"] == [
            "expiry_structure",
            "flow_activity",
            "gamma_exposure",
            "hedge_pressure",
            "positioning",
            "relative_value",
            "strike_concentration",
            "vol_surface",
        ]
        assert bundle["coverage_summary"]["expected_entity_count"] == 4
        assert bundle["coverage_summary"]["observed_entity_count"] == 0
        assert bundle["coverage_summary"]["raw_observed_entity_count"] == 2
        assert bundle["coverage_summary"]["expected_factor_count"] == 55
        assert bundle["coverage_summary"]["observed_factor_count"] == 0
        assert bundle["coverage_summary"]["raw_observed_factor_count"] == 55
        assert bundle["coverage_summary"]["observed_point_count"] == 0
        assert bundle["coverage_summary"]["raw_observed_point_count"] == 110
        assert bundle["coverage_summary"]["missing_entity_keys"] == ["BTC", "ETH", "SOL", "SUI"]
        assert bundle["configured_universe_summary"] == {
            "scope_kind": "default",
            "tracked_entity_keys": ["BTC", "ETH", "SOL", "SUI"],
            "asset_entity_count": 4,
            "minimum_asset_entity_count_for_market_breadth": 6,
            "breadth_status": "limited",
            "is_market_breadth_sufficient": False,
        }
        assert bundle["latest_quality_flag_breakdown"] == {
            "ok": 0,
            "partial": 0,
            "fallback": 0,
            "stale": 0,
            "unknown": 0,
        }
        assert bundle["latest_quality_ready_ratio"] == 0.0
        assert bundle["raw_latest_quality_flag_breakdown"] == {
            "ok": 110,
            "partial": 0,
            "fallback": 0,
            "stale": 0,
            "unknown": 0,
        }
        assert bundle["raw_latest_quality_ready_ratio"] == 1.0
        assert bundle["source_health_summary"]["ready_source_count"] == 8
        assert bundle["source_health_summary"]["problem_source_count"] == 0
        assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
        assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 8
        assert len(bundle["source_health"]) == 8
        assert bundle["venue_coverage_summary"]["complete_source_count"] == 8
        assert bundle["venue_coverage_summary"]["partial_source_count"] == 0
        assert bundle["venue_coverage_summary"]["missing_identity_source_count"] == 0
        assert bundle["venue_coverage_summary"]["observed_venues"] == [
            "Deribit",
            "OKX",
            "Binance",
        ]
        assert "options_entity_coverage_incomplete" in bundle["data_quality_flags"]
        assert "options_factor_coverage_incomplete" in bundle["data_quality_flags"]
        assert "options_configured_market_breadth_limited" in bundle["data_quality_flags"]
        assert "options_source_not_ready_present" not in bundle["data_quality_flags"]
        assert "options_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
        assert "options_context_empty" in bundle["data_quality_flags"]
        assert any(
            "没有任何可直接给 AI 使用的期权证据" in note
            for note in bundle["quality_notes"]
        )
        assert any(
            "默认资产宇宙只覆盖 4 个资产" in note
            for note in bundle["quality_notes"]
        )

        service.close()


def test_load_latest_context_bundle_treats_factor_filtered_options_scope_as_filtered(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_bundle_factor_filtered.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        bundle = service.load_latest_context_bundle(
            factor_ids=["options_atm_iv_30d"],
        )

        assert bundle["configured_universe_summary"]["scope_kind"] == "filtered"
        assert bundle["configured_universe_summary"]["breadth_status"] == "filtered"
        assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is None
        assert "options_configured_market_breadth_limited" not in bundle["data_quality_flags"]

        service.close()


def test_load_latest_context_bundle_treats_full_source_set_as_default_scope(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_bundle_full_sources.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        bundle = service.load_latest_context_bundle(
            source_names=[
                "vol_surface",
                "relative_value",
                "strike_concentration",
                "gamma_exposure",
                "flow_activity",
                "expiry_structure",
                "hedge_pressure",
                "positioning",
            ],
        )

        assert bundle["configured_universe_summary"]["scope_kind"] == "default"
        assert bundle["configured_universe_summary"]["breadth_status"] == "limited"
        assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is False
        assert "options_configured_market_breadth_limited" in bundle["data_quality_flags"]

        service.close()


def test_build_scheduler_registers_all_enabled_jobs(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            db=DBManager(str(tmp_path / "options_scheduler.sqlite"))
        )
        scheduler = service.build_scheduler(interval="1h", lookback_hours=24)

        assert isinstance(scheduler, BlockingScheduler)
        assert len(scheduler.get_jobs()) == 8
        service.close()


def test_collect_once_records_collection_runs_and_coverage(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_coverage.sqlite")),
        )
        service.init_storage()

        service.collect_once(interval="1h", lookback_hours=24)

        run_count = service.db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM collection_runs
            WHERE module_name = 'options_data'
            """
        )["count"]
        coverage = service.load_source_coverage(entity_keys=["BTC", "ETH"])
        coverage_map = {
            row["source_name"]: row
            for row in coverage["sources"]
        }

        assert run_count == 8
        assert coverage["source_count"] == 8
        assert coverage["stale_source_count"] == 0
        assert coverage["ready_source_count"] == 8
        assert coverage["problem_source_count"] == 0
        assert coverage["ready_for_ai_source_count"] == 8
        assert coverage["not_ready_for_ai_source_count"] == 0
        assert coverage["total_latest_point_count"] == 110
        assert coverage_map["vol_surface"]["expected_factor_count"] == 5
        assert coverage_map["relative_value"]["expected_factor_count"] == 4
        assert coverage_map["strike_concentration"]["expected_factor_count"] == 6
        assert coverage_map["strike_concentration"]["latest_point_count"] == 12
        assert coverage_map["gamma_exposure"]["expected_factor_count"] == 7
        assert coverage_map["gamma_exposure"]["latest_point_count"] == 14
        assert coverage_map["flow_activity"]["expected_factor_count"] == 7
        assert coverage_map["flow_activity"]["latest_point_count"] == 14
        assert coverage_map["expiry_structure"]["expected_factor_count"] == 7
        assert coverage_map["expiry_structure"]["latest_point_count"] == 14
        assert coverage_map["hedge_pressure"]["expected_factor_count"] == 14
        assert coverage_map["hedge_pressure"]["latest_point_count"] == 28
        assert coverage_map["positioning"]["expected_entity_count"] == 2
        assert coverage_map["positioning"]["latest_point_count"] == 10
        assert coverage_map["vol_surface"]["observed_venues"] == [
            "Deribit",
            "OKX",
            "Binance",
        ]
        assert coverage_map["vol_surface"]["missing_recommended_venues"] == []
        assert coverage_map["vol_surface"]["is_venue_coverage_complete"] is True
        assert coverage_map["vol_surface"]["latest_ok_point_count"] == 10
        assert coverage_map["vol_surface"]["latest_quality_ready_ratio"] == 1.0
        assert coverage_map["vol_surface"]["quality_notes"]
        assert coverage_map["relative_value"]["quality_notes"]
        assert coverage_map["strike_concentration"]["quality_notes"]
        assert coverage_map["gamma_exposure"]["quality_notes"]
        assert coverage_map["flow_activity"]["quality_notes"]
        assert coverage_map["expiry_structure"]["quality_notes"]
        assert coverage_map["hedge_pressure"]["quality_notes"]
        assert all(row["last_run_status"] == "success" for row in coverage["sources"])

        service.close()


def test_options_bundle_marks_incomplete_recommended_venue_coverage(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=PartialVenueSurfaceOptionsClient(),
            db=DBManager(str(tmp_path / "options_partial_venue.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        coverage = service.load_source_coverage(entity_keys=["BTC", "ETH"])
        coverage_map = {
            row["source_name"]: row
            for row in coverage["sources"]
        }
        bundle = service.load_latest_context_bundle(entity_keys=["BTC", "ETH"])
        source_health_map = {
            row["source_name"]: row
            for row in bundle["source_health"]
        }

        assert coverage["ready_source_count"] == 8
        assert coverage["ready_for_ai_source_count"] == 7
        assert coverage["not_ready_for_ai_source_count"] == 1
        assert coverage_map["vol_surface"]["observed_venues"] == ["Deribit"]
        assert coverage_map["vol_surface"]["missing_recommended_venues"] == [
            "OKX",
            "Binance",
        ]
        assert coverage_map["vol_surface"]["is_ready_for_ai"] is False
        assert coverage_map["vol_surface"]["is_venue_coverage_complete"] is False
        assert bundle["source_health_summary"]["ready_source_count"] == 8
        assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 7
        assert bundle["venue_coverage_summary"]["complete_source_count"] == 7
        assert bundle["venue_coverage_summary"]["partial_source_count"] == 1
        assert bundle["venue_coverage_summary"]["missing_identity_source_count"] == 0
        assert bundle["venue_coverage_summary"]["coverage_by_source"]["vol_surface"][
            "missing_recommended_venues"
        ] == ["OKX", "Binance"]
        assert source_health_map["vol_surface"]["observed_venues"] == ["Deribit"]
        assert source_health_map["vol_surface"]["is_ready_for_ai"] is False
        assert "options_recommended_venue_coverage_incomplete" in bundle["data_quality_flags"]
        assert any(
            "vol_surface 缺少 OKX, Binance" in note
            for note in bundle["quality_notes"]
        )

        service.close()


def test_options_bundle_marks_partial_quality_source_not_ai_ready(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=PartialQualitySurfaceOptionsClient(),
            db=DBManager(str(tmp_path / "options_partial_quality.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        coverage = service.load_source_coverage(entity_keys=["BTC", "ETH"])
        coverage_map = {
            row["source_name"]: row
            for row in coverage["sources"]
        }
        bundle = service.load_latest_context_bundle(entity_keys=["BTC", "ETH"])
        source_health_map = {
            row["source_name"]: row
            for row in bundle["source_health"]
        }

        assert coverage["ready_source_count"] == 8
        assert coverage["ready_for_ai_source_count"] == 7
        assert coverage["not_ready_for_ai_source_count"] == 1
        assert coverage_map["vol_surface"]["health_status"] == "ready"
        assert coverage_map["vol_surface"]["is_ready_for_ai"] is False
        assert coverage_map["vol_surface"]["missing_recommended_venues"] == []
        assert coverage_map["vol_surface"]["latest_partial_point_count"] > 0
        assert "partial_points_present" in coverage_map["vol_surface"]["data_quality_flags"]
        assert bundle["source_health_summary"]["ready_source_count"] == 8
        assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 7
        assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 1
        assert source_health_map["vol_surface"]["is_ready_for_ai"] is False
        assert bundle["row_count"] == 100
        assert bundle["raw_row_count"] == 110
        assert bundle["ai_excluded_source_names"] == ["vol_surface"]
        assert "options_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
        assert "options_factor_coverage_incomplete" in bundle["data_quality_flags"]
        assert "missing_vol_surface_for_2_assets" in bundle["data_quality_flags"]
        assert bundle["raw_latest_quality_flag_breakdown"]["partial"] == 5
        assert bundle["latest_partial_point_count"] == 0
        assert "vol_surface" not in bundle["sources"]
        assert any(
            "vol_surface" in note and "不适合直接作为 AI 的期权证据" in note
            for note in bundle["quality_notes"]
        )

        service.close()


def test_options_coverage_respects_factor_and_entity_filters(tmp_path):
    with patch.dict("config.settings.OPTIONS_CONFIG", OPTIONS_CONFIG_PATCH, clear=False):
        service = OptionsDataService(
            client=StaticOptionsClient(),
            db=DBManager(str(tmp_path / "options_filtered_coverage.sqlite")),
        )
        service.init_storage()
        service.collect_once(interval="1h", lookback_hours=24)

        coverage = service.load_source_coverage(
            factor_ids=["options_atm_iv_30d"],
            entity_keys=["BTC"],
        )

        assert coverage["source_count"] == 1
        row = coverage["sources"][0]
        assert row["source_name"] == "vol_surface"
        assert row["expected_factor_count"] == 1
        assert row["latest_factor_count"] == 1
        assert row["expected_entity_count"] == 1
        assert row["latest_entity_count"] == 1
        assert row["latest_point_count"] == 1
        assert row["latest_ok_point_count"] == 1
        assert row["latest_quality_ready_ratio"] == 1.0

        service.close()
