import json
import urllib.error
import sys
import threading
from datetime import timedelta, timezone
from io import BytesIO
from math import log1p
from pathlib import Path
from unittest.mock import patch

import pytest
from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
from data_layer.alternative_data import sources as alternative_sources
from data_layer.alternative_data.client import AlternativeDataClient, GitHubRateLimitExceededError
from data_layer.alternative_data.google_trends import GoogleTrendsCollector
from data_layer.alternative_data.github_activity import GitHubActivityCollector
from data_layer.alternative_data.models import AlternativeTimeSeriesPoint, utc_now_naive
from data_layer.alternative_data.service import AlternativeDataService
from data_layer.alternative_data.sources import (
    GITHUB_REPO_GROUPS_FILE,
    GOOGLE_TRENDS_QUERY_GROUPS_FILE,
    REGISTRY_DIR,
    STABLECOIN_ASSETS_FILE,
    load_alternative_factors,
    load_alternative_sources,
    load_github_repo_groups,
    load_google_trends_query_groups,
    load_stablecoin_assets,
)
from data_layer.alternative_data.stablecoin_supply import StablecoinSupplyCollector


class StaticAlternativeClient:
    def fetch_github_commits(self, owner, repo, since, until=None, per_page=100, max_pages=10):
        window = (until or utc_now_naive()) - since
        is_long_window = window >= timedelta(days=2)
        repo_name = f"{owner}/{repo}"
        if is_long_window:
            return {
                "bitcoin/bitcoin": [
                    self._commit("alice"),
                    self._commit("bob"),
                    self._commit("alice"),
                ],
                "bitcoin-core/secp256k1": [
                    self._commit("carol"),
                    self._commit("dave"),
                ],
                "bitcoin/bips": [
                    self._commit("erin"),
                ],
            }.get(repo_name, [])
        return {
            "bitcoin/bitcoin": [
                self._commit("alice"),
                self._commit("bob"),
            ],
            "bitcoin-core/secp256k1": [
                self._commit("carol"),
            ],
            "bitcoin/bips": [],
        }.get(repo_name, [])

    def search_github_pull_request_count(self, owner, repo, qualifier, since):
        repo_name = f"{owner}/{repo}"
        opened = {
            "bitcoin/bitcoin": 4,
            "bitcoin-core/secp256k1": 1,
            "bitcoin/bips": 0,
        }
        merged = {
            "bitcoin/bitcoin": 2,
            "bitcoin-core/secp256k1": 1,
            "bitcoin/bips": 1,
        }
        if qualifier == "created":
            return opened.get(repo_name, 0)
        return merged.get(repo_name, 0)

    def fetch_github_releases(self, owner, repo, per_page=100, max_pages=5):
        now = utc_now_naive()
        repo_name = f"{owner}/{repo}"
        payload = {
            "bitcoin/bitcoin": [
                {"published_at": (now - timedelta(days=10)).isoformat()},
                {"published_at": (now - timedelta(days=40)).isoformat()},
            ],
            "bitcoin-core/secp256k1": [
                {"published_at": (now - timedelta(days=3)).isoformat()},
            ],
            "bitcoin/bips": [],
        }
        return payload.get(repo_name, [])

    def fetch_stablecoin_assets(self):
        return [
            {
                "id": 1,
                "symbol": "USDT",
                "circulating": 1000.0,
                "chainCirculating": {
                    "Ethereum": 650.0,
                    "Tron": 350.0,
                },
                "timestamp": utc_now_naive().isoformat(),
            },
            {
                "id": 2,
                "symbol": "USDC",
                "circulating": 500.0,
                "chainCirculating": {
                    "Ethereum": 300.0,
                    "Solana": 200.0,
                },
                "timestamp": utc_now_naive().isoformat(),
            },
        ]

    def fetch_stablecoin_history(self, asset_id):
        now = utc_now_naive()
        payload = {
            1: [
                {"timestamp": (now - timedelta(days=7)).isoformat(), "supply": 700.0},
                {"timestamp": (now - timedelta(days=2)).isoformat(), "supply": 850.0},
                {"timestamp": (now - timedelta(days=1)).isoformat(), "supply": 900.0},
            ],
            2: [
                {"timestamp": (now - timedelta(days=7)).isoformat(), "supply": 350.0},
                {"timestamp": (now - timedelta(days=1)).isoformat(), "supply": 450.0},
            ],
        }
        return payload.get(asset_id, [])

    def fetch_google_trends_interest(
        self,
        query,
        timeframe,
        geo="",
        category=0,
        gprop="",
        hl="en-US",
        tz=0,
    ):
        now = utc_now_naive()
        rows_by_query = {
            "bitcoin": [
                {
                    "timestamp": now - timedelta(days=2),
                    "value": 22.0,
                    "formatted_time": "May 06, 2026",
                    "has_data": True,
                    "is_partial": False,
                },
                {
                    "timestamp": now - timedelta(days=1),
                    "value": 35.0,
                    "formatted_time": "May 07, 2026",
                    "has_data": True,
                    "is_partial": False,
                },
                {
                    "timestamp": now,
                    "value": 48.0,
                    "formatted_time": "May 08, 2026",
                    "has_data": True,
                    "is_partial": False,
                },
            ],
            "crypto": [
                {
                    "timestamp": now - timedelta(days=2),
                    "value": 40.0,
                    "formatted_time": "May 06, 2026",
                    "has_data": True,
                    "is_partial": False,
                },
                {
                    "timestamp": now - timedelta(days=1),
                    "value": 55.0,
                    "formatted_time": "May 07, 2026",
                    "has_data": True,
                    "is_partial": False,
                },
                {
                    "timestamp": now,
                    "value": 62.0,
                    "formatted_time": "May 08, 2026",
                    "has_data": True,
                    "is_partial": True,
                },
            ],
        }
        return rows_by_query.get(query, [])

    def fetch_google_trends_related_queries(
        self,
        query,
        timeframe,
        geo="",
        category=0,
        gprop="",
        hl="en-US",
        tz=0,
    ):
        return {
            "top": [
                {"title": f"{query} price", "value": 100.0, "formatted_value": "100", "is_breakout": False},
                {"title": f"{query} etf", "value": 80.0, "formatted_value": "80", "is_breakout": False},
            ],
            "rising": [
                {"title": f"{query} breakout", "value": 5000.0, "formatted_value": "Breakout", "is_breakout": True},
                {"title": f"{query} outlook", "value": 240.0, "formatted_value": "240", "is_breakout": False},
            ],
        }

    def fetch_google_trends_related_topics(
        self,
        query,
        timeframe,
        geo="",
        category=0,
        gprop="",
        hl="en-US",
        tz=0,
    ):
        return {
            "top": [
                {"title": f"{query} network", "value": 90.0, "formatted_value": "90", "is_breakout": False},
            ],
            "rising": [
                {"title": f"{query} ecosystem", "value": 170.0, "formatted_value": "170", "is_breakout": False},
                {"title": f"{query} mania", "value": 5000.0, "formatted_value": "Breakout", "is_breakout": True},
            ],
        }

    def fetch_stablecoin_chain_history(self, asset_id):
        now = utc_now_naive()
        payload = {
            1: [
                {
                    "timestamp": (now - timedelta(days=7)).isoformat(),
                    "chains": [
                        {"chain": "Ethereum", "supply": 420.0},
                        {"chain": "Tron", "supply": 280.0},
                    ],
                },
                {
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "chains": [
                        {"chain": "Ethereum", "supply": 540.0},
                        {"chain": "Tron", "supply": 360.0},
                    ],
                },
            ],
            2: [
                {
                    "timestamp": (now - timedelta(days=7)).isoformat(),
                    "chains": [
                        {"chain": "Ethereum", "supply": 210.0},
                        {"chain": "Solana", "supply": 140.0},
                    ],
                }
            ],
        }
        return payload.get(asset_id, [])

    @staticmethod
    def _commit(actor: str) -> dict:
        return {
            "author": {"login": actor},
            "commit": {
                "author": {
                    "name": actor,
                    "email": f"{actor}@example.com",
                }
            },
        }


