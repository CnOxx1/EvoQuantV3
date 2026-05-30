import asyncio
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from apscheduler.schedulers.blocking import BlockingScheduler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db_manager import DBManager
import data_layer.news_data.service as news_service_module
from data_layer.news_data.client import NewsFeedClient
from data_layer.news_data.collector import NewsCollector
from data_layer.news_data.models import NewsArticle, NewsSource, utc_now_naive
from data_layer.news_data.service import NewsDataService
from data_layer.news_data.sources import load_news_sources


def make_article(**overrides) -> NewsArticle:
    payload = {
        "source": "source",
        "feed_url": "https://example.com/feed.xml",
        "title": "Bitcoin headline",
        "url": "https://example.com/posts/1",
        "url_hash": "hash-1",
        "collected_at": utc_now_naive(),
    }
    payload.update(overrides)
    return NewsArticle(**payload)


def test_fetch_articles_inside_running_loop_requires_async_api():
    client = NewsFeedClient()

    async def run():
        with pytest.raises(RuntimeError, match="fetch_articles_async"):
            client.fetch_articles([])

    asyncio.run(run())


def test_resolve_atom_link_prefers_alternate():
    entry = ET.fromstring(
        """
        <entry xmlns="http://www.w3.org/2005/Atom">
          <link rel="self" href="https://api.example.com/item/1" />
          <link rel="alternate" href="https://example.com/post/1" />
        </entry>
        """
    )

    assert NewsFeedClient._resolve_atom_link(entry) == "https://example.com/post/1"


def test_safe_markup_keeps_xhtml_content_text():
    node = ET.fromstring(
        """
        <content type="xhtml" xmlns="http://www.w3.org/2005/Atom">
          <div><p>Hello <b>world</b></p></div>
        </content>
        """
    )

    markup = NewsFeedClient._safe_markup(node)

    assert markup is not None
    assert NewsFeedClient._html_to_text(markup) == "Hello world"


def test_extract_symbols_covers_tracked_assets_and_stablecoins():
    matches = NewsFeedClient._extract_symbols(
        (
            "Bitcoin and Ethereum lead majors while Solana and Sui bounce. "
            "Tether, USDC, DAI and First Digital USD liquidity also expand."
        )
    )

    assert matches == ["BTC", "ETH", "SOL", "SUI", "USDT", "USDC", "DAI", "FDUSD"]


def test_extract_symbols_expands_market_universe_and_preserves_first_mention_order():
    matches = NewsFeedClient._extract_symbols(
        (
            "Arbitrum and Chainlink rebound first, then Bitcoin reacts. "
            "Later Celestia, Pyth Network, Starknet and Optimism also rally."
        )
    )

    assert matches == ["ARB", "LINK", "BTC", "TIA", "PYTH", "STRK", "OP"]


def test_extract_symbols_avoids_generic_word_false_positives():
    matches = NewsFeedClient._extract_symbols(
        "Traders shared a link and a ton of charts, but no tracked asset was explicitly named."
    )

    assert matches == []


def test_canonicalize_url_resolves_relative_links_and_sorts_query():
    url = NewsFeedClient._canonicalize_url(
        "/posts/123?utm_source=rss&b=1&a=2",
        base_url="https://example.com/feed.xml",
    )

    assert url == "https://example.com/posts/123?a=2&b=1"


def test_canonicalize_url_rejects_non_http_schemes():
    assert NewsFeedClient._canonicalize_url("mailto:editor@example.com") is None
    assert NewsFeedClient._canonicalize_url("javascript:void(0)") is None


def test_canonicalize_url_preserves_duplicate_query_key_order():
    first = NewsFeedClient._canonicalize_url("https://example.com/post?ids=1&ids=2")
    second = NewsFeedClient._canonicalize_url("https://example.com/post?ids=2&ids=1")

    assert first == "https://example.com/post?ids=1&ids=2"
    assert second == "https://example.com/post?ids=2&ids=1"


def test_filter_articles_by_time_falls_back_to_collected_at():
    old_article = make_article(
        url="https://example.com/posts/old",
        url_hash="old",
        published_at=None,
        collected_at=utc_now_naive() - timedelta(days=10),
    )
    recent_article = make_article(
        url="https://example.com/posts/recent",
        url_hash="recent",
        published_at=None,
        collected_at=utc_now_naive() - timedelta(hours=1),
    )

    filtered = NewsCollector._filter_articles_by_time(
        [old_article, recent_article],
        hours=24,
    )

    assert [article.url_hash for article in filtered] == ["recent"]


