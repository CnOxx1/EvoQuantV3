import json

from loguru import logger

from config.settings import NEWS_CONFIG
from data_layer.news_data.models import NewsSource


CORE_MEDIA_SOURCES = [
    NewsSource(
        name="CoinDesk",
        feed_url="https://www.coindesk.com/arc/outboundfeeds/rss",
        fallback_feed_urls=[
            "https://coindesk.com/arc/outboundfeeds/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
        ],
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "breaking-news"],
    ),
    NewsSource(
        name="Cointelegraph",
        feed_url="https://cointelegraph.com/rss",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "market"],
    ),
    NewsSource(
        name="Decrypt",
        feed_url="https://decrypt.co/feed",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "policy"],
    ),
    NewsSource(
        name="CryptoSlate",
        feed_url="https://cryptoslate.com/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "data"],
    ),
    NewsSource(
        name="BeInCrypto",
        feed_url="https://beincrypto.com/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "market"],
    ),
    NewsSource(
        name="NewsBTC",
        feed_url="https://www.newsbtc.com/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "bitcoin"],
    ),
    NewsSource(
        name="AMBCrypto",
        feed_url="https://ambcrypto.com/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "altcoins"],
    ),
    NewsSource(
        name="CryptoPotato",
        feed_url="https://cryptopotato.com/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "market"],
    ),
    NewsSource(
        name="CoinJournal",
        feed_url="https://coinjournal.net/feed/",
        category="crypto-news",
        language="en",
        tags=["crypto", "media", "market"],
    ),
]

MARKET_INTELLIGENCE_SOURCES = [
    NewsSource(
        name="Blockworks",
        feed_url="https://blockworks.com/feed/",
        category="market-intelligence",
        language="en",
        tags=["crypto", "research", "markets"],
    ),
    NewsSource(
        name="Bitcoin Magazine",
        feed_url="https://bitcoinmagazine.com/feed",
        category="market-intelligence",
        language="en",
        tags=["crypto", "media", "bitcoin"],
    ),
    NewsSource(
        name="The Defiant",
        feed_url="https://thedefiant.io/api/feed",
        category="market-intelligence",
        language="en",
        tags=["crypto", "defi", "research"],
    ),
    NewsSource(
        name="99Bitcoins",
        feed_url="https://99bitcoins.com/feed/",
        category="market-intelligence",
        language="en",
        tags=["crypto", "education", "bitcoin"],
    ),
]

ECOSYSTEM_BLOG_SOURCES = [
    NewsSource(
        name="Arbitrum",
        feed_url="https://blog.arbitrum.io/feed/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "l2", "official"],
    ),
    NewsSource(
        name="Chainlink Blog",
        feed_url="https://blog.chain.link/feed/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "oracle", "official"],
    ),
    NewsSource(
        name="Sui Blog",
        feed_url="https://blog.sui.io/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "l1", "official"],
    ),
    NewsSource(
        name="Sonic Blog",
        feed_url="https://blog.soniclabs.com/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "l1", "official"],
    ),
    NewsSource(
        name="Sei Blog",
        feed_url="https://blog.sei.io/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "l1", "official"],
    ),
    NewsSource(
        name="Lido Blog",
        feed_url="https://blog.lido.fi/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "staking", "official"],
    ),
    NewsSource(
        name="1inch Blog",
        feed_url="https://blog.1inch.com/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "defi", "official"],
    ),
    NewsSource(
        name="Synthetix Blog",
        feed_url="https://blog.synthetix.io/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "defi", "official"],
    ),
    NewsSource(
        name="EigenLayer Blog",
        feed_url="https://blog.eigencloud.xyz/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "restaking", "official"],
    ),
    NewsSource(
        name="SatLayer Blog",
        feed_url="https://blog.satlayer.xyz/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "bitcoin", "official"],
    ),
    NewsSource(
        name="Avail Blog",
        feed_url="https://blog.availproject.org/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "modular", "official"],
    ),
    NewsSource(
        name="Celestia Blog",
        feed_url="https://blog.celestia.org/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "modular", "official"],
    ),
    NewsSource(
        name="RedStone Blog",
        feed_url="https://blog.redstone.finance/feed/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "oracle", "official"],
    ),
    NewsSource(
        name="QuickNode Blog",
        feed_url="https://blog.quicknode.com/rss/",
        category="ecosystem",
        language="en",
        tags=["crypto", "ecosystem", "infrastructure", "rpc"],
    ),
]