class RateLimitedAlternativeClient:
    def __init__(self):
        self.commit_calls = 0

    def fetch_github_commits(self, owner, repo, since, until=None, per_page=100, max_pages=10):
        self.commit_calls += 1
        raise GitHubRateLimitExceededError("GitHub API rate limit exceeded")

    def search_github_pull_request_count(self, owner, repo, qualifier, since):
        raise AssertionError("rate limit 后不应继续请求 PR search")

    def fetch_github_releases(self, owner, repo, per_page=100, max_pages=5):
        raise AssertionError("rate limit 后不应继续请求 releases")


def test_alternative_timeseries_point_normalizes_dimensions_and_timestamps():
    point = AlternativeTimeSeriesPoint(
        factor_id="github_commit_count_1d",
        category="developer_activity",
        factor_type="rolling_count",
        entity_type="repo_group",
        entity_key="BTC",
        interval="1d",
        observation_time=utc_now_naive().replace(tzinfo=timezone.utc),
        value=3,
        unit="count",
        dimensions_json={"repo_group_version": "v1", "repo_count": 3},
        config_version="v1",
        source_name="github",
        source_symbol="repo_group:BTC",
    )

    assert point.observation_time.tzinfo is None
    assert point.dimensions_key == "repo_count=3|repo_group_version=v1"
    assert point.history_db_tuple()[11] == "{\"repo_count\":3,\"repo_group_version\":\"v1\"}"