def test_select_sources_empty_list_returns_empty(tmp_path):
    collector = NewsCollector(NewsFeedClient(), DBManager(str(tmp_path / "sources.sqlite")))

    assert len(collector._select_sources(None)) > 0
    assert collector._select_sources([]) == []

    collector.db.close()


def test_select_sources_supports_group_category_and_tag_filters(tmp_path):
    collector = NewsCollector(NewsFeedClient(), DBManager(str(tmp_path / "filters.sqlite")))

    ecosystem_sources = collector._select_sources(source_groups=["ecosystem"])
    assert ecosystem_sources
    assert all(source.source_group == "ecosystem" for source in ecosystem_sources)

    governance_sources = collector._select_sources(categories=["governance"])
    assert governance_sources
    assert all(source.category == "governance" for source in governance_sources)

    official_sources = collector._select_sources(tags=["official"])
    assert official_sources
    assert all("official" in source.tags for source in official_sources)

    collector.db.close()


def test_load_news_sources_attaches_source_groups():
    sources = load_news_sources(source_names=["CoinDesk", "SEC Press Releases"])
    by_name = {source.name: source for source in sources}

    assert by_name["CoinDesk"].source_group == "core_media"
    assert by_name["SEC Press Releases"].source_group == "research_security_regulatory"


def test_deduplicate_articles_prefers_richer_version_in_same_batch():
    rich_article = make_article(
        url="https://example.com/posts/rich",
        url_hash="same",
        summary="rich summary",
        content_text="rich content",
        collected_at=utc_now_naive() - timedelta(hours=2),
    )
    sparse_article = make_article(
        url="https://example.com/posts/sparse",
        url_hash="same",
        summary=None,
        content_text=None,
        collected_at=utc_now_naive() - timedelta(hours=1),
    )

    deduped = NewsCollector._deduplicate_articles([rich_article, sparse_article])

    assert len(deduped) == 1
    assert deduped[0].summary == "rich summary"
    assert deduped[0].content_text == "rich content"
    assert deduped[0].collected_at == sparse_article.collected_at


def test_save_to_db_skips_unchanged_duplicates(tmp_path):
    db = DBManager(str(tmp_path / "news.sqlite"))
    db.init_tables()
    collector = NewsCollector(NewsFeedClient(), db)

    first_article = make_article()
    second_article = make_article(
        collected_at=utc_now_naive() + timedelta(hours=1),
    )

    collector.save_to_db([first_article])
    collector.save_to_db([second_article])

    row = db.fetch_one(
        "SELECT COUNT(*) AS count, collected_at FROM news_articles WHERE url_hash = ?",
        (first_article.url_hash,),
    )

    assert row["count"] == 1
    assert row["collected_at"] == first_article.collected_at.isoformat()

    db.close()


def test_save_to_db_preserves_existing_optional_fields_on_sparse_refetch(tmp_path):
    db = DBManager(str(tmp_path / "news_sparse.sqlite"))
    db.init_tables()
    collector = NewsCollector(NewsFeedClient(), db)

    rich_article = make_article(
        summary="summary",
        content_text="full body",
        author="alice",
        image_url="https://example.com/image.png",
        external_id="article-1",
    )
    sparse_article = make_article(
        summary=None,
        content_text=None,
        author=None,
        image_url=None,
        external_id=None,
    )

    collector.save_to_db([rich_article])
    collector.save_to_db([sparse_article])

    row = db.fetch_one(
        """
        SELECT summary, content_text, author, image_url, external_id
        FROM news_articles
        WHERE url_hash = ?
        """,
        (rich_article.url_hash,),
    )

    assert row["summary"] == "summary"
    assert row["content_text"] == "full body"
    assert row["author"] == "alice"
    assert row["image_url"] == "https://example.com/image.png"
    assert row["external_id"] == "article-1"

    db.close()


class StaticClient:
    def __init__(self, article: NewsArticle):
        self.article = article

    def fetch_articles(self, sources, limit_per_source=None):
        return [self.article]

    async def fetch_articles_async(self, sources, limit_per_source=None):
        return [self.article]


class CoverageHealthClient:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []

    def describe_source_health(self, sources=None):
        return list(self.rows)


class FakeResponse:
    def __init__(self, body: str, url: str, status: int = 200):
        self._body = body
        self.url = url
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"status={self.status}")

    async def text(self):
        return self._body


