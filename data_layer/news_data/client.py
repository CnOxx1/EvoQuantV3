import asyncio
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import aiohttp
from loguru import logger

from config.settings import MAX_RETRIES, NEWS_CONFIG, PROXY_URL, RETRY_DELAY
from data_layer.news_data.models import NewsArticle, NewsSource, utc_now_naive


REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
TRACKED_ASSETS_FILE = REGISTRY_DIR / "tracked_assets.json"


def _default_tracked_asset_aliases() -> dict[str, list[str]]:
    return {
        "BTC": ["BTC", "BITCOIN"],
        "ETH": ["ETH", "ETHEREUM", "ETHER"],
        "SOL": ["SOL", "SOLANA"],
        "SUI": ["SUI"],
        "BNB": ["BNB", "BINANCE COIN"],
        "XRP": ["XRP", "RIPPLE"],
        "DOGE": ["DOGE", "DOGECOIN"],
        "ADA": ["ADA", "CARDANO"],
        "TRX": ["TRX", "TRON"],
        "TON": ["TONCOIN", "THE OPEN NETWORK"],
        "AVAX": ["AVAX", "AVALANCHE"],
        "LINK": ["CHAINLINK"],
        "ARB": ["ARBITRUM"],
        "OP": ["OPTIMISM"],
        "AAVE": ["AAVE"],
        "UNI": ["UNISWAP"],
        "LDO": ["LIDO", "LIDO DAO"],
        "SEI": ["SEI", "SEI NETWORK"],
        "TIA": ["CELESTIA", "TIA"],
        "PYTH": ["PYTH", "PYTH NETWORK"],
        "STRK": ["STARKNET", "STRK"],
        "DYDX": ["DYDX", "DYDX CHAIN"],
        "ENS": ["ENS", "ETHEREUM NAME SERVICE"],
        "DOT": ["POLKADOT"],
        "ATOM": ["COSMOS", "COSMOS HUB"],
        "OSMO": ["OSMOSIS"],
        "ZEC": ["ZCASH", "ZEC"],
        "1INCH": ["1INCH"],
        "SNX": ["SYNTHETIX", "SNX"],
        "EIGEN": ["EIGENLAYER", "EIGEN"],
        "GTC": ["GITCOIN", "GTC"],
        "COW": ["COW DAO", "COWSWAP"],
        "SAFE": ["SAFE WALLET", "SAFE FOUNDATION"],
        "ONDO": ["ONDO"],
        "ENA": ["ETHENA", "ENA"],
        "WLD": ["WORLDCOIN"],
        "USDT": ["USDT", "TETHER"],
        "USDC": ["USDC", "USD COIN"],
        "DAI": ["DAI", "MAKERDAO DAI", "SKY DOLLAR"],
        "FDUSD": ["FDUSD", "FIRST DIGITAL USD"],
    }


def _normalize_tracked_asset_aliases(
    payload: object,
) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        raise ValueError("tracked asset registry must be a JSON object")

    normalized: dict[str, list[str]] = {}
    for raw_symbol, raw_aliases in payload.items():
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol:
            continue
        if not isinstance(raw_aliases, list):
            raise ValueError(f"aliases for {symbol} must be a JSON array")
        aliases: list[str] = []
        seen_aliases: set[str] = set()
        for raw_alias in raw_aliases:
            alias = str(raw_alias or "").strip().upper()
            if not alias or alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            aliases.append(alias)
        if aliases:
            normalized[symbol] = aliases
    if not normalized:
        raise ValueError("tracked asset registry is empty")
    return normalized


def _load_tracked_asset_aliases() -> dict[str, list[str]]:
    default_aliases = _default_tracked_asset_aliases()
    if not TRACKED_ASSETS_FILE.exists():
        return default_aliases
    try:
        payload = json.loads(TRACKED_ASSETS_FILE.read_text(encoding="utf-8"))
        return _normalize_tracked_asset_aliases(payload)
    except Exception as exc:
        logger.warning(
            f"加载 tracked asset registry 失败，回退到内置别名表: {type(exc).__name__}: {exc}"
        )
        return default_aliases