def test_init_storage_creates_alternative_tables_and_catalog(tmp_path):
    service = AlternativeDataService(db=DBManager(str(tmp_path / "alternative.sqlite")))
    service.init_storage()

    tables = {
        row["name"]
        for row in service.db.fetch_all(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'alternative_%'
            """
        )
    }
    factor_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("github_commit_count_1d",),
    )
    trends_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_search_interest",),
    )
    shock_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_attention_shock_7d",),
    )

    assert "alternative_factor_catalog" in tables
    assert "alternative_timeseries" in tables
    assert factor_row["source_name"] == "github"
    assert factor_row["entity_type"] == "repo_group"
    assert factor_row["enabled"] == 1
    assert trends_row["source_name"] == "google_trends"
    assert trends_row["entity_type"] == "query_group"
    assert trends_row["enabled"] == 1
    assert shock_row["source_name"] == "google_trends"
    assert shock_row["entity_type"] == "query_group"
    assert shock_row["enabled"] == 1
    related_query_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_related_query_breakout_count",),
    )
    related_topic_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_related_topic_rising_max_score",),
    )
    cross_query_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_cross_query_zscore",),
    )
    narrative_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("google_trends_narrative_concentration",),
    )
    bridge_row = service.db.fetch_one(
        """
        SELECT source_name, entity_type, enabled
        FROM alternative_factor_catalog
        WHERE factor_id = ?
        """,
        ("stablecoin_bridge_inflow",),
    )
    assert related_query_row["enabled"] == 1
    assert related_topic_row["enabled"] == 1
    assert cross_query_row["enabled"] == 1
    assert narrative_row["enabled"] == 1
    assert bridge_row["enabled"] == 1

    service.close()


def test_registry_files_are_externalized_and_loaded():
    assert (REGISTRY_DIR / GITHUB_REPO_GROUPS_FILE).exists() is True
    assert (REGISTRY_DIR / STABLECOIN_ASSETS_FILE).exists() is True
    assert (REGISTRY_DIR / GOOGLE_TRENDS_QUERY_GROUPS_FILE).exists() is True

    sources = load_alternative_sources()
    source_map = {
        row["source_name"]: row
        for row in sources
    }

    assert source_map["github"]["registry_file"] == GITHUB_REPO_GROUPS_FILE
    assert source_map["github"]["registry_record_count"] >= 1
    assert len(str(source_map["github"]["registry_version"])) == 12
    assert any(group["entity_key"] == "BTC" for group in load_github_repo_groups())
    assert any(asset["entity_key"] == "USDT" for asset in load_stablecoin_assets())
    assert any(
        query_group["entity_key"] == "bitcoin"
        for query_group in load_google_trends_query_groups()
    )


def test_registry_auto_reload_refreshes_metadata_and_dynamic_factors(monkeypatch, tmp_path):
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()

    (registry_dir / GITHUB_REPO_GROUPS_FILE).write_text(
        json.dumps(
            [
                {
                    "entity_key": "BTC",
                    "name": "Bitcoin Core",
                    "asset": "BTC",
                    "repos": ["bitcoin/bitcoin"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (registry_dir / STABLECOIN_ASSETS_FILE).write_text(
        json.dumps(
            [
                {
                    "entity_key": "USDT",
                    "name": "Tether USD",
                    "aliases": ["USDT"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (registry_dir / GOOGLE_TRENDS_QUERY_GROUPS_FILE).write_text(
        json.dumps(
            [
                {
                    "entity_key": "bitcoin",
                    "name": "Bitcoin Search Interest",
                    "query": "bitcoin",
                    "group_type": "asset",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(alternative_sources, "REGISTRY_DIR", registry_dir)

    github_before = load_alternative_sources(
        source_names=["github"],
        force_reload=True,
    )[0]
    stablecoin_factors_before = load_alternative_factors(
        enabled_only=False,
        source_names=["stablecoin"],
    )

    assert github_before["registry_record_count"] == 1
    assert stablecoin_factors_before[0].raw_meta["tracked_assets"] == ["USDT"]

    (registry_dir / GITHUB_REPO_GROUPS_FILE).write_text(
        json.dumps(
            [
                {
                    "entity_key": "BTC",
                    "name": "Bitcoin Core",
                    "asset": "BTC",
                    "repos": ["bitcoin/bitcoin"],
                },
                {
                    "entity_key": "ETH",
                    "name": "Ethereum Core",
                    "asset": "ETH",
                    "repos": ["ethereum/go-ethereum"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (registry_dir / STABLECOIN_ASSETS_FILE).write_text(
        json.dumps(
            [
                {
                    "entity_key": "USDT",
                    "name": "Tether USD",
                    "aliases": ["USDT"],
                },
                {
                    "entity_key": "USDC",
                    "name": "USD Coin",
                    "aliases": ["USDC"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    github_after = load_alternative_sources(source_names=["github"])[0]
    stablecoin_factors_after = load_alternative_factors(
        enabled_only=False,
        source_names=["stablecoin"],
    )

    assert github_after["registry_record_count"] == 2
    assert github_after["registry_version"] != github_before["registry_version"]
    assert {row["entity_key"] for row in load_github_repo_groups()} == {"BTC", "ETH"}
    assert load_stablecoin_assets()[1]["entity_key"] == "USDC"
    assert stablecoin_factors_after[0].raw_meta["tracked_assets"] == ["USDT", "USDC"]


def test_github_collector_aggregates_repo_group_metrics(tmp_path):
    db = DBManager(str(tmp_path / "github.sqlite"))
    db.init_tables()
    collector = GitHubActivityCollector(StaticAlternativeClient(), db)

    points = collector.collect(entity_keys=["BTC"])
    metrics = {
        point.factor_id: point.value
        for point in points
    }

    assert metrics["github_commit_count_1d"] == 3.0
    assert metrics["github_commit_count_7d"] == 6.0
    assert metrics["github_active_contributors_7d"] == 5.0
    assert metrics["github_opened_pr_count_7d"] == 5.0
    assert metrics["github_merged_pr_count_7d"] == 4.0
    assert metrics["github_release_count_30d"] == 2.0

    latest_count = db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ? AND entity_key = ?
        """,
        ("github", "BTC"),
    )
    assert latest_count["count"] == 6

    db.close()


def test_github_client_raises_rate_limit_without_retry(monkeypatch):
    client = AlternativeDataClient()
    calls = {"count": 0}

    def fake_urlopen(request, timeout=0):
        calls["count"] += 1
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "rate limit exceeded",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1780000000"},
            BytesIO(b'{"message":"API rate limit exceeded"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(GitHubRateLimitExceededError):
        client.fetch_github_commits(
            owner="bitcoin",
            repo="bitcoin",
            since=utc_now_naive() - timedelta(days=1),
            until=utc_now_naive(),
        )

    assert calls["count"] == 1


def test_github_collector_stops_current_cycle_after_rate_limit(tmp_path):
    db = DBManager(str(tmp_path / "github_rate_limit.sqlite"))
    db.init_tables()
    client = RateLimitedAlternativeClient()
    collector = GitHubActivityCollector(client, db)

    points = collector.collect(entity_keys=["BTC"])

    assert points == []
    assert client.commit_calls == 1
    db.close()


def test_stablecoin_collector_computes_supply_and_chain_metrics(tmp_path):
    db = DBManager(str(tmp_path / "stablecoin.sqlite"))
    db.init_tables()
    collector = StablecoinSupplyCollector(StaticAlternativeClient(), db)

    points = collector.collect(entity_keys=["USDT"])
    by_identity = {
        (point.factor_id, point.entity_key): point.value
        for point in points
    }

    assert by_identity[("stablecoin_total_supply", "USDT")] == 1000.0
    assert by_identity[("stablecoin_net_supply_change_24h", "USDT")] == 100.0
    assert by_identity[("stablecoin_net_supply_change_7d", "USDT")] == 300.0
    assert by_identity[("stablecoin_chain_supply", "USDT:ethereum")] == 650.0
    assert by_identity[("stablecoin_chain_supply", "USDT:tron")] == 350.0
    assert by_identity[("stablecoin_chain_supply_share", "USDT:ethereum")] == 0.65
    assert by_identity[("stablecoin_chain_supply_share", "USDT:tron")] == 0.35
    assert by_identity[("stablecoin_mint_volume", "USDT")] == 100.0
    assert by_identity[("stablecoin_burn_volume", "USDT")] == 0.0
    assert by_identity[("stablecoin_bridge_inflow", "USDT:ethereum")] == 10.0
    assert by_identity[("stablecoin_bridge_outflow", "USDT:tron")] == 10.0

    latest_count = db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ? AND (
            entity_key = ? OR entity_key = ? OR entity_key = ?
        )
        """,
        ("stablecoin", "USDT", "USDT:ethereum", "USDT:tron"),
    )
    assert latest_count["count"] == 13

    db.close()


def test_stablecoin_bootstrap_includes_chain_history(tmp_path):
    db = DBManager(str(tmp_path / "stablecoin_bootstrap.sqlite"))
    db.init_tables()
    collector = StablecoinSupplyCollector(StaticAlternativeClient(), db)

    points = collector.bootstrap_history(entity_keys=["USDT"])
    by_identity = {
        (point.factor_id, point.entity_key, point.interval, point.observation_time.date().isoformat()): point.value
        for point in points
    }

    assert by_identity[("stablecoin_chain_supply", "USDT:ethereum", "1d", (utc_now_naive() - timedelta(days=1)).date().isoformat())] == 540.0
    assert by_identity[("stablecoin_chain_supply_share", "USDT:tron", "1d", (utc_now_naive() - timedelta(days=7)).date().isoformat())] == 0.4
    assert by_identity[("stablecoin_mint_volume", "USDT", "1d", (utc_now_naive() - timedelta(days=2)).date().isoformat())] == 150.0
    assert by_identity[("stablecoin_bridge_inflow", "USDT:ethereum", "1d", utc_now_naive().date().isoformat())] == 10.0
    assert by_identity[("stablecoin_bridge_outflow", "USDT:tron", "1d", utc_now_naive().date().isoformat())] == 10.0

    db.close()


def test_stablecoin_chain_history_normalization_skips_generic_container_keys():
    base_now = utc_now_naive()
    payload = {
        "history": [
            {
                "timestamp": (base_now - timedelta(days=1)).isoformat(),
                "supply": 900.0,
            },
            {
                "timestamp": base_now.isoformat(),
                "supply": 1000.0,
            },
        ],
        "Ethereum": [
            {
                "timestamp": (base_now - timedelta(days=1)).isoformat(),
                "supply": 540.0,
            },
            {
                "timestamp": base_now.isoformat(),
                "supply": 600.0,
            },
        ],
        "Tron": [
            {
                "timestamp": (base_now - timedelta(days=1)).isoformat(),
                "supply": 360.0,
            },
            {
                "timestamp": base_now.isoformat(),
                "supply": 400.0,
            },
        ],
    }

    snapshots = AlternativeDataClient._normalize_stablecoin_chain_history(payload)

    assert len(snapshots) == 2
    assert {
        chain["chain"]
        for chain in snapshots[-1]["chains"]
    } == {"Ethereum", "Tron"}
    assert all(
        chain["chain"] not in {"history", "data"}
        for snapshot in snapshots
        for chain in snapshot["chains"]
    )


def test_google_trends_collector_collects_query_group_interest(tmp_path):
    db = DBManager(str(tmp_path / "google_trends.sqlite"))
    db.init_tables()
    collector = GoogleTrendsCollector(StaticAlternativeClient(), db)

    points = collector.collect(entity_keys=["bitcoin", "crypto"])
    by_identity = {
        (point.factor_id, point.entity_key, point.observation_time.date().isoformat()): (
            point.value,
            point.quality_flag,
            point.interval,
        )
        for point in points
    }

    assert by_identity[("google_trends_search_interest", "bitcoin", utc_now_naive().date().isoformat())][0] == 48.0
    assert by_identity[("google_trends_search_interest", "bitcoin", utc_now_naive().date().isoformat())][2] == "1d"
    assert by_identity[("google_trends_search_interest", "crypto", utc_now_naive().date().isoformat())][0] == 62.0
    assert by_identity[("google_trends_search_interest", "crypto", utc_now_naive().date().isoformat())][1] == "partial"
    assert round(
        by_identity[("google_trends_attention_shock_7d", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == round((48.0 - 28.5) / 28.5, 6)
    assert round(
        by_identity[("google_trends_attention_shock_7d", "crypto", utc_now_naive().date().isoformat())][0],
        6,
    ) == round((62.0 - 47.5) / 47.5, 6)
    assert by_identity[("google_trends_attention_shock_7d", "crypto", utc_now_naive().date().isoformat())][1] == "partial"
    assert round(
        by_identity[("google_trends_cross_query_zscore", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == -1.0
    assert round(
        by_identity[("google_trends_cross_query_zscore", "crypto", utc_now_naive().date().isoformat())][0],
        6,
    ) == 1.0
    assert by_identity[("google_trends_cross_query_percentile", "bitcoin", utc_now_naive().date().isoformat())][0] == 0.0
    assert by_identity[("google_trends_cross_query_percentile", "crypto", utc_now_naive().date().isoformat())][0] == 1.0
    assert by_identity[("google_trends_related_query_breakout_count", "bitcoin", utc_now_naive().date().isoformat())][0] == 1.0
    assert by_identity[("google_trends_related_query_rising_max_score", "bitcoin", utc_now_naive().date().isoformat())][0] == 5000.0
    assert by_identity[("google_trends_related_topic_breakout_count", "crypto", utc_now_naive().date().isoformat())][0] == 1.0
    assert by_identity[("google_trends_related_topic_rising_max_score", "crypto", utc_now_naive().date().isoformat())][0] == 5000.0
    total_narrative_weight = (
        log1p(100.0)
        + log1p(80.0)
        + log1p(5000.0)
        + log1p(240.0)
        + log1p(90.0)
        + log1p(170.0)
        + log1p(5000.0)
    )
    expected_speculation_share = (
        log1p(100.0)
        + log1p(5000.0)
        + log1p(240.0)
        + log1p(5000.0)
    ) / total_narrative_weight
    expected_builder_share = (
        log1p(90.0)
        + log1p(170.0)
    ) / total_narrative_weight
    expected_institutional_share = log1p(80.0) / total_narrative_weight
    assert round(
        by_identity[("google_trends_narrative_concentration", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == round(expected_speculation_share, 6)
    assert round(
        by_identity[("google_trends_narrative_speculation_share", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == round(expected_speculation_share, 6)
    assert round(
        by_identity[("google_trends_narrative_builder_share", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == round(expected_builder_share, 6)
    assert round(
        by_identity[("google_trends_narrative_institutional_share", "bitcoin", utc_now_naive().date().isoformat())][0],
        6,
    ) == round(expected_institutional_share, 6)
    assert by_identity[("google_trends_narrative_risk_share", "bitcoin", utc_now_naive().date().isoformat())][0] == 0.0

    latest_count = db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ? AND (entity_key = ? OR entity_key = ?)
        """,
        ("google_trends", "bitcoin", "crypto"),
    )
    assert latest_count["count"] == 26

    db.close()


def test_google_trends_bootstrap_stitches_long_history(tmp_path):
    db = DBManager(str(tmp_path / "google_trends_bootstrap.sqlite"))
    db.init_tables()
    collector = GoogleTrendsCollector(StaticAlternativeClient(), db)
    base_now = utc_now_naive()

    def fake_fetch_interest(query, timeframe, geo="", category=0, gprop="", hl="en-US", tz=0):
        rows = {
            recent_timeframe: [
                {"timestamp": base_now - timedelta(days=2), "value": 20.0, "formatted_time": "A", "has_data": True, "is_partial": False},
                {"timestamp": base_now - timedelta(days=1), "value": 30.0, "formatted_time": "B", "has_data": True, "is_partial": False},
                {"timestamp": base_now, "value": 40.0, "formatted_time": "C", "has_data": True, "is_partial": False},
            ],
            older_timeframe: [
                {"timestamp": base_now - timedelta(days=30), "value": 10.0, "formatted_time": "D", "has_data": True, "is_partial": False},
                {"timestamp": base_now - timedelta(days=2), "value": 10.0, "formatted_time": "A", "has_data": True, "is_partial": False},
                {"timestamp": base_now - timedelta(days=1), "value": 15.0, "formatted_time": "B", "has_data": True, "is_partial": False},
            ],
        }
        return rows.get(timeframe, [])

    with patch.dict(
        "config.settings.ALTERNATIVE_CONFIG",
        {
            "google_trends_bootstrap_history_days": 120,
            "google_trends_history_segment_days": 90,
            "google_trends_history_overlap_days": 30,
            "google_trends_window_days": 90,
        },
        clear=False,
    ):
        segments = collector._build_history_segments(
            total_days=120,
            segment_days=90,
            overlap_days=30,
        )
        recent_timeframe = str(segments[0]["timeframe"])
        older_timeframe = str(segments[1]["timeframe"])
        with patch.object(collector, "_fetch_interest_rows") as mock_fetch:
            mock_fetch.side_effect = lambda query_group, timeframe: fake_fetch_interest(
                query=str(query_group["query"]),
                timeframe=timeframe,
            )
            points = collector.bootstrap_history(entity_keys=["bitcoin"])

    assert any(
        point.factor_id == "google_trends_search_interest"
        and point.observation_time.date().isoformat() == (base_now - timedelta(days=30)).date().isoformat()
        and round(point.value, 6) == 20.0
        for point in points
    )
    assert any(
        point.factor_id == "google_trends_attention_shock_7d"
        for point in points
    )


def test_load_latest_context_bundle_groups_ai_ready_signals(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "bundle.sqlite")),
    )
    service.init_storage()
    service.collect_once(
        source_names=["google_trends", "github", "stablecoin"],
        entity_keys=["bitcoin", "crypto", "BTC", "USDT"],
    )

    bundle = service.load_latest_context_bundle(
        source_names=["google_trends", "github", "stablecoin"],
        entity_keys=["bitcoin", "crypto", "BTC", "USDT"],
    )

    assert bundle["as_of"] == bundle["latest_observation_time"]
    assert bundle["row_count"] == 19
    assert bundle["raw_row_count"] == 45
    assert bundle["source_counts"] == {
        "stablecoin": 13,
        "github": 6,
    }
    assert bundle["raw_source_counts"] == {
        "google_trends": 26,
        "stablecoin": 13,
        "github": 6,
    }
    assert bundle["ai_ready_source_names"] == ["github", "stablecoin"]
    assert bundle["ai_excluded_source_names"] == ["google_trends"]
    assert bundle["coverage_summary"]["expected_entity_count"] == 4
    assert bundle["coverage_summary"]["observed_entity_count"] == 6
    assert bundle["coverage_summary"]["observed_factor_count"] >= 3
    assert bundle["coverage_summary"]["observed_point_count"] == 45
    assert bundle["coverage_summary"]["observed_source_count"] == 3
    assert bundle["coverage_summary"]["coverage_by_source"] == [
        {
            "source_name": "github",
            "entity_type": "repo_group",
            "phase": "P0",
            "expected_entity_count": 1,
            "observed_entity_count": 1,
            "observed_factor_count": 6,
            "observed_point_count": 6,
            "is_ready_for_ai": True,
        },
        {
            "source_name": "google_trends",
            "entity_type": "query_group",
            "phase": "P1",
            "expected_entity_count": 2,
            "observed_entity_count": 2,
            "observed_factor_count": 13,
            "observed_point_count": 26,
            "is_ready_for_ai": False,
        },
        {
            "source_name": "stablecoin",
            "entity_type": "stablecoin_asset / stablecoin_chain",
            "phase": "P0",
            "expected_entity_count": 1,
            "observed_entity_count": 3,
            "observed_factor_count": 9,
            "observed_point_count": 13,
            "is_ready_for_ai": True,
        },
    ]
    assert bundle["coverage_summary"]["coverage_by_entity_type"] == [
        {
            "entity_type": "query_group",
            "expected_entity_count": 2,
            "observed_entity_count": 2,
            "source_count": 1,
            "ready_source_count": 1,
            "problem_source_count": 0,
        },
        {
            "entity_type": "repo_group",
            "expected_entity_count": 1,
            "observed_entity_count": 1,
            "source_count": 1,
            "ready_source_count": 1,
            "problem_source_count": 0,
        },
        {
            "entity_type": "stablecoin_asset / stablecoin_chain",
            "expected_entity_count": 1,
            "observed_entity_count": 3,
            "source_count": 1,
            "ready_source_count": 1,
            "problem_source_count": 0,
        },
    ]
    assert bundle["latest_quality_flag_breakdown"] == {
        "ok": 19,
        "partial": 0,
        "fallback": 0,
        "stale": 0,
        "unknown": 0,
    }
    assert bundle["latest_quality_ready_ratio"] == 1.0
    assert bundle["raw_latest_quality_flag_breakdown"]["partial"] > 0
    assert bundle["raw_latest_quality_ready_ratio"] < 1.0
    assert bundle["source_health_summary"]["ready_source_count"] == 3
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 2
    assert bundle["source_health_summary"]["not_ready_for_ai_source_count"] == 1
    assert bundle["configured_universe_summary"] == {
        "scope_kind": "filtered",
        "entity_type_counts": {
            "query_group": 2,
            "repo_group": 1,
            "stablecoin_asset": 1,
        },
        "entity_keys_by_type": {
            "query_group": ["bitcoin", "crypto"],
            "repo_group": ["BTC"],
            "stablecoin_asset": ["USDT"],
        },
        "minimum_entity_type_counts_for_market_breadth": {
            "query_group": 10,
            "repo_group": 6,
            "stablecoin_asset": 6,
        },
        "breadth_status": "filtered",
        "is_market_breadth_sufficient": None,
    }
    assert "google_trends_experimental_source" in bundle["data_quality_flags"]
    assert "google_trends_context_missing" in bundle["data_quality_flags"]
    assert "alternative_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert "alternative_partial_present" not in bundle["data_quality_flags"]
    assert all(item["health_status"] == "ready" for item in bundle["source_health"])
    source_health_map = {
        item["source_name"]: item
        for item in bundle["source_health"]
    }
    assert source_health_map["google_trends"]["is_ready_for_ai"] is False
    assert "experimental_source" in source_health_map["google_trends"]["data_quality_flags"]
    assert source_health_map["github"]["is_ready_for_ai"] is True
    assert source_health_map["stablecoin"]["is_ready_for_ai"] is True
    assert bundle["source_health"][0]["phase"] == "P0"
    assert bundle["source_health"][1]["phase"] == "P1"
    assert "google_trends" not in bundle["sources"]
    assert bundle["ai_excluded_sources"][0]["source_name"] == "google_trends"
    assert bundle["ai_excluded_sources"][0]["excluded_reason"] == "source_not_ready_for_ai"
    assert bundle["ai_excluded_sources"][0]["phase"] == "P1"
    assert bundle["ai_excluded_sources"][0]["raw_row_count"] == 26
    assert bundle["ai_excluded_sources"][0]["raw_entity_count"] == 2
    assert (
        "google_trends_search_interest"
        in bundle["ai_excluded_sources"][0]["raw_factor_ids"]
    )

    github_leader = bundle["sources"]["github"]["leaders_by_commit_7d"][0]
    assert github_leader["entity_key"] == "BTC"
    assert github_leader["commit_count_7d"] == 6.0

    stablecoin_summary = bundle["sources"]["stablecoin"]["summary"]
    assert stablecoin_summary["total_mint_volume_1d"] == 100.0
    assert stablecoin_summary["total_burn_volume_1d"] == 0.0
    usdt_asset = {
        item["entity_key"]: item
        for item in bundle["sources"]["stablecoin"]["assets"]
    }["USDT"]
    assert usdt_asset["mint_volume_1d"] == 100.0
    assert usdt_asset["dominant_chain"] == "Ethereum"
    assert usdt_asset["chains"][0]["entity_key"] == "USDT:ethereum"

    service.close()


