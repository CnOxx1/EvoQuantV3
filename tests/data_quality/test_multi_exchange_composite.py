"""Regression tests for source-aware composite candle quality gating."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.build_multi_exchange_composite_candles import evaluate_bucket

def candle(exchange: str, close: float, valid: bool = True) -> dict:
    return {"exchange": exchange, "open": 100.0, "high": max(101.0, close + 1.0) if valid else 99.0, "low": min(99.0, close - 1.0), "close": close, "volume": 10.0, "payload_json": "{}"}

class TestMultiExchangeComposite(unittest.TestCase):
    def test_two_consistent_sources_create_accepted_bucket(self):
        result = evaluate_bucket([candle("coinbase", 100.0), candle("kraken", 100.4)], 2, 100)
        self.assertTrue(result["accepted"]); self.assertEqual(len(result["included"]), 2)

    def test_outlier_source_is_excluded_when_two_sources_agree(self):
        result = evaluate_bucket([candle("coinbase", 100.0), candle("kraken", 100.2), candle("bitstamp", 112.0)], 2, 100)
        self.assertTrue(result["accepted"]); self.assertEqual({item["exchange"] for item in result["included"]}, {"coinbase", "kraken"})

    def test_divergent_two_source_bucket_is_rejected(self):
        result = evaluate_bucket([candle("coinbase", 100.0), candle("kraken", 104.0)], 2, 100)
        self.assertFalse(result["accepted"]); self.assertEqual(result["reason"], "insufficient_consistent_sources")

if __name__ == "__main__": unittest.main()
