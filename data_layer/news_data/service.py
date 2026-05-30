import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from config.settings import NEWS_CONFIG
from database.db_manager import DBManager
from data_layer.data_quality import resolve_source_health_status, summarize_health_rows
from data_layer.news_data.client import NewsFeedClient, TRACKED_ASSET_ALIASES
from data_layer.news_data.collector import NewsCollector
from data_layer.news_data.sources import load_news_sources


class NewsDataService:
    """新闻数据模块统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    HIGH_FREQUENCY_SOURCE_GROUPS = {"core_media", "market_intelligence"}
    AI_READY_MIN_CONTENT_TEXT_COVERAGE_RATIO = 0.5
    MINIMUM_TRACKED_ASSET_COUNT_FOR_MARKET_BREADTH = 20
    TRACKED_ASSET_MARKET_ROLE_GROUPS = {
        "core_majors": {
            "BTC",
            "ETH",
            "SOL",
            "SUI",
            "BNB",
            "XRP",
            "DOGE",
            "ADA",
            "TRX",
            "TON",
            "AVAX",
            "LINK",
        },
        "ecosystem_beta": {
            "ARB",
            "OP",
            "AAVE",
            "UNI",
            "LDO",
            "SEI",
            "TIA",
            "PYTH",
            "STRK",
            "DYDX",
            "ENS",
            "DOT",
            "ATOM",
            "OSMO",
            "ZEC",
            "1INCH",
            "SNX",
            "EIGEN",
            "GTC",
            "COW",
            "SAFE",
            "ONDO",
            "ENA",
            "WLD",
        },
        "stablecoins": {"USDT", "USDC", "DAI", "FDUSD"},
    }
    MINIMUM_TRACKED_ASSET_GROUP_COUNTS_FOR_MARKET_BREADTH = {
        "core_majors": 6,
        "ecosystem_beta": 8,
        "stablecoins": 3,
    }

    def __init__(
        self,
        client: NewsFeedClient | None = None,
        db: DBManager | None = None,
        collector: NewsCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or NewsFeedClient()
        self.collector = collector or NewsCollector(self.client, self.db)

    def init_storage(self):
        self.db.init_market_data_tables()

    def collect_once(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ):
        return self.collector.collect(
            hours=hours,
            limit_per_source=limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )

    async def collect_once_async(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ):
        return await self.collector.collect_async(
            hours=hours,
            limit_per_source=limit_per_source,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )

    def describe_sources(
        self,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> list[dict]:
        return [
            {
                "name": source.name,
                "feed_url": source.feed_url,
                "fallback_feed_urls": source.fallback_feed_urls,
                "category": source.category,
                "source_group": source.source_group,
                "language": source.language,
                "enabled": source.enabled,
                "tags": source.tags,
            }
            for source in load_news_sources(
                source_names=source_names,
                categories=categories,
                tags=tags,
                source_groups=source_groups,
                enabled_only=False,
            )
        ]

    @staticmethod
    def _append_unique(values: list[str], value: str | None):
        text = str(value or "").strip()
        if text and text not in values:
            values.append(text)

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _normalized_source_group(value: str | None) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _count_articles_by_source(rows: list[dict]) -> dict[str, int]:
        counter: Counter = Counter()
        for row in rows:
            counter[str(row["source"])] += 1
        return dict(
            sorted(
                counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        )

    @staticmethod
    def _ai_ready_source_names(coverage_rows: list[dict]) -> set[str]:
        return {
            str(row["source_name"])
            for row in coverage_rows
            if row.get("is_ready_for_ai")
        }

    @classmethod
    def _build_ai_excluded_sources(
        cls,
        *,
        raw_rows: list[dict],
        coverage_rows: list[dict],
    ) -> list[dict]:
        raw_rows_by_source: dict[str, list[dict]] = {}
        for row in raw_rows:
            raw_rows_by_source.setdefault(str(row["source"]), []).append(row)

        excluded: list[dict] = []
        for coverage_row in coverage_rows:
            source_name = str(coverage_row["source_name"])
            source_rows = raw_rows_by_source.get(source_name) or []
            if not source_rows or coverage_row.get("is_ready_for_ai"):
                continue
            excluded.append(
                {
                    "source_name": source_name,
                    "source_group": coverage_row.get("source_group"),
                    "category": coverage_row.get("category"),
                    "excluded_reason": cls.AI_EXCLUDED_SOURCE_REASON,
                    "raw_article_count": len(source_rows),
                    "raw_articles_with_summary_count": sum(
                        1
                        for row in source_rows
                        if str(row.get("summary") or "").strip()
                    ),
                    "raw_articles_with_content_text_count": sum(
                        1
                        for row in source_rows
                        if str(row.get("content_text") or "").strip()
                    ),
                    "raw_latest_article_time": max(
                        (
                            row["effective_time"]
                            for row in source_rows
                            if row.get("effective_time")
                        ),
                        default=None,
                    ),
                    "raw_relevance_symbols": sorted(
                        {
                            str(symbol).strip().upper()
                            for row in source_rows
                            for symbol in (row.get("relevance_symbols_list") or [])
                            if str(symbol).strip()
                        }
                    ),
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    def _is_high_frequency_source_group(self, value: str | None) -> bool:
        return self._normalized_source_group(value) in self.HIGH_FREQUENCY_SOURCE_GROUPS

    def _coverage_expectation_for_source(self, source) -> str:
        if self._is_high_frequency_source_group(source.source_group):
            return "continuous_newsflow"
        return "event_driven_reference"

    def _recommended_recent_articles(self, source) -> int:
        source_group = self._normalized_source_group(source.source_group)
        if source_group == "core_media":
            return 2
        if source_group == "market_intelligence":
            return 1
        return 0

    def _article_count_for_health(self, source, total_articles: int, recent_articles: int) -> int:
        if self._recommended_recent_articles(source) > 0:
            return recent_articles
        return total_articles

    def _is_source_ready_for_ai(
        self,
        *,
        source,
        health_status: str,
        recent_articles: int,
        recent_articles_with_content_text: int,
        recent_articles_with_relevance_symbols: int,
    ) -> bool:
        if health_status != "ready":
            return False
        recommended_recent_articles = self._recommended_recent_articles(source)
        if recommended_recent_articles > 0:
            if recent_articles < recommended_recent_articles:
                return False
            if recent_articles_with_relevance_symbols <= 0:
                return False
            content_ratio = (
                recent_articles_with_content_text / recent_articles
                if recent_articles > 0
                else 0.0
            )
            if content_ratio < self.AI_READY_MIN_CONTENT_TEXT_COVERAGE_RATIO:
                return False
            return True
        return True

    def _build_quality_flags_and_notes(
        self,
        *,
        source,
        hours: int,
        configuration_ready: bool,
        total_articles: int,
        recent_articles: int,
        recent_articles_with_content_text: int,
        recent_articles_with_relevance_symbols: int,
        is_stale: bool,
        in_cooldown: bool,
        consecutive_failures: int,
        last_article_age_seconds: float | None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []
        recommended_recent_articles = self._recommended_recent_articles(source)
        coverage_expectation = self._coverage_expectation_for_source(source)

        if not configuration_ready:
            self._append_unique(flags, "unconfigured_source")
            self._append_unique(notes, "当前新闻源没有可用 feed 地址，无法提供真实新闻样本。")
        if total_articles <= 0:
            self._append_unique(flags, "no_historical_articles")
            self._append_unique(notes, "该新闻源还没有任何历史文章入库，AI 无法从这个来源获得文本证据。")
        if is_stale:
            self._append_unique(flags, "stale_source")
            self._append_unique(notes, "最近一次新闻采集已超过调度容忍窗口，这路文本数据不应视为当前有效。")
        if in_cooldown:
            self._append_unique(flags, "source_in_cooldown")
            self._append_unique(notes, "该新闻源当前处于失败冷却期，短期内不会继续抓取。")
        if consecutive_failures > 0:
            self._append_unique(flags, "consecutive_failures_present")
            self._append_unique(notes, "该新闻源近期出现连续失败，需要关注上游可用性和解析稳定性。")

        if recommended_recent_articles > 0:
            if recent_articles <= 0:
                self._append_unique(flags, "no_recent_articles")
                self._append_unique(
                    notes,
                    f"该连续新闻流在最近 {hours} 小时内没有新增文章，AI 当前事件感知会缺少这一路输入。",
                )
            elif recent_articles < recommended_recent_articles:
                self._append_unique(flags, "recent_articles_thin")
                self._append_unique(
                    notes,
                    f"最近 {hours} 小时仅入库 {recent_articles} 条文章，低于该类新闻源建议覆盖阈值 {recommended_recent_articles} 条。",
                )
            if recent_articles > 0 and recent_articles_with_relevance_symbols <= 0:
                self._append_unique(flags, "relevance_symbol_coverage_missing")
                self._append_unique(
                    notes,
                    "最近这一路新闻虽然有更新，但没有任何文章命中已跟踪资产标签，AI 很难把文本快速映射到可交易对象。",
                )
            if recent_articles > 0:
                content_ratio = recent_articles_with_content_text / recent_articles
                if content_ratio < self.AI_READY_MIN_CONTENT_TEXT_COVERAGE_RATIO:
                    self._append_unique(flags, "content_text_coverage_thin")
                    self._append_unique(
                        notes,
                        "最近这一路连续新闻流正文可用比例偏低，AI 更多只能依赖标题和摘要做判断。",
                    )
        elif recent_articles <= 0 and total_articles > 0:
            self._append_unique(
                notes,
                "该类来源偏事件驱动或低频参考，没有最近文章不一定表示采集异常，但当前也没有新增文本证据。",
            )

        if coverage_expectation == "event_driven_reference":
            self._append_unique(
                notes,
                "这类来源更适合作为监管、治理、公告和研究补充证据，不应替代连续新闻流。",
            )

        if last_article_age_seconds is not None and recommended_recent_articles <= 0:
            if last_article_age_seconds > 30 * 24 * 3600:
                self._append_unique(flags, "reference_source_quiet")
                self._append_unique(
                    notes,
                    "该低频参考源最近一篇文章已经超过 30 天，AI 近期不会从这一路获得新的公告类证据。",
                )
        return flags, notes

    @staticmethod
    def _recent_article_ratio(total_articles: int, recent_articles: int) -> float:
        if total_articles <= 0:
            return 0.0
        return round(recent_articles / total_articles, 4)

    def _age_seconds(self, now: datetime, value: str | None) -> float | None:
        parsed = self._parse_timestamp(value)
        if parsed is None:
            return None
        return max((now - parsed).total_seconds(), 0.0)

    @staticmethod
    def _loads_json(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _loads_string_list(cls, value: str | None) -> list[str]:
        payload = cls._loads_json(value)
        if not isinstance(payload, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in payload:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    @classmethod
    def _build_configured_universe_summary(cls) -> dict[str, object]:
        tracked_symbols = sorted(
            {
                str(symbol or "").strip().upper()
                for symbol in TRACKED_ASSET_ALIASES
                if str(symbol or "").strip()
            }
        )
        tracked_symbol_set = set(tracked_symbols)
        tracked_symbols_by_group: dict[str, list[str]] = {}
        market_role_counts: dict[str, int] = {}
        grouped_symbols: set[str] = set()
        for group_name, candidate_symbols in cls.TRACKED_ASSET_MARKET_ROLE_GROUPS.items():
            covered_symbols = sorted(tracked_symbol_set & set(candidate_symbols))
            tracked_symbols_by_group[group_name] = covered_symbols
            market_role_counts[group_name] = len(covered_symbols)
            grouped_symbols.update(covered_symbols)
        ungrouped_symbols = sorted(tracked_symbol_set - grouped_symbols)
        missing_market_role_groups = [
            group_name
            for group_name, minimum_count in (
                cls.MINIMUM_TRACKED_ASSET_GROUP_COUNTS_FOR_MARKET_BREADTH.items()
            )
            if int(market_role_counts.get(group_name) or 0) < int(minimum_count)
        ]
        breadth_status = (
            "sufficient"
            if (
                len(tracked_symbols) >= cls.MINIMUM_TRACKED_ASSET_COUNT_FOR_MARKET_BREADTH
                and not missing_market_role_groups
            )
            else "limited"
        )
        return {
            "scope_kind": "default",
            "tracked_symbols": tracked_symbols,
            "tracked_symbols_by_group": tracked_symbols_by_group,
            "ungrouped_symbols": ungrouped_symbols,
            "asset_count": len(tracked_symbols),
            "market_role_counts": market_role_counts,
            "minimum_asset_count_for_market_breadth": (
                cls.MINIMUM_TRACKED_ASSET_COUNT_FOR_MARKET_BREADTH
            ),
            "minimum_market_role_counts_for_market_breadth": dict(
                cls.MINIMUM_TRACKED_ASSET_GROUP_COUNTS_FOR_MARKET_BREADTH
            ),
            "missing_market_role_groups": missing_market_role_groups,
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": breadth_status == "sufficient",
        }

    def _article_effective_time(self, row: dict) -> datetime | None:
        return self._parse_timestamp(row.get("published_at")) or self._parse_timestamp(
            row.get("collected_at")
        )

    def _build_context_quality(
        self,
        *,
        hours: int,
        coverage_rows: list[dict],
        article_count: int,
        raw_article_count: int,
        source_counts: Counter,
        source_group_counts: Counter,
        symbol_counts: Counter,
        content_article_count: int,
        configured_universe_summary: dict[str, object] | None = None,
        ai_excluded_source_count: int = 0,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []

        ready_for_ai_rows = [
            row
            for row in coverage_rows
            if row.get("is_ready_for_ai")
        ]
        ready_for_ai_high_frequency_rows = [
            row
            for row in ready_for_ai_rows
            if self._is_high_frequency_source_group(row.get("source_group"))
        ]
        configured_core_media_ready_for_ai = any(
            row.get("is_ready_for_ai")
            and self._normalized_source_group(row.get("source_group")) == "core_media"
            for row in coverage_rows
        )
        configured_market_intelligence_ready_for_ai = any(
            row.get("is_ready_for_ai")
            and self._normalized_source_group(row.get("source_group")) == "market_intelligence"
            for row in coverage_rows
        )
        non_ready_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("health_status") != "ready"
        ]
        not_ready_for_ai_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("is_ready_for_ai")
        ]
        stale_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("is_stale")
        ]
        cooldown_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("in_cooldown")
        ]

        if non_ready_sources:
            self._append_unique(flags, "news_source_not_ready_present")
            self._append_unique(
                notes,
                "当前仍有未 ready 的新闻源: "
                f"{', '.join(non_ready_sources[:6])}"
                f"{' ...' if len(non_ready_sources) > 6 else ''}。",
            )
        if not_ready_for_ai_sources:
            self._append_unique(flags, "news_source_not_ready_for_ai_present")
            self._append_unique(
                notes,
                "当前仍有新闻源没有达到可直接供 AI 使用的质量门槛: "
                f"{', '.join(not_ready_for_ai_sources[:6])}"
                f"{' ...' if len(not_ready_for_ai_sources) > 6 else ''}。",
            )
        if stale_sources:
            self._append_unique(flags, "news_stale_sources_present")
            self._append_unique(
                notes,
                "部分新闻源已经 stale，AI 不应把这些来源视为当前事件流。"
            )
        if cooldown_sources:
            self._append_unique(flags, "news_cooldown_sources_present")
            self._append_unique(
                notes,
                "部分新闻源处于失败冷却期，近期新闻覆盖存在继续变薄的风险。"
            )
        if (
            configured_universe_summary
            and configured_universe_summary.get("scope_kind") == "default"
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            self._append_unique(flags, "news_configured_market_breadth_limited")
            market_role_counts = configured_universe_summary.get("market_role_counts") or {}
            minimum_market_role_counts = (
                configured_universe_summary.get(
                    "minimum_market_role_counts_for_market_breadth"
                )
                or {}
            )
            missing_market_role_groups = (
                configured_universe_summary.get("missing_market_role_groups") or []
            )
            missing_group_samples = ", ".join(
                f"{group_name}({int(market_role_counts.get(group_name) or 0)}/"
                f"{int(minimum_market_role_counts.get(group_name) or 0)})"
                for group_name in missing_market_role_groups[:6]
            )
            self._append_unique(
                notes,
                "当前 news 默认跟踪资产注册表只覆盖 "
                f"{int(configured_universe_summary.get('asset_count') or 0)} 个资产，"
                "更适合核心观察名单；"
                "对更广市场 breadth 的新闻映射仍有限。"
                + (
                    f"不足的资产分组有: {missing_group_samples}。"
                    if missing_group_samples
                    else ""
                ),
            )
        if not configured_core_media_ready_for_ai:
            self._append_unique(flags, "news_core_media_missing")
            self._append_unique(
                notes,
                "当前没有达到 AI 可用门槛的核心新闻媒体流，AI 对即时市场头条的感知会变弱。"
            )
        if not configured_market_intelligence_ready_for_ai:
            self._append_unique(flags, "news_market_intelligence_missing")
            self._append_unique(
                notes,
                "当前没有达到 AI 可用门槛的市场深度解读流，AI 很难把 headline 和研究背景拼起来。"
            )
        if not ready_for_ai_high_frequency_rows:
            self._append_unique(flags, "news_high_frequency_coverage_missing")
            self._append_unique(
                notes,
                "当前没有达到 AI 可用门槛的连续新闻流来源，文本层更像低频公告补充而不是实时新闻覆盖。"
            )

        if article_count <= 0:
            self._append_unique(flags, "news_context_empty")
            if raw_article_count > 0 and ai_excluded_source_count > 0:
                self._append_unique(
                    notes,
                    f"最近 {hours} 小时虽然已有真实已落库新闻，但它们全部来自尚未达到 AI-ready 门槛的来源，当前没有任何可直接给 AI 使用的实时文本事件输入。"
                )
            else:
                self._append_unique(
                    notes,
                    f"最近 {hours} 小时没有任何已落库新闻，AI 当前缺少实时文本事件输入。"
                )
            return flags, notes

        thin_threshold = (
            max(2, min(12, len(ready_for_ai_high_frequency_rows)))
            if ready_for_ai_high_frequency_rows
            else 2
        )
        if article_count < thin_threshold:
            self._append_unique(flags, "news_recent_articles_thin")
            self._append_unique(
                notes,
                f"最近 {hours} 小时仅有 {article_count} 条文章，低于当前新闻覆盖建议阈值 {thin_threshold} 条。"
            )

        leader_source, leader_count = max(
            source_counts.items(),
            key=lambda item: (item[1], item[0]),
        )
        leader_share = leader_count / article_count
        if article_count >= 3 and leader_share >= 0.6:
            self._append_unique(flags, "news_source_concentration_high")
            self._append_unique(
                notes,
                f"最近 {hours} 小时 {leader_source} 占全部新闻 {leader_share:.0%}，文本证据过度集中。"
            )

        high_frequency_article_count = sum(
            count
            for group_name, count in source_group_counts.items()
            if group_name in self.HIGH_FREQUENCY_SOURCE_GROUPS
        )
        if high_frequency_article_count <= 0:
            self._append_unique(flags, "news_only_low_frequency_articles")
            self._append_unique(
                notes,
                "当前窗口里的文章全部来自低频公告、论坛或研究类来源，缺少连续 headline 流。"
            )

        content_ratio = content_article_count / article_count
        if content_ratio < 0.5:
            self._append_unique(flags, "news_text_body_coverage_thin")
            self._append_unique(
                notes,
                "最近新闻里正文可用比例偏低，AI 更多只能依赖标题和摘要做判断。"
            )

        if article_count >= 3 and not symbol_counts:
            self._append_unique(flags, "news_symbol_tagging_missing")
            self._append_unique(
                notes,
                "最近新闻没有命中任何资产标签，AI 难以快速把新闻映射到交易标的。"
            )
        return flags, notes

    def load_source_coverage(
        self,
        hours: int = 24,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> dict:
        sources = load_news_sources(
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
            enabled_only=False,
        )
        now = self._utc_now_naive()
        if not sources:
            health_summary = summarize_health_rows([])
            return {
                "generated_at": now.isoformat(),
                "source_count": 0,
                "total_article_count": 0,
                "recent_article_count": 0,
                "stale_source_count": 0,
                "cooldown_source_count": 0,
                "ready_for_ai_source_count": 0,
                "not_ready_for_ai_source_count": 0,
                **health_summary,
                "sources": [],
            }

        source_name_list = [source.name for source in sources]
        placeholders = ",".join("?" for _ in source_name_list)
        recent_cutoff = (now - timedelta(hours=hours)).isoformat()

        article_rows = self.db.fetch_all(
            f"""
            SELECT
                source,
                COUNT(*) AS total_articles,
                SUM(CASE WHEN COALESCE(published_at, collected_at) >= ? THEN 1 ELSE 0 END) AS recent_articles,
                SUM(
                    CASE
                        WHEN COALESCE(published_at, collected_at) >= ?
                             AND TRIM(COALESCE(content_text, '')) <> ''
                        THEN 1 ELSE 0
                    END
                ) AS recent_articles_with_content_text,
                SUM(
                    CASE
                        WHEN COALESCE(published_at, collected_at) >= ?
                             AND COALESCE(relevance_symbols, '') NOT IN ('', '[]')
                        THEN 1 ELSE 0
                    END
                ) AS recent_articles_with_relevance_symbols,
                MAX(collected_at) AS last_collected_at,
                MAX(COALESCE(published_at, collected_at)) AS last_article_time
            FROM news_articles
            WHERE source IN ({placeholders})
            GROUP BY source
            """,
            (recent_cutoff, recent_cutoff, recent_cutoff, *source_name_list),
        )
        article_map = {
            str(row["source"]): dict(row)
            for row in article_rows
        }

        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'news_data'
                  AND source_name IN ({placeholders})
                GROUP BY source_name
            ) AS latest
                ON runs.id = latest.latest_id
            """,
            tuple(source_name_list),
        )
        run_map = {
            str(row["source_name"]): dict(row)
            for row in run_rows
        }

        health_provider = getattr(self.client, "describe_source_health", None)
        health_rows = health_provider(sources) if callable(health_provider) else []
        health_map = {
            str(row["source_name"]): row
            for row in health_rows
        }

        coverage_rows: list[dict] = []
        for source in sources:
            article_meta = article_map.get(source.name, {})
            run_meta = run_map.get(source.name, {})
            health_meta = health_map.get(source.name, {})
            last_run_at = self._parse_timestamp(run_meta.get("finished_at"))
            is_stale = last_run_at is None or (
                now - last_run_at
            ).total_seconds() > NEWS_CONFIG["interval_seconds"] * 3
            configuration_ready = bool(
                [value for value in [source.feed_url, *source.fallback_feed_urls] if str(value or "").strip()]
            )
            total_articles = int(article_meta.get("total_articles") or 0)
            recent_articles = int(article_meta.get("recent_articles") or 0)
            recent_articles_with_content_text = int(
                article_meta.get("recent_articles_with_content_text") or 0
            )
            recent_articles_with_relevance_symbols = int(
                article_meta.get("recent_articles_with_relevance_symbols") or 0
            )
            consecutive_failures = int(health_meta.get("consecutive_failures") or 0)
            in_cooldown = bool(health_meta.get("in_cooldown") or False)
            effective_last_run_status = "cooldown" if in_cooldown else run_meta.get("status")
            health_status = resolve_source_health_status(
                enabled=bool(source.enabled),
                configuration_ready=configuration_ready,
                last_run_status=effective_last_run_status,
                latest_point_count=self._article_count_for_health(
                    source,
                    total_articles=total_articles,
                    recent_articles=recent_articles,
                ),
                is_stale=is_stale,
            )
            last_article_age_seconds = self._age_seconds(now, article_meta.get("last_article_time"))
            data_quality_flags, quality_notes = self._build_quality_flags_and_notes(
                source=source,
                hours=hours,
                configuration_ready=configuration_ready,
                total_articles=total_articles,
                recent_articles=recent_articles,
                recent_articles_with_content_text=recent_articles_with_content_text,
                recent_articles_with_relevance_symbols=recent_articles_with_relevance_symbols,
                is_stale=is_stale,
                in_cooldown=in_cooldown,
                consecutive_failures=consecutive_failures,
                last_article_age_seconds=last_article_age_seconds,
            )
            is_ready_for_ai = self._is_source_ready_for_ai(
                source=source,
                health_status=health_status,
                recent_articles=recent_articles,
                recent_articles_with_content_text=recent_articles_with_content_text,
                recent_articles_with_relevance_symbols=recent_articles_with_relevance_symbols,
            )
            coverage_rows.append(
                {
                    "source_name": source.name,
                    "name": source.name,
                    "feed_url": source.feed_url,
                    "fallback_feed_urls": source.fallback_feed_urls,
                    "source_group": source.source_group,
                    "category": source.category,
                    "language": source.language,
                    "enabled": source.enabled,
                    "configuration_ready": configuration_ready,
                    "coverage_expectation": self._coverage_expectation_for_source(source),
                    "recommended_recent_articles": self._recommended_recent_articles(source),
                    "tags": source.tags,
                    "total_articles": total_articles,
                    "recent_articles": recent_articles,
                    "recent_articles_with_content_text": recent_articles_with_content_text,
                    "recent_articles_with_relevance_symbols": recent_articles_with_relevance_symbols,
                    "recent_content_text_coverage_ratio": (
                        round(recent_articles_with_content_text / recent_articles, 4)
                        if recent_articles > 0
                        else 0.0
                    ),
                    "recent_relevance_symbol_coverage_ratio": (
                        round(recent_articles_with_relevance_symbols / recent_articles, 4)
                        if recent_articles > 0
                        else 0.0
                    ),
                    "recent_article_ratio": self._recent_article_ratio(
                        total_articles=total_articles,
                        recent_articles=recent_articles,
                    ),
                    "has_recent_article": recent_articles > 0,
                    "last_collected_at": article_meta.get("last_collected_at"),
                    "last_article_time": article_meta.get("last_article_time"),
                    "last_article_age_seconds": last_article_age_seconds,
                    "last_run_status": run_meta.get("status"),
                    "last_run_item_count": int(run_meta.get("item_count") or 0),
                    "last_run_finished_at": run_meta.get("finished_at"),
                    "last_run_message": run_meta.get("message"),
                    "last_run_metadata": self._loads_json(run_meta.get("metadata_json")),
                    "consecutive_failures": consecutive_failures,
                    "in_cooldown": in_cooldown,
                    "cooldown_until": health_meta.get("cooldown_until"),
                    "last_error": health_meta.get("last_error"),
                    "is_stale": is_stale,
                    "health_status": health_status,
                    "is_ready_for_ai": is_ready_for_ai,
                    "data_quality_flags": data_quality_flags,
                    "quality_notes": quality_notes,
                }
            )

        coverage_rows.sort(
            key=lambda item: (
                item["health_status"] != "ready",
                not item["is_ready_for_ai"],
                item["is_stale"],
                -(item["recent_articles"] or 0),
                item["source_name"],
            )
        )
        health_summary = summarize_health_rows(coverage_rows)
        ready_for_ai_source_count = sum(1 for item in coverage_rows if item["is_ready_for_ai"])

        return {
            "generated_at": now.isoformat(),
            "source_count": len(coverage_rows),
            "total_article_count": sum(item["total_articles"] for item in coverage_rows),
            "recent_article_count": sum(item["recent_articles"] for item in coverage_rows),
            "stale_source_count": sum(1 for item in coverage_rows if item["is_stale"]),
            "cooldown_source_count": sum(1 for item in coverage_rows if item["in_cooldown"]),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(coverage_rows) - ready_for_ai_source_count,
            **health_summary,
            "sources": coverage_rows,
        }

    def load_latest_context_bundle(
        self,
        hours: int = 24,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
        limit: int = 50,
    ) -> dict:
        now = self._utc_now_naive()
        coverage = self.load_source_coverage(
            hours=hours,
            source_names=source_names,
            categories=categories,
            tags=tags,
            source_groups=source_groups,
        )
        coverage_rows = coverage.get("sources", [])
        coverage_map = {
            str(row["source_name"]): row
            for row in coverage_rows
        }
        configured_universe_summary = self._build_configured_universe_summary()
        selected_source_names = [str(row["source_name"]) for row in coverage_rows]
        parsed_rows: list[dict] = []

        if selected_source_names:
            placeholders = ",".join("?" for _ in selected_source_names)
            cutoff = (now - timedelta(hours=hours)).isoformat()
            rows = self.db.fetch_all(
                f"""
                SELECT
                    source, source_type, feed_url, category, title, summary,
                    content_text, url, url_hash, author, published_at, collected_at,
                    language, relevance_symbols, tags, image_url, external_id,
                    raw_payload_json
                FROM news_articles
                WHERE source IN ({placeholders})
                  AND COALESCE(published_at, collected_at) >= ?
                ORDER BY COALESCE(published_at, collected_at) DESC,
                         collected_at DESC,
                         source ASC
                """,
                (*selected_source_names, cutoff),
            )
            for row in rows:
                row_dict = dict(row)
                coverage_meta = coverage_map.get(str(row_dict["source"]), {})
                effective_time_dt = self._article_effective_time(row_dict)
                parsed_rows.append(
                    {
                        **row_dict,
                        "effective_time": (
                            effective_time_dt.isoformat()
                            if effective_time_dt is not None
                            else None
                        ),
                        "source_group": coverage_meta.get("source_group"),
                        "source_health_status": coverage_meta.get("health_status"),
                        "relevance_symbols_list": self._loads_string_list(
                            row_dict.get("relevance_symbols")
                        ),
                        "tags_list": self._loads_string_list(row_dict.get("tags")),
                        "raw_payload": self._loads_json(row_dict.get("raw_payload_json")),
                    }
                )

        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=parsed_rows,
            coverage_rows=coverage_rows,
        )
        raw_parsed_rows = list(parsed_rows)
        parsed_rows = [
            row
            for row in raw_parsed_rows
            if str(row["source"]) in ai_ready_source_names
        ]

        def _summarize_rows(rows: list[dict]) -> dict[str, object]:
            source_counts: Counter = Counter()
            source_group_counts: Counter = Counter()
            category_counts: Counter = Counter()
            tag_counts: Counter = Counter()
            language_counts: Counter = Counter()
            symbol_counts: Counter = Counter()
            symbol_source_map: dict[str, set[str]] = {}
            content_article_count = 0
            summary_article_count = 0
            symbol_article_count = 0

            for row in rows:
                source_name = str(row["source"])
                source_group = str(row.get("source_group") or "ungrouped")
                category = str(row.get("category") or "uncategorized")
                language = str(row.get("language") or "unknown")
                source_counts[source_name] += 1
                source_group_counts[source_group] += 1
                category_counts[category] += 1
                language_counts[language] += 1
                if str(row.get("summary") or "").strip():
                    summary_article_count += 1
                if str(row.get("content_text") or "").strip():
                    content_article_count += 1
                relevance_symbols = row.get("relevance_symbols_list") or []
                if relevance_symbols:
                    symbol_article_count += 1
                for symbol in relevance_symbols:
                    symbol_counts[symbol] += 1
                    symbol_source_map.setdefault(symbol, set()).add(source_name)
                for tag in row.get("tags_list") or []:
                    tag_counts[tag] += 1

            return {
                "source_counts": source_counts,
                "source_group_counts": source_group_counts,
                "category_counts": category_counts,
                "tag_counts": tag_counts,
                "language_counts": language_counts,
                "symbol_counts": symbol_counts,
                "symbol_source_map": symbol_source_map,
                "content_article_count": content_article_count,
                "summary_article_count": summary_article_count,
                "symbol_article_count": symbol_article_count,
            }

        stats = _summarize_rows(parsed_rows)
        raw_stats = _summarize_rows(raw_parsed_rows)
        source_counts = stats["source_counts"]
        source_group_counts = stats["source_group_counts"]
        category_counts = stats["category_counts"]
        tag_counts = stats["tag_counts"]
        language_counts = stats["language_counts"]
        symbol_counts = stats["symbol_counts"]
        symbol_source_map = stats["symbol_source_map"]
        content_article_count = int(stats["content_article_count"])
        summary_article_count = int(stats["summary_article_count"])
        symbol_article_count = int(stats["symbol_article_count"])
        raw_source_counts = self._count_articles_by_source(raw_parsed_rows)

        def _sorted_distribution(counter: Counter, field_name: str) -> list[dict]:
            total = sum(counter.values()) or 1
            return [
                {
                    field_name: key,
                    "article_count": count,
                    "article_share": round(count / total, 4),
                }
                for key, count in sorted(
                    counter.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ]

        latest_effective_time = max(
            (
                row["effective_time"]
                for row in parsed_rows
                if row.get("effective_time")
            ),
            default=None,
        )
        raw_latest_effective_time = max(
            (
                row["effective_time"]
                for row in raw_parsed_rows
                if row.get("effective_time")
            ),
            default=None,
        )
        source_health = [
            {
                "source_name": row["source_name"],
                "source_group": row["source_group"],
                "category": row["category"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "recent_articles": row["recent_articles"],
                "total_articles": row["total_articles"],
                "last_article_time": row["last_article_time"],
                "last_run_status": row["last_run_status"],
                "consecutive_failures": row["consecutive_failures"],
                "in_cooldown": row["in_cooldown"],
                "is_stale": row["is_stale"],
                "data_quality_flags": row["data_quality_flags"],
                "quality_notes": row["quality_notes"],
            }
            for row in coverage_rows
        ]
        coverage_by_source = [
            {
                "source_name": row["source_name"],
                "source_group": row["source_group"],
                "category": row["category"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "coverage_expectation": row["coverage_expectation"],
                "recommended_recent_articles": row["recommended_recent_articles"],
                "recent_articles": row["recent_articles"],
                "total_articles": row["total_articles"],
                "has_recent_article": row["has_recent_article"],
            }
            for row in coverage_rows
        ]
        data_quality_flags, quality_notes = self._build_context_quality(
            hours=hours,
            coverage_rows=coverage_rows,
            article_count=len(parsed_rows),
            raw_article_count=len(raw_parsed_rows),
            source_counts=source_counts,
            source_group_counts=source_group_counts,
            symbol_counts=symbol_counts,
            content_article_count=content_article_count,
            configured_universe_summary=configured_universe_summary,
            ai_excluded_source_count=len(ai_excluded_sources),
        )

        return {
            "as_of": latest_effective_time,
            "raw_as_of": raw_latest_effective_time,
            "generated_at": now.isoformat(),
            "row_count": len(parsed_rows),
            "article_count": len(parsed_rows),
            "raw_article_count": len(raw_parsed_rows),
            "source_counts": self._count_articles_by_source(parsed_rows),
            "raw_source_counts": raw_source_counts,
            "ai_ready_source_names": sorted(ai_ready_source_names),
            "ai_excluded_source_names": [
                str(item["source_name"])
                for item in ai_excluded_sources
            ],
            "ai_excluded_sources": ai_excluded_sources,
            "configured_universe_summary": configured_universe_summary,
            "coverage_summary": {
                "selected_source_count": coverage.get("source_count", 0),
                "observed_source_count": len(source_counts),
                "raw_observed_source_count": len(raw_source_counts),
                "ready_source_count": coverage.get("ready_source_count", 0),
                "problem_source_count": coverage.get("problem_source_count", 0),
                "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
                "recent_article_count": coverage.get("recent_article_count", 0),
                "total_article_count": coverage.get("total_article_count", 0),
                "observed_source_groups": sorted(source_group_counts),
                "raw_observed_source_groups": sorted(raw_stats["source_group_counts"]),
                "missing_high_frequency_source_groups": sorted(
                    self.HIGH_FREQUENCY_SOURCE_GROUPS
                    - {
                        self._normalized_source_group(row.get("source_group"))
                        for row in coverage_rows
                        if row.get("is_ready_for_ai")
                    }
                ),
                "coverage_by_source": coverage_by_source,
            },
            "source_health_summary": {
                "source_count": coverage.get("source_count", 0),
                "ready_source_count": coverage.get("ready_source_count", 0),
                "problem_source_count": coverage.get("problem_source_count", 0),
                "stale_source_count": coverage.get("stale_source_count", 0),
                "cooldown_source_count": coverage.get("cooldown_source_count", 0),
                "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
                "not_ready_for_ai_source_count": coverage.get(
                    "not_ready_for_ai_source_count",
                    0,
                ),
            },
            "source_health": source_health,
            "text_completeness_summary": {
                "articles_with_summary_count": summary_article_count,
                "articles_with_content_text_count": content_article_count,
                "articles_with_relevance_symbols_count": symbol_article_count,
                "content_text_ready_ratio": (
                    round(content_article_count / len(parsed_rows), 4)
                    if parsed_rows
                    else 0.0
                ),
            },
            "raw_text_completeness_summary": {
                "articles_with_summary_count": int(raw_stats["summary_article_count"]),
                "articles_with_content_text_count": int(raw_stats["content_article_count"]),
                "articles_with_relevance_symbols_count": int(raw_stats["symbol_article_count"]),
                "content_text_ready_ratio": (
                    round(int(raw_stats["content_article_count"]) / len(raw_parsed_rows), 4)
                    if raw_parsed_rows
                    else 0.0
                ),
            },
            "top_sources_by_recent_articles": [
                {
                    "source_name": source_name,
                    "article_count": count,
                    "article_share": round(count / len(parsed_rows), 4),
                    "source_group": coverage_map.get(source_name, {}).get("source_group"),
                    "category": coverage_map.get(source_name, {}).get("category"),
                    "health_status": coverage_map.get(source_name, {}).get("health_status"),
                    "is_ready_for_ai": coverage_map.get(source_name, {}).get("is_ready_for_ai"),
                }
                for source_name, count in sorted(
                    source_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ][:10],
            "category_distribution": _sorted_distribution(category_counts, "category"),
            "source_group_distribution": _sorted_distribution(source_group_counts, "source_group"),
            "language_distribution": _sorted_distribution(language_counts, "language"),
            "tag_distribution": [
                {
                    "tag": tag,
                    "article_count": count,
                    "article_share": round(count / len(parsed_rows), 4),
                }
                for tag, count in sorted(
                    tag_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ][:20],
            "dominant_symbols": [
                {
                    "symbol": symbol,
                    "article_count": count,
                    "article_share": round(count / len(parsed_rows), 4),
                    "source_count": len(symbol_source_map.get(symbol) or set()),
                }
                for symbol, count in sorted(
                    symbol_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ][:10],
            "latest_articles": [
                {
                    "source": row["source"],
                    "source_group": row.get("source_group"),
                    "category": row.get("category"),
                    "title": row["title"],
                    "summary": row.get("summary"),
                    "url": row["url"],
                    "author": row.get("author"),
                    "language": row.get("language"),
                    "published_at": row.get("published_at"),
                    "collected_at": row.get("collected_at"),
                    "effective_time": row.get("effective_time"),
                    "relevance_symbols": row.get("relevance_symbols_list") or [],
                    "tags": row.get("tags_list") or [],
                    "has_content_text": bool(str(row.get("content_text") or "").strip()),
                    "health_status": row.get("source_health_status"),
                }
                for row in parsed_rows[: max(int(limit), 0)]
            ],
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
        }

    def _run_scheduled_collect(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ):
        local_db = DBManager(self.db.db_path)
        local_collector = NewsCollector(self.client, local_db)
        try:
            return local_collector.collect(
                hours=hours,
                limit_per_source=limit_per_source,
                source_names=source_names,
                categories=categories,
                tags=tags,
                source_groups=source_groups,
            )
        finally:
            local_db.close()

    def build_scheduler(
        self,
        hours: int | None = None,
        limit_per_source: int | None = None,
        source_names: list[str] | None = None,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        source_groups: list[str] | None = None,
    ) -> BlockingScheduler:
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self._run_scheduled_collect,
            "interval",
            seconds=NEWS_CONFIG["interval_seconds"],
            id="news_articles",
            name="新闻数据采集",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=max(60, NEWS_CONFIG["interval_seconds"]),
            kwargs={
                "hours": hours if hours is not None else NEWS_CONFIG["lookback_hours"],
                "limit_per_source": (
                    limit_per_source
                    if limit_per_source is not None
                    else NEWS_CONFIG["max_items_per_source"]
                ),
                "source_names": source_names,
                "categories": categories,
                "tags": tags,
                "source_groups": source_groups,
            },
        )
        return scheduler

    def close(self):
        self.db.close()
