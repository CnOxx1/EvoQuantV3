"""Regression tests for public miner metrics larger than SQLite INTEGER."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_layer.miner_data.service import MinerDataService
from database.db_manager import DBManager


class _LargeValueClient:
    def fetch_mining_stats(self):
        return {
            "hashrate": 869082239846352759570,
            "difficulty": 127479855693691.4,
            "block_reward": 3.125,
        }

    def fetch_miner_outflows(self):
        return {}

    def fetch_hashrate_history(self):
        return [{
            "timestamp": "2026-08-22 03:31:57",
            "avgHashrate": 869082239846352759570,
            "difficulty": 127479855693691.4,
        }]

    def close(self):
        return None


class TestMinerNumericNormalization(unittest.TestCase):
    def test_large_public_numeric_fields_are_saved_as_sqlite_reals(self):
        with tempfile.TemporaryDirectory() as directory:
            db = DBManager(str(Path(directory) / "miner.sqlite"))
            service = MinerDataService(client=_LargeValueClient(), db=db)
            try:
                service.init_storage()
                service.collect_once()
                metrics = db.conn.execute(
                    "SELECT hashrate, difficulty FROM miner_metrics"
                ).fetchone()
                history = db.conn.execute(
                    "SELECT hashrate, difficulty FROM hashrate_history"
                ).fetchone()
                self.assertIsNotNone(metrics)
                self.assertIsNotNone(history)
                self.assertGreater(metrics[0], 0.0)
                self.assertGreater(history[0], 0.0)
            finally:
                service.close()
                db.close()
