"""Regression tests for raw-data continuity auditing and recovery queue state."""
from __future__ import annotations
import sqlite3, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import audit_data_coverage_and_queue_backfills as audit

class TestDataCoverageAudit(unittest.TestCase):
    def test_audit_reports_time_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "raw.db"
            conn = sqlite3.connect(database)
            conn.execute("CREATE TABLE raw (instrument TEXT, observed_ms INTEGER)")
            conn.executemany("INSERT INTO raw VALUES (?,?)", [("BTC", 0), ("BTC", 1_000), ("BTC", 4_000)])
            conn.commit(); conn.close()
            result = audit.audit_spec({"dataset": "test", "db": database, "table": "raw", "partition": "instrument", "time": "observed_ms", "interval_ms": 1_000, "command": "rerun"})
            self.assertEqual(result["partitions"][0]["gap_count"], 1)
            self.assertEqual(result["gaps"][0]["gap_ms"], 3_000)

    def test_queue_preserves_confirmed_source_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            original = audit.MARKET_DB
            try:
                audit.MARKET_DB = Path(directory) / "market.db"
                result = [{"dataset": "bitcoin", "gaps": [{"partition": "metric", "after": 1, "before": 3, "gap_ms": 2}], "recommended_command": "rerun"}]
                audit.queue_tasks(result)
                conn = sqlite3.connect(audit.MARKET_DB)
                conn.execute("UPDATE data_backfill_tasks SET status='source_omission'")
                conn.commit(); conn.close()
                audit.queue_tasks(result)
                conn = sqlite3.connect(audit.MARKET_DB)
                status = conn.execute("SELECT status FROM data_backfill_tasks").fetchone()[0]
                conn.close()
                self.assertEqual(status, "source_omission")
            finally:
                audit.MARKET_DB = original

if __name__ == "__main__": unittest.main()