class FakeRequestContext:
    def __init__(self, result):
        self.result = result

    async def __aenter__(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, responses_by_url):
        self.responses_by_url = {
            url: list(results)
            for url, results in responses_by_url.items()
        }
        self.calls: list[tuple[str, str | None]] = []

    def get(self, url, proxy=None):
        self.calls.append((url, proxy))
        results = self.responses_by_url[url]
        if not results:
            raise AssertionError(f"unexpected extra request for {url}")
        return FakeRequestContext(results.pop(0))


def test_scheduler_job_uses_fresh_db_connection_per_thread(tmp_path):
    db_path = str(tmp_path / "scheduler.sqlite")
    service = NewsDataService(
        client=StaticClient(make_article(url_hash="scheduled", url="https://example.com/scheduled")),
        db=DBManager(db_path),
    )
    service.init_storage()

    errors: list[str] = []

    def worker():
        try:
            service._run_scheduled_collect(source_names=["CoinDesk"])
        except Exception as exc:  # pragma: no cover - explicit failure capture
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []

    verify_db = DBManager(db_path)
    row = verify_db.fetch_one(
        "SELECT COUNT(*) AS count FROM news_articles WHERE url_hash = ?",
        ("scheduled",),
    )
    assert row["count"] == 1
    verify_db.close()
    service.close()


def test_build_scheduler_uses_thread_safe_wrapper(tmp_path):
    service = NewsDataService(db=DBManager(str(tmp_path / "scheduler_build.sqlite")))

    scheduler = service.build_scheduler()

    assert isinstance(scheduler, BlockingScheduler)
    job = scheduler.get_job("news_articles")
    assert job is not None
    assert job.func == service._run_scheduled_collect

    service.close()


def test_collect_once_records_collection_run_and_coverage(tmp_path):
    db_path = str(tmp_path / "news_coverage.sqlite")
    service = NewsDataService(
        client=StaticClient(
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                url_hash="coverage-1",
                url="https://example.com/coverage-1",
            )
        ),
        db=DBManager(db_path),
    )
    service.init_storage()

    service.collect_once(source_names=["CoinDesk"])

    run_row = service.db.fetch_one(
        """
        SELECT module_name, source_name, status, item_count
        FROM collection_runs
        WHERE module_name = 'news_data' AND source_name = 'CoinDesk'
        ORDER BY id DESC
        LIMIT 1
        """
    )
    coverage = service.load_source_coverage(source_names=["CoinDesk"])

    assert run_row["status"] == "success"
    assert run_row["item_count"] == 1
    assert coverage["source_count"] == 1
    assert coverage["ready_source_count"] == 1
    assert coverage["problem_source_count"] == 0
    assert coverage["ready_for_ai_source_count"] == 0
    assert coverage["not_ready_for_ai_source_count"] == 1
    assert coverage["recent_article_count"] == 1
    assert coverage["sources"][0]["source_name"] == "CoinDesk"
    assert coverage["sources"][0]["name"] == "CoinDesk"
    assert coverage["sources"][0]["configuration_ready"] is True
    assert coverage["sources"][0]["health_status"] == "ready"
    assert coverage["sources"][0]["is_ready_for_ai"] is False
    assert coverage["sources"][0]["last_run_status"] == "success"
    assert "recent_articles_thin" in coverage["sources"][0]["data_quality_flags"]
    service.close()


def test_source_coverage_marks_cooldown_and_missing_recent_news(tmp_path):
    db = DBManager(str(tmp_path / "news_quality.sqlite"))
    service = NewsDataService(
        client=CoverageHealthClient(
            rows=[
                {
                    "source_name": "CoinDesk",
                    "consecutive_failures": 2,
                    "in_cooldown": True,
                    "cooldown_until": (
                        datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=30)
                    ).isoformat(),
                    "last_error": "timeout",
                }
            ]
        ),
        db=db,
    )
    service.init_storage()

    service.collector.save_to_db(
        [
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                url_hash="quality-1",
                url="https://example.com/quality-1",
                collected_at=utc_now_naive() - timedelta(days=3),
                published_at=utc_now_naive() - timedelta(days=3),
            )
        ]
    )

    now = utc_now_naive()
    service.db.record_collection_run(
        module_name="news_data",
        source_name="CoinDesk",
        job_name="news_articles",
        status="success",
        item_count=0,
        started_at=(now - timedelta(minutes=1)).isoformat(),
        finished_at=now.isoformat(),
        duration_seconds=60,
        metadata_json='{"feed_url":"https://www.coindesk.com/arc/outboundfeeds/rss"}',
    )

    coverage = service.load_source_coverage(source_names=["CoinDesk"])
    source = coverage["sources"][0]

    assert coverage["source_count"] == 1
    assert coverage["cooldown_source_count"] == 1
    assert coverage["problem_source_count"] == 1
    assert source["health_status"] == "cooldown"
    assert source["is_ready_for_ai"] is False
    assert source["recent_articles"] == 0
    assert "source_in_cooldown" in source["data_quality_flags"]
    assert "consecutive_failures_present" in source["data_quality_flags"]
    assert "no_recent_articles" in source["data_quality_flags"]
    assert any("失败冷却期" in note for note in source["quality_notes"])
    service.close()


