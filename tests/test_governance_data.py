"""Unit tests for GovernanceDataService."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.db_manager import DBManager
from data_layer.governance_data.service import GovernanceDataService


class StaticGovernanceClient:
    """Static mock client returning fake proposals and votes."""

    TRACKED_SPACES = ["aave.eth"]
    tally_key = ""

    def fetch_snapshot_proposals(self, space, state="active", first=10):
        if state == "active":
            return [
                {
                    "id": "proposal_001",
                    "title": "Increase staking rewards",
                    "state": "active",
                    "scores": [150000.0, 30000.0],
                    "scores_total": 180000.0,
                    "quorum": 100000,
                    "start": 1715000000,
                    "end": 1715600000,
                },
            ]
        return []

    def fetch_snapshot_votes(self, proposal_id, first=100):
        return [
            {"voter": "0xwhale1", "vp": 80000.0, "choice": "1",
             "created": 1715100000},
            {"voter": "0xuser2", "vp": 5000.0, "choice": "1",
             "created": 1715200000},
            {"voter": "0xuser3", "vp": 3000.0, "choice": "2",
             "created": 1715300000},
        ]

    def fetch_tally_proposals(self, governor_id, first=10):
        return []

    def fetch_tally_votes(self, proposal_id, first=100):
        return []

    def close(self):
        pass


def test_init_storage_creates_governance_tables(tmp_path):
    db = DBManager(str(tmp_path / "gov.sqlite"))
    service = GovernanceDataService(client=StaticGovernanceClient(), db=db)
    service.init_storage()

    tables = {
        row["name"]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "governance_proposals" in tables
    assert "governance_votes" in tables
    assert "governance_activity" in tables


def test_collect_once_stores_proposals_and_votes(tmp_path):
    db = DBManager(str(tmp_path / "gov_collect.sqlite"))
    service = GovernanceDataService(client=StaticGovernanceClient(), db=db)
    service.init_storage()
    service.collect_once()

    proposal_count = db.conn.execute(
        "SELECT COUNT(*) FROM governance_proposals"
    ).fetchone()[0]
    vote_count = db.conn.execute(
        "SELECT COUNT(*) FROM governance_votes"
    ).fetchone()[0]
    assert proposal_count >= 1
    assert vote_count >= 3


def test_collect_once_computes_activity_metrics(tmp_path):
    db = DBManager(str(tmp_path / "gov_activity.sqlite"))
    service = GovernanceDataService(client=StaticGovernanceClient(), db=db)
    service.init_storage()
    service.collect_once()

    activity_count = db.conn.execute(
        "SELECT COUNT(*) FROM governance_activity"
    ).fetchone()[0]
    assert activity_count >= 1

    row = db.conn.execute(
        "SELECT proposals_active, whale_vote_pct "
        "FROM governance_activity LIMIT 1"
    ).fetchone()
    assert row[0] == 1
    assert row[1] > 0


def test_load_latest_context_bundle_returns_governance_signals(tmp_path):
    db = DBManager(str(tmp_path / "gov_bundle.sqlite"))
    service = GovernanceDataService(client=StaticGovernanceClient(), db=db)
    service.init_storage()
    service.collect_once()

    bundle = service.load_latest_context_bundle()
    assert bundle["status"] == "ready"
    assert "market_signals" in bundle
    assert bundle["market_signals"]["active_proposal_count"] == 1
    assert "active_proposals" in bundle
    assert bundle["active_proposals"][0]["title"] == "Increase staking rewards"