def test_load_latest_context_bundle_flags_default_market_breadth_limits(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "bundle_breadth.sqlite")),
    )
    service.init_storage()
    service.collect_once(
        source_names=["google_trends", "github", "stablecoin"],
    )

    bundle = service.load_latest_context_bundle(
        source_names=["google_trends", "github", "stablecoin"],
    )

    assert bundle["configured_universe_summary"] == {
        "scope_kind": "default",
        "entity_type_counts": {
            "query_group": 8,
            "repo_group": 4,
            "stablecoin_asset": 4,
        },
        "entity_keys_by_type": {
            "query_group": [
                "bitcoin",
                "bitcoin_etf",
                "crypto",
                "ethereum",
                "memecoin",
                "solana",
                "stablecoin",
                "sui",
            ],
            "repo_group": ["BTC", "ETH", "SOL", "SUI"],
            "stablecoin_asset": ["DAI", "FDUSD", "USDC", "USDT"],
        },
        "minimum_entity_type_counts_for_market_breadth": {
            "query_group": 10,
            "repo_group": 6,
            "stablecoin_asset": 6,
        },
        "breadth_status": "limited",
        "is_market_breadth_sufficient": False,
    }
    assert "alternative_configured_market_breadth_limited" in bundle["data_quality_flags"]
    assert any(
        "query_group=8/10" in note and "repo_group=4/6" in note and "stablecoin_asset=4/6" in note
        for note in bundle["quality_notes"]
    )

    service.close()