def test_reference_source_can_remain_ai_ready_without_recent_articles(tmp_path):
    db = DBManager(str(tmp_path / "news_reference.sqlite"))
    service = NewsDataService(db=db)
    service.init_storage()

    article_time = utc_now_naive() - timedelta(days=3)
    service.collector.save_to_db(
        [
            make_article(
                source="SEC Press Releases",
                feed_url="https://www.sec.gov/news/pressreleases.rss",
                url_hash="sec-1",
                url="https://example.com/sec-1",
                collected_at=article_time,
                published_at=article_time,
            )
        ]
    )

    now = utc_now_naive()
    service.db.record_collection_run(
        module_name="news_data",
        source_name="SEC Press Releases",
        job_name="news_articles",
        status="success",
        item_count=0,
        started_at=(now - timedelta(minutes=2)).isoformat(),
        finished_at=now.isoformat(),
        duration_seconds=120,
        metadata_json='{"feed_url":"https://www.sec.gov/news/pressreleases.rss"}',
    )

    coverage = service.load_source_coverage(source_names=["SEC Press Releases"], hours=24)
    source = coverage["sources"][0]

    assert coverage["ready_source_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 1
    assert source["health_status"] == "ready"
    assert source["is_ready_for_ai"] is True
    assert source["coverage_expectation"] == "event_driven_reference"
    assert source["recommended_recent_articles"] == 0
    assert source["recent_articles"] == 0
    assert "no_recent_articles" not in source["data_quality_flags"]
    assert "recent_articles_thin" not in source["data_quality_flags"]
    assert any("低频参考" in note for note in source["quality_notes"])
    service.close()


def test_high_frequency_source_requires_content_and_symbol_coverage_for_ai_ready(tmp_path):
    db = DBManager(str(tmp_path / "news_high_frequency_quality.sqlite"))
    service = NewsDataService(db=db)
    service.init_storage()

    now = utc_now_naive()
    service.collector.save_to_db(
        [
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                url_hash="hf-1",
                url="https://example.com/hf-1",
                title="Market wrap one",
                summary="summary only",
                content_text=None,
                published_at=now - timedelta(hours=1),
                collected_at=now - timedelta(hours=1),
                relevance_symbols=[],
            ),
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                url_hash="hf-2",
                url="https://example.com/hf-2",
                title="Market wrap two",
                summary="summary only",
                content_text=None,
                published_at=now - timedelta(hours=2),
                collected_at=now - timedelta(hours=2),
                relevance_symbols=[],
            ),
        ]
    )
    service.db.record_collection_run(
        module_name="news_data",
        source_name="CoinDesk",
        job_name="news_articles",
        status="success",
        item_count=2,
        started_at=(now - timedelta(minutes=5)).isoformat(),
        finished_at=now.isoformat(),
        duration_seconds=300,
    )

    coverage = service.load_source_coverage(source_names=["CoinDesk"])
    source = coverage["sources"][0]

    assert coverage["ready_source_count"] == 1
    assert coverage["ready_for_ai_source_count"] == 0
    assert source["recent_articles"] == 2
    assert source["recent_articles_with_content_text"] == 0
    assert source["recent_articles_with_relevance_symbols"] == 0
    assert source["health_status"] == "ready"
    assert source["is_ready_for_ai"] is False
    assert "content_text_coverage_thin" in source["data_quality_flags"]
    assert "relevance_symbol_coverage_missing" in source["data_quality_flags"]
    service.close()


