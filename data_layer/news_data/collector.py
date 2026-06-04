import json
from datetime import datetime
from datetime import timedelta

from loguru import logger

from config.settings import NEWS_CONFIG
from database.db_manager import DBManager
from data_layer.news_data.client import NewsFeedClient
from data_layer.news_data.models import NewsArticle, NewsSource, utc_now_naive
from data_layer.news_data.sources import load_news_sources


class NewsCollector:
    """新闻采集器，负责抓取、筛选、去重和落库。"""

    def __init__(self, client: NewsFeedClient, db: DBManager):
        self.client = client
        self.db = db

    def _select_sources(
        self,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
        ) -> list[NewsSource]:
        return load_news_sources(
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )

    @staticmethod
    def _count_articles_by_source(
        articles: list[NewsArticle],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for article in articles:
            counts[article.source] = counts.get(article.source, 0) + 1
        return counts

    def _record_source_runs(
        self,
        sources: list[NewsSource],
        raw_articles: list[NewsArticle],
        filtered_articles: list[NewsArticle],
        deduped_articles: list[NewsArticle],
        hours: int | None,
        limit_per_source: int | None,
        categories: list[str] | None,
        tags: list[str] | None,
        source_groups: list[str] | None,
    ):
        stats_provider = getattr(self.client, "get_last_fetch_stats", None)
        raw_stats = stats_provider() if callable(stats_provider) else []
        stats_by_source = {
            str(item["source_name"]): item
            for item in raw_stats
        }
        raw_counts = self._count_articles_by_source(raw_articles)
        filtered_counts = self._count_articles_by_source(filtered_articles)
        deduped_counts = self._count_articles_by_source(deduped_articles)

        for source in sources:
            stat = stats_by_source.get(source.name, {})
            started_at = stat.get("started_at") or utc_now_naive().isoformat()
            finished_at = stat.get("finished_at") or utc_now_naive().isoformat()
            status = str(stat.get("status") or "").strip().lower()
            if not status:
                status = "success" if raw_counts.get(source.name, 0) > 0 else "empty"

            metadata = {
                "feed_url": source.feed_url,
                "source_group": source.source_group,
                "category": source.category,
                "tags": source.tags,
                "hours": hours,
                "limit_per_source": limit_per_source,
                "filter_categories": categories,
                "filter_tags": tags,
                "filter_source_groups": source_groups,
                "requested_feed_url": stat.get("requested_feed_url"),
                "effective_feed_url": stat.get("effective_feed_url"),
                "candidate_count": stat.get("candidate_count"),
                "raw_article_count": raw_counts.get(source.name, 0),
                "filtered_article_count": filtered_counts.get(source.name, 0),
                "deduped_article_count": deduped_counts.get(source.name, 0),
            }
            duration_seconds = None
            try:
                duration_seconds = (
                    NewsCollector._parse_iso_time(finished_at)
                    - NewsCollector._parse_iso_time(started_at)
                ).total_seconds()
            except Exception:
                duration_seconds = None

            self.db.record_collection_run(
                module_name="news_data",
                source_name=source.name,
                job_name="news_articles",
                status=status,
                item_count=filtered_counts.get(source.name, 0),
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
                message=stat.get("error"),
                metadata_json=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                commit=False,
            )
        if sources:
            self.db.commit()

    @staticmethod
    def _parse_iso_time(value: str):
        return datetime.fromisoformat(value)

    def fetch_recent_articles(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> list[NewsArticle]:
        sources = self._select_sources(
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        if not sources:
            logger.warning("没有可用的新闻源配置")
            return []

        articles = self.client.fetch_articles(
            sources=sources,
            limit_per_source=limit_per_source or NEWS_CONFIG["max_items_per_source"],
        )
        filtered = self._filter_articles_by_time(articles, hours=hours)
        deduped = self._deduplicate_articles(filtered)
        self._record_source_runs(
            sources=sources,
            raw_articles=articles,
            filtered_articles=filtered,
            deduped_articles=deduped,
            hours=hours,
            limit_per_source=limit_per_source,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        deduped.sort(
            key=lambda article: article.published_at or article.collected_at,
            reverse=True,
        )
        logger.info(f"本轮共获取 {len(deduped)} 条标准化新闻")
        return deduped

    async def fetch_recent_articles_async(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> list[NewsArticle]:
        sources = self._select_sources(
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        if not sources:
            logger.warning("没有可用的新闻源配置")
            return []

        articles = await self.client.fetch_articles_async(
            sources=sources,
            limit_per_source=limit_per_source or NEWS_CONFIG["max_items_per_source"],
        )
        filtered = self._filter_articles_by_time(articles, hours=hours)
        deduped = self._deduplicate_articles(filtered)
        self._record_source_runs(
            sources=sources,
            raw_articles=articles,
            filtered_articles=filtered,
            deduped_articles=deduped,
            hours=hours,
            limit_per_source=limit_per_source,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        deduped.sort(
            key=lambda article: article.published_at or article.collected_at,
            reverse=True,
        )
        logger.info(f"本轮共获取 {len(deduped)} 条标准化新闻")
        return deduped

    @staticmethod
    def _filter_articles_by_time(
        articles: list[NewsArticle],
        hours: int | None = None,
    ) -> list[NewsArticle]:
        if hours is None or hours <= 0:
            return articles

        cutoff = utc_now_naive() - timedelta(hours=hours)
        results: list[NewsArticle] = []
        for article in articles:
            article_time = article.published_at or article.collected_at
            if article_time >= cutoff:
                results.append(article)
        return results

    @staticmethod
    def _deduplicate_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
        deduped: dict[str, NewsArticle] = {}
        for article in articles:
            previous = deduped.get(article.url_hash)
            if previous is None:
                deduped[article.url_hash] = article
                continue

            deduped[article.url_hash] = NewsCollector._merge_articles(previous, article)
        return list(deduped.values())

    @staticmethod
    def _article_priority(article: NewsArticle) -> tuple:
        article_time = article.published_at or article.collected_at
        return (
            1 if article.content_text else 0,
            len(article.content_text or ""),
            1 if article.summary else 0,
            len(article.summary or ""),
            1 if article.author else 0,
            1 if article.image_url else 0,
            1 if article.external_id else 0,
            len(article.relevance_symbols),
            len(article.tags),
            article_time,
            article.collected_at,
        )

    @staticmethod
    def _merge_articles(previous: NewsArticle, current: NewsArticle) -> NewsArticle:
        if NewsCollector._article_priority(current) >= NewsCollector._article_priority(previous):
            primary = current
            secondary = previous
        else:
            primary = previous
            secondary = current

        return NewsArticle(
            source=primary.source or secondary.source,
            source_type=primary.source_type or secondary.source_type,
            feed_url=primary.feed_url or secondary.feed_url,
            category=primary.category or secondary.category,
            title=primary.title or secondary.title,
            summary=primary.summary or secondary.summary,
            content_text=primary.content_text or secondary.content_text,
            url=primary.url or secondary.url,
            url_hash=primary.url_hash,
            author=primary.author or secondary.author,
            published_at=primary.published_at or secondary.published_at,
            collected_at=max(primary.collected_at, secondary.collected_at),
            language=primary.language or secondary.language,
            relevance_symbols=NewsCollector._merge_strings(
                primary.relevance_symbols,
                secondary.relevance_symbols,
            ),
            tags=NewsCollector._merge_strings(primary.tags, secondary.tags),
            image_url=primary.image_url or secondary.image_url,
            external_id=primary.external_id or secondary.external_id,
            raw_payload_json=primary.raw_payload_json or secondary.raw_payload_json,
        )

    @staticmethod
    def _merge_strings(primary: list[str], secondary: list[str]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()
        for value in [*primary, *secondary]:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(normalized)
        return results

    def save_to_db(self, articles: list[NewsArticle]):
        if not articles:
            logger.warning("没有可保存的新闻数据")
            return

        sql = """
            INSERT INTO news_articles (
                source, source_type, feed_url, category, title, summary,
                content_text, url, url_hash, author, published_at, collected_at,
                language, sentiment_label, relevance_symbols, tags, image_url,
                external_id, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url_hash) DO UPDATE SET
                source = excluded.source,
                source_type = excluded.source_type,
                feed_url = excluded.feed_url,
                category = excluded.category,
                title = excluded.title,
                summary = COALESCE(excluded.summary, news_articles.summary),
                content_text = COALESCE(excluded.content_text, news_articles.content_text),
                url = excluded.url,
                author = COALESCE(excluded.author, news_articles.author),
                published_at = COALESCE(excluded.published_at, news_articles.published_at),
                collected_at = excluded.collected_at,
                language = excluded.language,
                relevance_symbols = excluded.relevance_symbols,
                tags = excluded.tags,
                image_url = COALESCE(excluded.image_url, news_articles.image_url),
                external_id = COALESCE(excluded.external_id, news_articles.external_id),
                raw_payload_json = excluded.raw_payload_json
            WHERE
                COALESCE(news_articles.source, '') <> COALESCE(excluded.source, '')
                OR COALESCE(news_articles.source_type, '') <> COALESCE(excluded.source_type, '')
                OR COALESCE(news_articles.feed_url, '') <> COALESCE(excluded.feed_url, '')
                OR COALESCE(news_articles.category, '') <> COALESCE(excluded.category, '')
                OR COALESCE(news_articles.title, '') <> COALESCE(excluded.title, '')
                OR COALESCE(news_articles.summary, '') <> COALESCE(excluded.summary, news_articles.summary, '')
                OR COALESCE(news_articles.content_text, '') <> COALESCE(excluded.content_text, news_articles.content_text, '')
                OR COALESCE(news_articles.url, '') <> COALESCE(excluded.url, '')
                OR COALESCE(news_articles.author, '') <> COALESCE(excluded.author, news_articles.author, '')
                OR COALESCE(CAST(news_articles.published_at AS TEXT), '') <> COALESCE(CAST(excluded.published_at AS TEXT), CAST(news_articles.published_at AS TEXT), '')
                OR COALESCE(news_articles.language, '') <> COALESCE(excluded.language, '')
                OR COALESCE(news_articles.relevance_symbols, '[]') <> COALESCE(excluded.relevance_symbols, '[]')
                OR COALESCE(news_articles.tags, '[]') <> COALESCE(excluded.tags, '[]')
                OR COALESCE(news_articles.image_url, '') <> COALESCE(excluded.image_url, news_articles.image_url, '')
                OR COALESCE(news_articles.external_id, '') <> COALESCE(excluded.external_id, news_articles.external_id, '')
        """
        params_list = [
            (
                article.source,
                article.source_type,
                article.feed_url,
                article.category,
                article.title,
                article.summary,
                article.content_text,
                article.url,
                article.url_hash,
                article.author,
                article.published_at.isoformat() if article.published_at else None,
                article.collected_at.isoformat(),
                article.language,
                None,
                json.dumps(article.relevance_symbols, ensure_ascii=False),
                json.dumps(article.tags, ensure_ascii=False),
                article.image_url,
                article.external_id,
                article.raw_payload_json,
            )
            for article in articles
        ]
        before_changes = self.db.conn.total_changes
        self.db.execute_many(sql, params_list)
        self.db.commit()
        written = self.db.conn.total_changes - before_changes
        logger.info(f"已写入/更新 {written} 条新闻到数据库（输入 {len(articles)} 条）")

    def collect(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> list[NewsArticle]:
        logger.info("开始采集新闻数据...")
        articles = self.fetch_recent_articles(
            hours=hours if hours is not None else NEWS_CONFIG["lookback_hours"],
            limit_per_source=limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        if articles:
            self.save_to_db(articles)
        logger.info("新闻数据采集完成")
        return articles

    async def collect_async(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> list[NewsArticle]:
        logger.info("开始采集新闻数据...")
        articles = await self.fetch_recent_articles_async(
            hours=hours if hours is not None else NEWS_CONFIG["lookback_hours"],
            limit_per_source=limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        if articles:
            self.save_to_db(articles)
        logger.info("新闻数据采集完成")
        return articles