TRACKED_ASSET_ALIASES = _load_tracked_asset_aliases()

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

RSS_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
    "atom": "http://www.w3.org/2005/Atom",
}


class _HTMLTextExtractor(HTMLParser):
    """轻量 HTML -> text 提取器。"""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str):
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return " ".join(self.parts)


@dataclass
class _SourceHealthState:
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None
    last_error: str | None = None


@dataclass
class _SourceFetchStat:
    source_name: str
    status: str
    article_count: int
    started_at: datetime
    finished_at: datetime
    requested_feed_url: str
    effective_feed_url: str | None = None
    error: str | None = None
    candidate_count: int = 1


class NewsFeedClient:
    """RSS / Atom 新闻抓取客户端。"""

    def __init__(self):
        self.timeout_seconds = NEWS_CONFIG["timeout_seconds"]
        self.user_agent = NEWS_CONFIG["user_agent"]
        self.proxy = PROXY_URL
        self.fetch_concurrency = max(1, NEWS_CONFIG["fetch_concurrency"])
        self.max_connections_per_host = max(1, NEWS_CONFIG["max_connections_per_host"])
        self.resolver_mode = NEWS_CONFIG["resolver_mode"] or "auto"
        self.source_failure_threshold = max(1, NEWS_CONFIG["source_failure_threshold"])
        self.source_cooldown_base_seconds = max(
            1,
            NEWS_CONFIG["source_cooldown_base_seconds"],
        )
        self.source_cooldown_max_seconds = max(
            self.source_cooldown_base_seconds,
            NEWS_CONFIG["source_cooldown_max_seconds"],
        )
        self._source_health: dict[str, _SourceHealthState] = {}
        self._source_health_lock = threading.Lock()
        self._last_fetch_stats: dict[str, _SourceFetchStat] = {}
        self._last_fetch_stats_lock = threading.Lock()

    def fetch_articles(
        self,
        sources: list[NewsSource],
        limit_per_source: int | None = None,
    ) -> list[NewsArticle]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.fetch_articles_async(
                    sources=sources,
                    limit_per_source=limit_per_source,
                )
            )
        raise RuntimeError(
            "NewsFeedClient.fetch_articles() 不能在已有事件循环中调用，"
            "请改用 await fetch_articles_async(...)。"
        )

    async def fetch_articles_async(
        self,
        sources: list[NewsSource],
        limit_per_source: int | None = None,
    ) -> list[NewsArticle]:
        return await self._fetch_articles_async(
            sources=sources,
            limit_per_source=limit_per_source,
        )

    async def _fetch_articles_async(
        self,
        sources: list[NewsSource],
        limit_per_source: int | None,
    ) -> list[NewsArticle]:
        self._clear_last_fetch_stats()
        runnable_sources = self._select_runnable_sources(sources)
        if not runnable_sources:
            logger.warning("本轮新闻源全部处于冷却期，跳过采集")
            return []

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {"User-Agent": self.user_agent}
        semaphore = asyncio.Semaphore(self.fetch_concurrency)
        connector = self._build_connector()
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
        ) as session:
            tasks = [
                self._fetch_source(session, source, limit_per_source, semaphore)
                for source in runnable_sources
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        articles: list[NewsArticle] = []
        for source, result in zip(runnable_sources, results, strict=False):
            if isinstance(result, Exception):
                now = utc_now_naive()
                self._store_fetch_stat(
                    _SourceFetchStat(
                        source_name=source.name,
                        status="error",
                        article_count=0,
                        started_at=now,
                        finished_at=now,
                        requested_feed_url=source.feed_url,
                        error=f"unexpected task error: {type(result).__name__}: {result}",
                        candidate_count=len(self._candidate_feed_urls(source)),
                    )
                )
                self._record_source_failure(
                    source,
                    f"unexpected task error: {type(result).__name__}: {result}",
                )
                logger.error(f"抓取新闻源失败 [{source.name}]: {result}")
                continue
            articles.extend(result)
        return articles

    async def _fetch_source(
        self,
        session: aiohttp.ClientSession,
        source: NewsSource,
        limit_per_source: int | None,
        semaphore: asyncio.Semaphore,
    ) -> list[NewsArticle]:
        started_at = utc_now_naive()
        candidate_count = len(self._candidate_feed_urls(source))
        async with semaphore:
            download_result = await self._download_feed(session, source)
            if not download_result:
                finished_at = utc_now_naive()
                self._store_fetch_stat(
                    _SourceFetchStat(
                        source_name=source.name,
                        status="error",
                        article_count=0,
                        started_at=started_at,
                        finished_at=finished_at,
                        requested_feed_url=source.feed_url,
                        error="download failed after all retries",
                        candidate_count=candidate_count,
                    )
                )
                self._record_source_failure(source, "download failed after all retries")
                return []

        payload, effective_feed_url = download_result
        collected_at = utc_now_naive()
        active_source = source.model_copy(update={"feed_url": effective_feed_url})
        try:
            articles = self._parse_feed(
                source=active_source,
                payload=payload,
                collected_at=collected_at,
                limit_per_source=limit_per_source,
            )
            self._store_fetch_stat(
                _SourceFetchStat(
                    source_name=source.name,
                    status="success",
                    article_count=len(articles),
                    started_at=started_at,
                    finished_at=utc_now_naive(),
                    requested_feed_url=source.feed_url,
                    effective_feed_url=effective_feed_url,
                    candidate_count=candidate_count,
                )
            )
            self._record_source_success(source)
            return articles
        except Exception as exc:
            finished_at = utc_now_naive()
            self._store_fetch_stat(
                _SourceFetchStat(
                    source_name=source.name,
                    status="error",
                    article_count=0,
                    started_at=started_at,
                    finished_at=finished_at,
                    requested_feed_url=source.feed_url,
                    effective_feed_url=effective_feed_url,
                    error=f"parse error: {type(exc).__name__}: {exc}",
                    candidate_count=candidate_count,
                )
            )
            self._record_source_failure(
                source,
                f"parse error: {type(exc).__name__}: {exc}",
            )
            logger.error(f"解析新闻源失败 [{source.name}]: {exc}")
            return []

    async def _download_feed(
        self,
        session: aiohttp.ClientSession,
        source: NewsSource,
    ) -> tuple[str, str] | None:
        candidate_urls = self._candidate_feed_urls(source)
        total_candidates = len(candidate_urls)
        previous_feed_url: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            candidate_index = (attempt - 1) % total_candidates
            feed_url = candidate_urls[candidate_index]
            if previous_feed_url and feed_url != previous_feed_url:
                logger.warning(
                    f"本轮重试切换 feed 地址 [{source.name}]: "
                    f"{previous_feed_url} -> {feed_url}"
                )
            try:
                async with session.get(feed_url, proxy=self.proxy) as response:
                    response.raise_for_status()
                    payload = await response.text()
                    resolved_feed_url = str(response.url)
                    if feed_url != source.feed_url or resolved_feed_url != source.feed_url:
                        logger.info(
                            f"新闻源使用回退/规范化地址 [{source.name}] "
                            f"{source.feed_url} -> {resolved_feed_url}"
                        )
                    return payload, resolved_feed_url
            except Exception as exc:
                logger.warning(
                    f"下载新闻源失败 [{source.name}] "
                    f"(第{attempt}/{MAX_RETRIES}次, 候选{candidate_index + 1}/{total_candidates}, "
                    f"url={feed_url}): {exc}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * attempt)
            previous_feed_url = feed_url
        return None

    def _build_connector(self) -> aiohttp.TCPConnector:
        resolver = None
        if self.resolver_mode == "threaded":
            resolver = aiohttp.ThreadedResolver()
        elif self.resolver_mode == "async":
            resolver = aiohttp.AsyncResolver()
        elif self.resolver_mode != "auto":
            logger.warning(
                f"未知 NEWS_RESOLVER_MODE={self.resolver_mode}，回退到 aiohttp 默认 resolver"
            )

        return aiohttp.TCPConnector(
            resolver=resolver,
            limit_per_host=self.max_connections_per_host,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

    def _select_runnable_sources(
        self,
        sources: list[NewsSource],
        now: datetime | None = None,
    ) -> list[NewsSource]:
        current_time = now or self._utc_now()
        runnable_sources: list[NewsSource] = []
        for source in sources:
            if self._is_source_in_cooldown(source, now=current_time):
                current_time_naive = current_time.astimezone(timezone.utc).replace(
                    tzinfo=None
                )
                self._store_fetch_stat(
                    _SourceFetchStat(
                        source_name=source.name,
                        status="cooldown",
                        article_count=0,
                        started_at=current_time_naive,
                        finished_at=current_time_naive,
                        requested_feed_url=source.feed_url,
                        error="source in cooldown",
                        candidate_count=len(self._candidate_feed_urls(source)),
                    )
                )
                continue
            runnable_sources.append(source)
        return runnable_sources

    def _is_source_in_cooldown(
        self,
        source: NewsSource,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or self._utc_now()
        with self._source_health_lock:
            state = self._source_health.get(self._source_key(source))
            if state is None or state.cooldown_until is None:
                return False

            if state.cooldown_until <= current_time:
                state.cooldown_until = None
                return False

            remaining_seconds = max(
                int((state.cooldown_until - current_time).total_seconds()),
                1,
            )
            logger.warning(
                f"新闻源处于冷却期，暂时跳过 [{source.name}] "
                f"remaining={remaining_seconds}s failures={state.consecutive_failures}"
            )
            return True

    def _record_source_failure(self, source: NewsSource, error: str):
        key = self._source_key(source)
        with self._source_health_lock:
            state = self._source_health.setdefault(key, _SourceHealthState())
            state.consecutive_failures += 1
            state.last_error = error

            if state.consecutive_failures < self.source_failure_threshold:
                logger.warning(
                    f"新闻源失败计数增加 [{source.name}] "
                    f"failures={state.consecutive_failures}/{self.source_failure_threshold} "
                    f"error={error}"
                )
                return

            cooldown_multiplier = 2 ** (
                state.consecutive_failures - self.source_failure_threshold
            )
            cooldown_seconds = min(
                self.source_cooldown_base_seconds * cooldown_multiplier,
                self.source_cooldown_max_seconds,
            )
            state.cooldown_until = self._utc_now() + timedelta(seconds=cooldown_seconds)

            logger.warning(
                f"新闻源进入冷却期 [{source.name}] "
                f"failures={state.consecutive_failures} cooldown={cooldown_seconds}s "
                f"error={error}"
            )

    def _record_source_success(self, source: NewsSource):
        key = self._source_key(source)
        with self._source_health_lock:
            state = self._source_health.get(key)
            if state is None:
                return

            if state.consecutive_failures <= 0 and state.cooldown_until is None:
                return

            previous_failures = state.consecutive_failures
            self._source_health.pop(key, None)

        logger.info(
            f"新闻源恢复成功，清除失败状态 [{source.name}] "
            f"previous_failures={previous_failures}"
        )

    def _clear_last_fetch_stats(self):
        with self._last_fetch_stats_lock:
            self._last_fetch_stats = {}

    def _store_fetch_stat(self, stat: _SourceFetchStat):
        with self._last_fetch_stats_lock:
            self._last_fetch_stats[stat.source_name.strip().lower()] = stat

    def get_last_fetch_stats(self) -> list[dict]:
        with self._last_fetch_stats_lock:
            stats = list(self._last_fetch_stats.values())
        stats.sort(key=lambda item: item.source_name.lower())
        return [
            {
                "source_name": stat.source_name,
                "status": stat.status,
                "article_count": stat.article_count,
                "started_at": stat.started_at.isoformat(),
                "finished_at": stat.finished_at.isoformat(),
                "requested_feed_url": stat.requested_feed_url,
                "effective_feed_url": stat.effective_feed_url,
                "error": stat.error,
                "candidate_count": stat.candidate_count,
            }
            for stat in stats
        ]

    def describe_source_health(
        self,
        sources: list[NewsSource] | None = None,
    ) -> list[dict]:
        selected_sources = sources or []
        if not selected_sources:
            return []

        current_time = self._utc_now()
        rows: list[dict] = []
        with self._source_health_lock:
            for source in selected_sources:
                state = self._source_health.get(self._source_key(source))
                cooldown_until = state.cooldown_until if state else None
                rows.append(
                    {
                        "source_name": source.name,
                        "consecutive_failures": state.consecutive_failures if state else 0,
                        "cooldown_until": (
                            cooldown_until.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
                            if cooldown_until is not None
                            else None
                        ),
                        "last_error": state.last_error if state else None,
                        "in_cooldown": bool(
                            cooldown_until is not None and cooldown_until > current_time
                        ),
                    }
                )
        rows.sort(key=lambda item: item["source_name"].lower())
        return rows

    @staticmethod
    def _candidate_feed_urls(source: NewsSource) -> list[str]:
        ordered_urls = [source.feed_url, *source.fallback_feed_urls]
        seen: set[str] = set()
        results: list[str] = []
        for value in ordered_urls:
            url = value.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            results.append(url)
        return results

    @staticmethod
    def _source_key(source: NewsSource) -> str:
        return source.name.strip().lower()

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    def _parse_feed(
        self,
        source: NewsSource,
        payload: str,
        collected_at: datetime,
        limit_per_source: int | None,
    ) -> list[NewsArticle]:
        root = ET.fromstring(payload)
        root_tag = self._local_name(root.tag)
        if root_tag == "rss":
            items = self._parse_rss(source, root, collected_at, source_type="rss")
        elif root_tag == "feed":
            items = self._parse_atom(source, root, collected_at, source_type="atom")
        else:
            raise ValueError(f"不支持的 feed 根节点: {root.tag}")

        if limit_per_source is not None and limit_per_source > 0:
            return items[:limit_per_source]
        return items

    def _parse_rss(
        self,
        source: NewsSource,
        root: ET.Element,
        collected_at: datetime,
        source_type: str,
    ) -> list[NewsArticle]:
        channel = root.find("channel")
        if channel is None:
            return []

        articles: list[NewsArticle] = []
        for item in channel.findall("item"):
            title = self._safe_text(item.find("title"))
            link = self._safe_text(item.find("link"))
            guid = self._safe_text(item.find("guid"))
            summary_html = self._safe_text(item.find("description"))
            content_html = self._safe_text(item.find("content:encoded", RSS_NAMESPACES))
            author = self._safe_text(item.find("dc:creator", RSS_NAMESPACES))
            if not author:
                author = self._safe_text(item.find("author"))

            categories = [
                text
                for text in (
                    self._safe_text(category_node)
                    for category_node in item.findall("category")
                )
                if text
            ]
            published_at = self._parse_datetime(self._safe_text(item.find("pubDate")))
            image_url = self._find_rss_image(item, content_html or summary_html)

            article = self._build_article(
                source=source,
                title=title,
                link=link,
                external_id=guid,
                summary_html=summary_html,
                content_html=content_html,
                author=author,
                categories=categories,
                published_at=published_at,
                collected_at=collected_at,
                image_url=image_url,
                source_type=source_type,
            )
            if article:
                articles.append(article)

        return articles

    def _parse_atom(
        self,
        source: NewsSource,
        root: ET.Element,
        collected_at: datetime,
        source_type: str,
    ) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for entry in root.findall("atom:entry", RSS_NAMESPACES):
            title = self._safe_text(entry.find("atom:title", RSS_NAMESPACES))
            link = self._resolve_atom_link(entry)
            external_id = self._safe_text(entry.find("atom:id", RSS_NAMESPACES))
            summary_html = self._safe_markup(entry.find("atom:summary", RSS_NAMESPACES))
            content_html = self._safe_markup(entry.find("atom:content", RSS_NAMESPACES))

            author = None
            author_node = entry.find("atom:author", RSS_NAMESPACES)
            if author_node is not None:
                author = self._safe_text(author_node.find("atom:name", RSS_NAMESPACES))

            categories = [
                node.attrib["term"].strip()
                for node in entry.findall("atom:category", RSS_NAMESPACES)
                if node.attrib.get("term")
            ]
            published_at = self._parse_datetime(
                self._safe_text(entry.find("atom:published", RSS_NAMESPACES))
                or self._safe_text(entry.find("atom:updated", RSS_NAMESPACES))
            )
            image_url = self._find_atom_image(entry, content_html or summary_html)

            article = self._build_article(
                source=source,
                title=title,
                link=link,
                external_id=external_id,
                summary_html=summary_html,
                content_html=content_html,
                author=author,
                categories=categories,
                published_at=published_at,
                collected_at=collected_at,
                image_url=image_url,
                source_type=source_type,
            )
            if article:
                articles.append(article)

        return articles

    def _build_article(
        self,
        source: NewsSource,
        title: str | None,
        link: str | None,
        external_id: str | None,
        summary_html: str | None,
        content_html: str | None,
        author: str | None,
        categories: list[str],
        published_at: datetime | None,
        collected_at: datetime,
        image_url: str | None,
        source_type: str,
    ) -> NewsArticle | None:
        if not title or not link:
            return None

        canonical_url = self._canonicalize_url(link, base_url=source.feed_url)
        if not canonical_url:
            return None

        summary_text = self._html_to_text(summary_html)
        content_text = self._html_to_text(content_html or summary_html)
        tags = self._unique_strings([*source.tags, *categories])
        symbols = self._extract_symbols(" ".join(filter(None, [title, summary_text, content_text])))
        raw_payload_json = json.dumps(
            {
                "title": title,
                "link": canonical_url,
                "external_id": external_id,
                "summary_html": summary_html,
                "content_html": content_html,
                "author": author,
                "categories": categories,
                "published_at": published_at.isoformat() if published_at else None,
                "image_url": image_url,
            },
            ensure_ascii=False,
        )

        return NewsArticle(
            source=source.name,
            source_type=source_type,
            feed_url=source.feed_url,
            category=source.category or (categories[0] if categories else None),
            title=title.strip(),
            summary=summary_text,
            content_text=content_text,
            url=canonical_url,
            url_hash=self._hash_url(canonical_url),
            author=author,
            published_at=published_at,
            collected_at=collected_at,
            language=source.language,
            relevance_symbols=symbols,
            tags=tags,
            image_url=image_url,
            external_id=external_id,
            raw_payload_json=raw_payload_json,
        )

    @staticmethod
    def _safe_text(node: ET.Element | None) -> str | None:
        if node is None:
            return None
        parts = [
            fragment.strip()
            for fragment in node.itertext()
            if fragment and fragment.strip()
        ]
        if not parts:
            return None
        return " ".join(parts)

    @staticmethod
    def _safe_markup(node: ET.Element | None) -> str | None:
        if node is None:
            return None
        if not list(node):
            return NewsFeedClient._safe_text(node)

        fragments: list[str] = []
        if node.text and node.text.strip():
            fragments.append(node.text.strip())
        fragments.extend(
            ET.tostring(child, encoding="unicode")
            for child in list(node)
        )
        markup = "".join(fragments).strip()
        return markup or None

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        text = value.strip()

        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError, IndexError):
            pass

        candidates = [
            text,
            text.replace("Z", "+00:00"),
        ]
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
        return None

    @staticmethod
    def _html_to_text(value: str | None) -> str | None:
        if not value:
            return None
        parser = _HTMLTextExtractor()
        parser.feed(value)
        text = unescape(parser.get_text())
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    @staticmethod
    def _hash_url(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonicalize_url(url: str | None, base_url: str | None = None) -> str | None:
        if not url:
            return None
        raw = url.strip()
        if not raw:
            return None
        if base_url:
            raw = urljoin(base_url, raw)
        split_result = urlsplit(raw)
        if split_result.scheme and split_result.scheme.lower() not in {"http", "https"}:
            return None
        if not split_result.netloc:
            return raw

        query_items = sorted(
            [
                (key, value)
                for key, value in parse_qsl(split_result.query, keep_blank_values=True)
                if key.lower() not in TRACKING_QUERY_KEYS
            ],
            key=lambda item: item[0],
        )
        path = split_result.path.rstrip("/") or "/"
        scheme = split_result.scheme.lower() or "https"
        hostname = (split_result.hostname or "").lower()
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"

        userinfo = ""
        if split_result.username:
            userinfo = split_result.username
            if split_result.password:
                userinfo = f"{userinfo}:{split_result.password}"
            userinfo = f"{userinfo}@"

        port = split_result.port
        if port and not (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            netloc = f"{userinfo}{hostname}:{port}"
        else:
            netloc = f"{userinfo}{hostname}"

        return urlunsplit((
            scheme,
            netloc,
            path,
            urlencode(query_items, doseq=True),
            "",
        ))

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(normalized)
        return results

    @staticmethod
    def _extract_symbols(text: str) -> list[str]:
        if not text:
            return []

        upper_text = text.upper()
        matches: list[tuple[int, str]] = []
        for symbol, aliases in TRACKED_ASSET_ALIASES.items():
            earliest_match_start = None
            for alias in aliases:
                pattern = rf"(?<![A-Z0-9]){re.escape(alias)}(?![A-Z0-9])"
                matched = re.search(pattern, upper_text)
                if matched is None:
                    continue
                if earliest_match_start is None or matched.start() < earliest_match_start:
                    earliest_match_start = matched.start()
            if earliest_match_start is not None:
                matches.append((earliest_match_start, symbol))
        matches.sort(key=lambda item: (item[0], item[1]))
        return [symbol for _, symbol in matches]

    @staticmethod
    def _extract_image_url_from_html(content_html: str | None) -> str | None:
        if not content_html:
            return None
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _find_rss_image(self, item: ET.Element, content_html: str | None) -> str | None:
        media_content = item.find("media:content", RSS_NAMESPACES)
        if media_content is not None and media_content.attrib.get("url"):
            return media_content.attrib["url"].strip()

        media_thumbnail = item.find("media:thumbnail", RSS_NAMESPACES)
        if media_thumbnail is not None and media_thumbnail.attrib.get("url"):
            return media_thumbnail.attrib["url"].strip()

        enclosure = item.find("enclosure")
        if enclosure is not None and enclosure.attrib.get("url"):
            return enclosure.attrib["url"].strip()

        return self._extract_image_url_from_html(content_html)

    def _find_atom_image(self, entry: ET.Element, content_html: str | None) -> str | None:
        media_content = entry.find("media:content", RSS_NAMESPACES)
        if media_content is not None and media_content.attrib.get("url"):
            return media_content.attrib["url"].strip()

        for link_node in entry.findall("atom:link", RSS_NAMESPACES):
            if link_node.attrib.get("rel") == "enclosure" and link_node.attrib.get("href"):
                return link_node.attrib["href"].strip()

        return self._extract_image_url_from_html(content_html)

    @staticmethod
    def _resolve_atom_link(entry: ET.Element) -> str | None:
        candidates: dict[str, list[str]] = {
            "alternate": [],
            "": [],
            "self": [],
        }
        for link_node in entry.findall("atom:link", RSS_NAMESPACES):
            href = link_node.attrib.get("href")
            rel = link_node.attrib.get("rel", "alternate").strip().lower()
            if href and rel in candidates:
                candidates[rel].append(href.strip())
        for rel in ("alternate", "", "self"):
            if candidates[rel]:
                return candidates[rel][0]
        return None