def test_load_latest_context_bundle_exposes_ai_ready_news_context(monkeypatch, tmp_path):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    monkeypatch.setattr(
        NewsDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = NewsDataService(db=DBManager(str(tmp_path / "news_bundle.sqlite")))
    service.init_storage()
    service.collector.save_to_db(
        [
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                category="crypto-news",
                title="BTC ETF inflow accelerates",
                url="https://example.com/coindesk-1",
                url_hash="coindesk-1",
                summary="ETF demand stays firm",
                content_text="Bitcoin ETF inflows accelerated again overnight.",
                published_at=fixed_now - timedelta(hours=1),
                collected_at=fixed_now - timedelta(minutes=50),
                relevance_symbols=["BTC"],
                tags=["etf", "institutional"],
            ),
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                category="crypto-news",
                title="ETH funding stays elevated",
                url="https://example.com/coindesk-2",
                url_hash="coindesk-2",
                summary="ETH perp sentiment remains warm",
                content_text="Ether derivatives continue to price aggressive positioning.",
                published_at=fixed_now - timedelta(hours=2),
                collected_at=fixed_now - timedelta(hours=2),
                relevance_symbols=["ETH"],
                tags=["derivatives"],
            ),
            make_article(
                source="Cointelegraph",
                feed_url="https://cointelegraph.com/rss",
                category="crypto-news",
                title="SOL ecosystem volume rebounds as USDC liquidity returns",
                url="https://example.com/cointelegraph-1",
                url_hash="cointelegraph-1",
                summary="SOL regains spot momentum",
                content_text="Solana ecosystem activity picked up across majors while USDC settlement demand improved.",
                published_at=fixed_now - timedelta(hours=3),
                collected_at=fixed_now - timedelta(hours=3),
                relevance_symbols=["SOL", "USDC"],
                tags=["ecosystem", "stablecoin"],
            ),
            make_article(
                source="Cointelegraph",
                feed_url="https://cointelegraph.com/rss",
                category="crypto-news",
                title="ETH spot demand improves as exchange reserves tighten",
                url="https://example.com/cointelegraph-2",
                url_hash="cointelegraph-2",
                summary="ETH liquidity stays constructive",
                content_text="Exchange reserves declined further while spot demand remained firm.",
                published_at=fixed_now - timedelta(hours=2, minutes=30),
                collected_at=fixed_now - timedelta(hours=2, minutes=20),
                relevance_symbols=["ETH"],
                tags=["exchange", "spot"],
            ),
            make_article(
                source="Blockworks",
                feed_url="https://blockworks.com/feed/",
                category="market-intelligence",
                title="BTC basis remains firm into macro week as Tether flows stay strong",
                url="https://example.com/blockworks-1",
                url_hash="blockworks-1",
                summary="Desk commentary stays constructive",
                content_text=None,
                published_at=fixed_now - timedelta(hours=4),
                collected_at=fixed_now - timedelta(hours=4),
                relevance_symbols=["BTC", "USDT"],
                tags=["research", "macro", "stablecoin"],
            ),
        ]
    )

    for source_name in ("CoinDesk", "Cointelegraph", "Blockworks"):
        service.db.record_collection_run(
            module_name="news_data",
            source_name=source_name,
            job_name="news_articles",
            status="success",
            item_count=1,
            started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=300,
        )

    bundle = service.load_latest_context_bundle(
        hours=24,
        source_names=["CoinDesk", "Cointelegraph", "Blockworks"],
    )

    assert bundle["as_of"] == (fixed_now - timedelta(hours=1)).isoformat()
    assert bundle["raw_as_of"] == (fixed_now - timedelta(hours=1)).isoformat()
    assert bundle["article_count"] == 4
    assert bundle["raw_article_count"] == 5
    assert bundle["source_counts"] == {
        "CoinDesk": 2,
        "Cointelegraph": 2,
    }
    assert bundle["raw_source_counts"] == {
        "CoinDesk": 2,
        "Cointelegraph": 2,
        "Blockworks": 1,
    }
    assert bundle["ai_ready_source_names"] == ["CoinDesk", "Cointelegraph"]
    assert bundle["ai_excluded_source_names"] == ["Blockworks"]
    assert bundle["configured_universe_summary"]["scope_kind"] == "default"
    assert bundle["configured_universe_summary"]["breadth_status"] == "sufficient"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is True
    assert (
        bundle["configured_universe_summary"]["market_role_counts"]["stablecoins"]
        >= bundle["configured_universe_summary"][
            "minimum_market_role_counts_for_market_breadth"
        ]["stablecoins"]
    )
    assert "BTC" in bundle["configured_universe_summary"]["tracked_symbols_by_group"]["core_majors"]
    assert bundle["coverage_summary"]["selected_source_count"] == 3
    assert bundle["coverage_summary"]["observed_source_count"] == 2
    assert bundle["coverage_summary"]["raw_observed_source_count"] == 3
    assert bundle["coverage_summary"]["ready_for_ai_source_count"] == 2
    assert bundle["coverage_summary"]["missing_high_frequency_source_groups"] == [
        "market_intelligence"
    ]
    assert bundle["coverage_summary"]["coverage_by_source"][0]["source_name"] == "CoinDesk"
    assert bundle["source_health_summary"]["ready_source_count"] == 3
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 2
    assert bundle["text_completeness_summary"]["articles_with_content_text_count"] == 4
    assert bundle["raw_text_completeness_summary"]["articles_with_content_text_count"] == 4
    assert bundle["raw_text_completeness_summary"]["articles_with_relevance_symbols_count"] == 5
    assert bundle["top_sources_by_recent_articles"][0]["source_name"] == "CoinDesk"
    assert bundle["category_distribution"][0]["category"] == "crypto-news"
    assert bundle["source_group_distribution"][0]["source_group"] == "core_media"
    assert bundle["dominant_symbols"][0]["symbol"] == "ETH"
    assert bundle["dominant_symbols"][0]["article_count"] == 2
    assert any(item["symbol"] == "USDC" for item in bundle["dominant_symbols"])
    assert not any(item["symbol"] == "USDT" for item in bundle["dominant_symbols"])
    assert bundle["latest_articles"][0]["title"] == "BTC ETF inflow accelerates"
    assert bundle["latest_articles"][0]["health_status"] == "ready"
    assert all(item["source"] != "Blockworks" for item in bundle["latest_articles"])
    assert bundle["ai_excluded_sources"][0]["source_name"] == "Blockworks"
    assert bundle["ai_excluded_sources"][0]["excluded_reason"] == "source_not_ready_for_ai"
    assert bundle["ai_excluded_sources"][0]["raw_article_count"] == 1
    assert bundle["ai_excluded_sources"][0]["raw_relevance_symbols"] == ["BTC", "USDT"]
    assert "news_configured_market_breadth_limited" not in bundle["data_quality_flags"]
    assert "news_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert "news_market_intelligence_missing" in bundle["data_quality_flags"]
    assert bundle["quality_notes"]

    service.close()


