"""Regression coverage for Regime's merged-kline symbol contract."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from logic_layer.regime_detection.service import RegimeDetectionService


class TestRegimeSymbolContract(unittest.TestCase):
    def test_asset_codes_are_normalized_to_merged_kline_symbols(self):
        self.assertEqual(RegimeDetectionService._storage_symbol("BTC"), "BTC/USDT")
        self.assertEqual(RegimeDetectionService._storage_symbol("ETH"), "ETH/USDT")
        self.assertEqual(RegimeDetectionService._storage_symbol("BTC/USDT"), "BTC/USDT")

    def test_legacy_naive_regime_timestamps_are_treated_as_utc(self):
        now = datetime(2026, 8, 22, 4, 30, tzinfo=timezone.utc)
        self.assertEqual(RegimeDetectionService._duration_hours("2026-08-22T03:00:00", now), 1)
        self.assertEqual(RegimeDetectionService._duration_hours("2026-08-22T03:00:00+00:00", now), 1)