def test_alternative_bundle_treats_source_filtered_scope_as_filtered(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "bundle_source_filtered.sqlite")),
    )
    service.init_storage()
    service.collect_once(
        source_names=["github"],
    )

    bundle = service.load_latest_context_bundle(
        source_names=["github"],
    )

    assert bundle["configured_universe_summary"]["scope_kind"] == "filtered"
    assert bundle["configured_universe_summary"]["breadth_status"] == "filtered"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is None
    assert "alternative_configured_market_breadth_limited" not in bundle["data_quality_flags"]

    service.close()


def test_collect_once_records_collection_runs_and_source_coverage(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "coverage.sqlite")),
    )
    service.init_storage()

    summary = service.collect_once(
        source_names=["google_trends", "github", "stablecoin"],
        entity_keys=["bitcoin", "crypto", "BTC", "USDT"],
    )

    run_count = service.db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM collection_runs
        WHERE module_name = 'alternative_data'
        """
    )["count"]
    coverage = service.load_source_coverage(
        source_names=["google_trends", "github", "stablecoin"],
        entity_keys=["bitcoin", "crypto", "BTC", "USDT"],
    )
    coverage_map = {
        row["source_name"]: row
        for row in coverage["sources"]
    }

    assert summary == {
        "google_trends_points": 38,
        "github_points": 6,
        "stablecoin_points": 13,
    }
    assert run_count == 3
    assert coverage["source_count"] == 3
    assert coverage["stale_source_count"] == 0
    assert coverage["ready_source_count"] == 3
    assert coverage["problem_source_count"] == 0
    assert coverage["total_latest_point_count"] == 45
    assert coverage["ready_for_ai_source_count"] == 2
    assert coverage["not_ready_for_ai_source_count"] == 1
    assert coverage_map["google_trends"]["health_status"] == "ready"
    assert coverage_map["google_trends"]["is_ready_for_ai"] is False
    assert "experimental_source" in coverage_map["google_trends"]["data_quality_flags"]
    assert coverage_map["google_trends"]["latest_partial_point_count"] > 0
    assert coverage_map["google_trends"]["latest_quality_ready_ratio"] < 1.0
    assert coverage_map["google_trends"]["quality_notes"]
    assert coverage_map["google_trends"]["registry_version"]
    assert coverage_map["github"]["latest_point_count"] == 6
    assert coverage_map["github"]["latest_ok_point_count"] == 6
    assert coverage_map["github"]["is_ready_for_ai"] is True
    assert coverage_map["stablecoin"]["expected_entity_count"] == 1
    assert coverage_map["stablecoin"]["latest_entity_count"] == 3
    assert coverage_map["stablecoin"]["latest_point_count"] == 13
    assert coverage_map["stablecoin"]["is_ready_for_ai"] is True
    assert all(row["last_run_status"] == "success" for row in coverage["sources"])

    service.close()


def test_scheduler_jobs_use_thread_safe_wrappers(tmp_path):
    db_path = str(tmp_path / "scheduler.sqlite")
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(db_path),
    )
    service.init_storage()

    errors: list[str] = []

    def worker():
        try:
            service._run_google_trends_job(entity_keys=["bitcoin"])
            service._run_github_job(entity_keys=["BTC"])
            service._run_stablecoin_job(entity_keys=["USDT"])
        except Exception as exc:  # pragma: no cover - explicit failure capture
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []

    verify_db = DBManager(db_path)
    github_count = verify_db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ?
        """,
        ("github",),
    )
    stablecoin_count = verify_db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ?
        """,
        ("stablecoin",),
    )
    trends_count = verify_db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM latest_alternative_timeseries
        WHERE source_name = ?
        """,
        ("google_trends",),
    )
    run_count = verify_db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM collection_runs
        WHERE module_name = 'alternative_data'
        """
    )

    assert trends_count["count"] >= 1
    assert github_count["count"] >= 1
    assert stablecoin_count["count"] >= 1
    assert run_count["count"] == 3

    verify_db.close()
    service.close()


def test_build_scheduler_uses_alternative_wrappers(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "build.sqlite")),
    )

    scheduler = service.build_scheduler(
        source_names=["google_trends", "github", "stablecoin"],
        entity_keys=["bitcoin", "BTC", "USDT"],
    )

    assert isinstance(scheduler, BlockingScheduler)
    assert scheduler.get_job("alternative_google_trends").func == service._run_google_trends_job
    assert scheduler.get_job("alternative_github").func == service._run_github_job
    assert scheduler.get_job("alternative_stablecoin").func == service._run_stablecoin_job

    service.close()


def test_describe_registry_supports_source_and_entity_filters(tmp_path):
    service = AlternativeDataService(
        client=StaticAlternativeClient(),
        db=DBManager(str(tmp_path / "registry.sqlite")),
    )

    registry = service.describe_registry(
        source_names=["google_trends"],
        entity_keys=["bitcoin"],
    )

    assert [row["source_name"] for row in registry["sources"]] == ["google_trends"]
    assert registry["sources"][0]["registry_file"] == GOOGLE_TRENDS_QUERY_GROUPS_FILE
    assert registry["sources"][0]["registry_record_count"] >= 1
    assert len(str(registry["sources"][0]["registry_version"])) == 12
    assert {row["factor_id"] for row in registry["factors"]} == {
        "google_trends_search_interest",
        "google_trends_attention_shock_7d",
        "google_trends_related_query_breakout_count",
        "google_trends_related_query_rising_max_score",
        "google_trends_related_topic_breakout_count",
        "google_trends_related_topic_rising_max_score",
        "google_trends_cross_query_zscore",
        "google_trends_cross_query_percentile",
        "google_trends_narrative_concentration",
        "google_trends_narrative_speculation_share",
        "google_trends_narrative_builder_share",
        "google_trends_narrative_institutional_share",
        "google_trends_narrative_risk_share",
    }
    assert registry["entities"] == [
        {
            "source_name": "google_trends",
            "entity_type": "query_group",
            "entity_key": "bitcoin",
            "name": "Bitcoin Search Interest",
            "description": "query=bitcoin; type=asset",
        }
    ]

    service.close()
