"""Regression coverage for domain health declarations and access policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from api.routers.status import DOMAIN_REGISTRY
from core.feature_flags import DEFAULT_DISABLED_DOMAINS, FeatureFlags


class TestStatusRegistry(unittest.TestCase):
    def test_registry_uses_authoritative_domain_tables(self):
        self.assertEqual(
            DOMAIN_REGISTRY["stablecoin_flow"]["table"],
            "stablecoin_chain_flows",
        )
        self.assertEqual(DOMAIN_REGISTRY["mev"]["table"], "mev_blocks")
        self.assertEqual(DOMAIN_REGISTRY["asset_metadata"]["table"], "asset_metadata_snapshots")
        self.assertEqual(DOMAIN_REGISTRY["bitcoin_onchain_history"]["table"], "bitcoin_onchain_history")
        self.assertEqual(DOMAIN_REGISTRY["ethereum_network"]["table"], "ethereum_network_snapshots")
        self.assertEqual(DOMAIN_REGISTRY["okx_derivatives_history"]["table"], "okx_derivatives_raw")
        self.assertEqual(DOMAIN_REGISTRY["okx_market_history"]["table"], "okx_market_candle_history_raw")
        self.assertEqual(DOMAIN_REGISTRY["okx_funding_history"]["table"], "okx_funding_history_raw")
        self.assertEqual(DOMAIN_REGISTRY["deribit_funding_history"]["table"], "deribit_funding_history_raw")
        self.assertEqual(DOMAIN_REGISTRY["multi_exchange_quotes"]["table"], "public_exchange_quote_snapshots")

    def test_unlicensed_or_unimplemented_domains_are_disabled_by_default(self):
        for domain in DEFAULT_DISABLED_DOMAINS:
            with self.subTest(domain=domain), patch.dict(
                "os.environ", {f"FF_{domain.upper()}_ENABLED": ""}, clear=False
            ):
                # Empty is not an enabled override; remove it after entering the patch.
                import os
                os.environ.pop(f"FF_{domain.upper()}_ENABLED", None)
                self.assertFalse(FeatureFlags().is_enabled(domain))

    def test_operator_can_explicitly_enable_disabled_domain(self):
        with patch.dict("os.environ", {"FF_ETF_FLOW_ENABLED": "1"}, clear=False):
            self.assertTrue(FeatureFlags().is_enabled("etf_flow"))

    def test_public_exchange_domain_remains_enabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("FF_EXCHANGE_ENABLED", None)
            self.assertTrue(FeatureFlags().is_enabled("exchange"))