def test_context_bundle_marks_high_frequency_group_missing_when_source_not_ai_ready(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    monkeypatch.setattr(
        NewsDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )

    service = NewsDataService(db=DBManager(str(tmp_path / "news_bundle_gap.sqlite")))
    service.init_storage()
    service.collector.save_to_db(
        [
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                category="crypto-news",
                title="BTC ETF flow returns",
                url="https://example.com/gap-coindesk-1",
                url_hash="gap-coindesk-1",
                published_at=fixed_now - timedelta(hours=1),
                collected_at=fixed_now - timedelta(minutes=45),
                relevance_symbols=["BTC"],
            ),
            make_article(
                source="Blockworks",
                feed_url="https://blockworks.com/feed/",
                category="market-intelligence",
                title="Macro desk sees basis holding up",
                url="https://example.com/gap-blockworks-1",
                url_hash="gap-blockworks-1",
                published_at=fixed_now - timedelta(hours=2),
                collected_at=fixed_now - timedelta(hours=2),
                relevance_symbols=["BTC"],
            ),
        ]
    )

    for source_name in ("CoinDesk", "Blockworks"):
        service.db.record_collection_run(
            module_name="news_data",
            source_name=source_name,
            job_name="news_articles",
            status="success",
            item_count=1,
            started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
            finished_at=fixed_now.isoformat(),
            duration_seconds=300,
        )

    bundle = service.load_latest_context_bundle(
        hours=24,
        source_names=["CoinDesk", "Blockworks"],
    )

    assert bundle["article_count"] == 0
    assert bundle["raw_article_count"] == 2
    assert bundle["source_counts"] == {}
    assert bundle["raw_source_counts"] == {
        "Blockworks": 1,
        "CoinDesk": 1,
    }
    assert bundle["ai_ready_source_names"] == []
    assert bundle["ai_excluded_source_names"] == ["Blockworks", "CoinDesk"]
    assert bundle["coverage_summary"]["ready_source_count"] == 2
    assert bundle["coverage_summary"]["ready_for_ai_source_count"] == 0
    assert bundle["coverage_summary"]["missing_high_frequency_source_groups"] == [
        "core_media",
        "market_intelligence",
    ]
    assert bundle["source_health_summary"]["ready_for_ai_source_count"] == 0
    assert "news_source_not_ready_for_ai_present" in bundle["data_quality_flags"]
    assert "news_context_empty" in bundle["data_quality_flags"]
    assert bundle["latest_articles"] == []
    assert any(item["source_name"] == "CoinDesk" and item["is_ready_for_ai"] is False for item in bundle["coverage_summary"]["coverage_by_source"])
    service.close()