GOVERNANCE_AND_FORUM_SOURCES = [
    NewsSource(
        name="Lido Research",
        feed_url="https://research.lido.fi/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "staking", "forum"],
    ),
    NewsSource(
        name="EigenLayer Forum",
        feed_url="https://forum.eigenlayer.xyz/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "restaking", "forum"],
    ),
    NewsSource(
        name="Arbitrum Forum",
        feed_url="https://forum.arbitrum.foundation/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "l2", "forum"],
    ),
    NewsSource(
        name="ENS Governance",
        feed_url="https://discuss.ens.domains/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "identity", "forum"],
    ),
    NewsSource(
        name="Sky Forum",
        feed_url="https://forum.skyeco.com/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "defi", "forum"],
    ),
    NewsSource(
        name="dYdX Forum",
        feed_url="https://dydx.forum/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "derivatives", "forum"],
    ),
    NewsSource(
        name="Safe Forum",
        feed_url="https://forum.safefoundation.org/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "wallet", "forum"],
    ),
    NewsSource(
        name="Starknet Community",
        feed_url="https://community.starknet.io/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "l2", "forum"],
    ),
    NewsSource(
        name="CoW DAO Forum",
        feed_url="https://forum.cow.fi/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "dex", "forum"],
    ),
    NewsSource(
        name="Gitcoin Governance",
        feed_url="https://gov.gitcoin.co/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "grants", "forum"],
    ),
    NewsSource(
        name="Osmosis Community Hall",
        feed_url="https://forum.osmosis.zone/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "cosmos", "forum"],
    ),
    NewsSource(
        name="Celestia Forum",
        feed_url="https://forum.celestia.org/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "modular", "forum"],
    ),
    NewsSource(
        name="Zcash Community Forum",
        feed_url="https://forum.zcashcommunity.com/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "privacy", "forum"],
    ),
    NewsSource(
        name="Babylon Forum",
        feed_url="https://forum.babylon.foundation/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "bitcoin", "forum"],
    ),
    NewsSource(
        name="Polkadot Forum",
        feed_url="https://forum.polkadot.network/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "multichain", "forum"],
    ),
    NewsSource(
        name="Cosmos Hub Forum",
        feed_url="https://forum.cosmos.network/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "cosmos", "forum"],
    ),
    NewsSource(
        name="Nym Forum",
        feed_url="https://forum.nym.com/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "privacy", "forum"],
    ),
    NewsSource(
        name="Berachain Forum",
        feed_url="https://forum.berachain.com/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "l1", "forum"],
    ),
    NewsSource(
        name="Scroll Forum",
        feed_url="https://forum.scroll.io/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "zk-rollup", "forum"],
    ),
    NewsSource(
        name="Initia Forum",
        feed_url="https://forum.initia.xyz/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "cosmos", "forum"],
    ),
    NewsSource(
        name="Aztec Forum",
        feed_url="https://forum.aztec.network/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "privacy", "forum"],
    ),
    NewsSource(
        name="Connext Forum",
        feed_url="https://forum.connext.network/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "bridge", "forum"],
    ),
    NewsSource(
        name="Pyth DAO Forum",
        feed_url="https://forum.pyth.network/latest.rss",
        category="governance",
        language="en",
        tags=["crypto", "governance", "oracle", "forum"],
    ),
]