def test_context_bundle_marks_configured_market_breadth_limited_when_registry_is_narrow(
    monkeypatch,
    tmp_path,
):
    fixed_now = datetime(2026, 5, 10, 12, 0, 0)
    monkeypatch.setattr(
        NewsDataService,
        "_utc_now_naive",
        staticmethod(lambda: fixed_now),
    )
    monkeypatch.setattr(
        news_service_module,
        "TRACKED_ASSET_ALIASES",
        {
            "BTC": ["BTC", "BITCOIN"],
            "ETH": ["ETH", "ETHEREUM"],
            "USDT": ["USDT", "TETHER"],
        },
    )

    service = NewsDataService(db=DBManager(str(tmp_path / "news_bundle_narrow_registry.sqlite")))
    service.init_storage()
    service.collector.save_to_db(
        [
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                category="crypto-news",
                title="Bitcoin liquidity stays firm",
                url="https://example.com/narrow-coindesk-1",
                url_hash="narrow-coindesk-1",
                summary="BTC and USDT remain active",
                content_text="Bitcoin liquidity stays firm while stablecoin balances hold up.",
                published_at=fixed_now - timedelta(hours=1),
                collected_at=fixed_now - timedelta(minutes=45),
                relevance_symbols=["BTC", "USDT"],
            ),
            make_article(
                source="CoinDesk",
                feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
                category="crypto-news",
                title="Ethereum traders stay cautious",
                url="https://example.com/narrow-coindesk-2",
                url_hash="narrow-coindesk-2",
                summary="ETH positioning cools",
                content_text="Ethereum derivatives traders remain cautious ahead of macro catalysts.",
                published_at=fixed_now - timedelta(hours=2),
                collected_at=fixed_now - timedelta(hours=2),
                relevance_symbols=["ETH"],
            ),
        ]
    )
    service.db.record_collection_run(
        module_name="news_data",
        source_name="CoinDesk",
        job_name="news_articles",
        status="success",
        item_count=2,
        started_at=(fixed_now - timedelta(minutes=5)).isoformat(),
        finished_at=fixed_now.isoformat(),
        duration_seconds=300,
    )

    bundle = service.load_latest_context_bundle(
        hours=24,
        source_names=["CoinDesk"],
    )

    assert bundle["configured_universe_summary"]["breadth_status"] == "limited"
    assert bundle["configured_universe_summary"]["is_market_breadth_sufficient"] is False
    assert bundle["configured_universe_summary"]["asset_count"] == 3
    assert bundle["configured_universe_summary"]["market_role_counts"] == {
        "core_majors": 2,
        "ecosystem_beta": 0,
        "stablecoins": 1,
    }
    assert bundle["configured_universe_summary"]["missing_market_role_groups"] == [
        "core_majors",
        "ecosystem_beta",
        "stablecoins",
    ]
    assert "news_configured_market_breadth_limited" in bundle["data_quality_flags"]

    service.close()


def test_describe_sources_returns_filtered_metadata():
    service = NewsDataService()

    rows = service.describe_sources(source_groups=["core_media"], tags=["breaking-news"])

    assert rows
    assert all(row["source_group"] == "core_media" for row in rows)
    assert all("breaking-news" in row["tags"] for row in rows)

    service.close()


def test_candidate_feed_urls_deduplicate_and_preserve_order():
    source = NewsSource(
        name="Example",
        feed_url="https://example.com/feed.xml",
        fallback_feed_urls=[
            "https://example.com/feed.xml",
            " https://backup.example.com/feed.xml ",
            "https://backup.example.com/feed.xml",
        ],
    )

    assert NewsFeedClient._candidate_feed_urls(source) == [
        "https://example.com/feed.xml",
        "https://backup.example.com/feed.xml",
    ]


def test_source_enters_cooldown_after_failure_threshold(monkeypatch):
    client = NewsFeedClient()
    client.source_failure_threshold = 2
    client.source_cooldown_base_seconds = 60
    client.source_cooldown_max_seconds = 300
    source = NewsSource(name="Example", feed_url="https://example.com/feed.xml")
    now = datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(client, "_utc_now", lambda: now)

    client._record_source_failure(source, "first failure")
    state = client._source_health[client._source_key(source)]
    assert state.consecutive_failures == 1
    assert state.cooldown_until is None

    client._record_source_failure(source, "second failure")
    state = client._source_health[client._source_key(source)]
    assert state.consecutive_failures == 2
    assert state.cooldown_until == now + timedelta(seconds=60)
    assert client._is_source_in_cooldown(source, now=now + timedelta(seconds=30)) is True


def test_select_runnable_sources_skips_cooling_source(monkeypatch):
    client = NewsFeedClient()
    client.source_failure_threshold = 1
    client.source_cooldown_base_seconds = 120
    client.source_cooldown_max_seconds = 300
    cooled = NewsSource(name="Cooled", feed_url="https://example.com/cooled.xml")
    active = NewsSource(name="Active", feed_url="https://example.com/active.xml")
    now = datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(client, "_utc_now", lambda: now)
    client._record_source_failure(cooled, "down")

    runnable = client._select_runnable_sources(
        [cooled, active],
        now=now + timedelta(seconds=30),
    )

    assert [source.name for source in runnable] == ["Active"]


def test_source_success_clears_failure_state(monkeypatch):
    client = NewsFeedClient()
    client.source_failure_threshold = 1
    client.source_cooldown_base_seconds = 60
    client.source_cooldown_max_seconds = 300
    source = NewsSource(name="Recovered", feed_url="https://example.com/feed.xml")
    now = datetime(2026, 5, 7, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(client, "_utc_now", lambda: now)
    client._record_source_failure(source, "temporary issue")
    assert client._source_key(source) in client._source_health

    client._record_source_success(source)

    assert client._source_key(source) not in client._source_health
    assert client._select_runnable_sources([source], now=now + timedelta(seconds=1)) == [source]


def test_download_feed_switches_to_fallback_url(monkeypatch):
    client = NewsFeedClient()
    source = NewsSource(
        name="Example",
        feed_url="https://example.com/feed.xml",
        fallback_feed_urls=["https://backup.example.com/feed.xml"],
    )
    session = FakeSession(
        {
            "https://example.com/feed.xml": [RuntimeError("ssl mismatch")],
            "https://backup.example.com/feed.xml": [
                FakeResponse(
                    body="<rss><channel></channel></rss>",
                    url="https://backup.example.com/feed.xml",
                )
            ],
        }
    )

    monkeypatch.setattr("data_layer.news_data.client.MAX_RETRIES", 2)
    monkeypatch.setattr("data_layer.news_data.client.RETRY_DELAY", 0)

    payload, effective_url = asyncio.run(client._download_feed(session, source))

    assert payload == "<rss><channel></channel></rss>"
    assert effective_url == "https://backup.example.com/feed.xml"
    assert [call[0] for call in session.calls] == [
        "https://example.com/feed.xml",
        "https://backup.example.com/feed.xml",
    ]


def test_fetch_source_uses_effective_feed_url_for_relative_links(monkeypatch):
    client = NewsFeedClient()
    source = NewsSource(
        name="Example",
        feed_url="https://example.com/feed.xml",
        fallback_feed_urls=["https://backup.example.com/feed.xml"],
    )
    session = FakeSession(
        {
            "https://example.com/feed.xml": [RuntimeError("ssl mismatch")],
            "https://backup.example.com/feed.xml": [
                FakeResponse(
                    body=(
                        "<?xml version='1.0' encoding='UTF-8'?>"
                        "<rss><channel><item>"
                        "<title>Backup item</title>"
                        "<link>/posts/1</link>"
                        "</item></channel></rss>"
                    ),
                    url="https://backup.example.com/feed.xml",
                )
            ],
        }
    )
    semaphore = asyncio.Semaphore(1)

    monkeypatch.setattr("data_layer.news_data.client.MAX_RETRIES", 2)
    monkeypatch.setattr("data_layer.news_data.client.RETRY_DELAY", 0)

    articles = asyncio.run(client._fetch_source(session, source, None, semaphore))

    assert len(articles) == 1
    assert articles[0].feed_url == "https://backup.example.com/feed.xml"
    assert articles[0].url == "https://backup.example.com/posts/1"