RESEARCH_SECURITY_AND_REGULATORY_SOURCES = [
    NewsSource(
        name="Chainalysis",
        feed_url="https://www.chainalysis.com/feed/",
        category="research",
        language="en",
        tags=["crypto", "research", "compliance", "onchain"],
    ),
    NewsSource(
        name="Immunefi",
        feed_url="https://immunefi.com/blog/rss/",
        category="security-research",
        language="en",
        tags=["crypto", "security", "bug-bounty", "research"],
    ),
    NewsSource(
        name="SEC Press Releases",
        feed_url="https://www.sec.gov/news/pressreleases.rss",
        category="regulatory",
        language="en",
        tags=["crypto", "regulatory", "policy", "official"],
    ),
    NewsSource(
        name="Elliptic",
        feed_url="https://www.elliptic.co/blog/rss.xml",
        category="research",
        language="en",
        tags=["crypto", "research", "compliance", "forensics"],
    ),
    NewsSource(
        name="CFTC General Press Releases",
        feed_url="https://www.cftc.gov/RSS/RSSGP/rssgp.xml",
        category="regulatory",
        language="en",
        tags=["crypto", "regulatory", "policy", "official"],
    ),
    NewsSource(
        name="CFTC Enforcement Actions",
        feed_url="https://www.cftc.gov/RSS/RSSENF/rssenf.xml",
        category="regulatory",
        language="en",
        tags=["crypto", "regulatory", "enforcement", "official"],
    ),
    NewsSource(
        name="Trail of Bits",
        feed_url="https://blog.trailofbits.com/index.xml",
        category="security-research",
        language="en",
        tags=["crypto", "security", "research", "auditing"],
    ),
]


DEFAULT_NEWS_SOURCES = [
    *[source.model_copy(update={"source_group": "core_media"}) for source in CORE_MEDIA_SOURCES],
    *[
        source.model_copy(update={"source_group": "market_intelligence"})
        for source in MARKET_INTELLIGENCE_SOURCES
    ],
    *[source.model_copy(update={"source_group": "ecosystem"}) for source in ECOSYSTEM_BLOG_SOURCES],
    *[
        source.model_copy(update={"source_group": "governance_forum"})
        for source in GOVERNANCE_AND_FORUM_SOURCES
    ],
    *[
        source.model_copy(update={"source_group": "research_security_regulatory"})
        for source in RESEARCH_SECURITY_AND_REGULATORY_SOURCES
    ],
]


def _normalize_filter(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    return {value.strip().lower() for value in values if value.strip()}


def load_news_sources(
    source_names: list[str] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    source_groups: list[str] | None = None,
    enabled_only: bool = True,
) -> list[NewsSource]:
    """加载默认新闻源，并支持通过环境变量追加配置。"""

    sources = list(DEFAULT_NEWS_SOURCES)
    extra_feeds_json = NEWS_CONFIG.get("extra_feeds_json", "").strip()
    if extra_feeds_json:
        try:
            extra_items = json.loads(extra_feeds_json)
            if not isinstance(extra_items, list):
                raise ValueError("NEWS_EXTRA_FEEDS_JSON 必须是 JSON 数组")
            for item in extra_items:
                sources.append(NewsSource(**item))
        except Exception as exc:
            logger.error(f"解析 NEWS_EXTRA_FEEDS_JSON 失败: {exc}")

    selected_sources = sources if not enabled_only else [source for source in sources if source.enabled]
    return filter_news_sources(
        selected_sources,
        source_names=source_names,
        categories=categories,
        tags=tags,
        source_groups=source_groups,
    )


def filter_news_sources(
    sources: list[NewsSource],
    source_names: list[str] | None = None,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
    source_groups: list[str] | None = None,
) -> list[NewsSource]:
    name_filter = _normalize_filter(source_names)
    category_filter = _normalize_filter(categories)
    tag_filter = _normalize_filter(tags)
    group_filter = _normalize_filter(source_groups)

    if source_names is not None and not name_filter:
        return []
    if categories is not None and not category_filter:
        return []
    if tags is not None and not tag_filter:
        return []
    if source_groups is not None and not group_filter:
        return []

    filtered: list[NewsSource] = []
    for source in sources:
        if name_filter and source.name.strip().lower() not in name_filter:
            continue
        if category_filter and (source.category or "").strip().lower() not in category_filter:
            continue
        if group_filter and (source.source_group or "").strip().lower() not in group_filter:
            continue
        if tag_filter:
            source_tags = {tag.strip().lower() for tag in source.tags if tag.strip()}
            if source.category:
                source_tags.add(source.category.strip().lower())
            if source.source_group:
                source_tags.add(source.source_group.strip().lower())
            if source_tags.isdisjoint(tag_filter):
                continue
        filtered.append(source)
    return filtered
