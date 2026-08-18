import os

from dotenv import load_dotenv

# 加载 .env 文件（项目根目录）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, ".env"), override=False)

from config.symbols import TARGET_SYMBOLS  # noqa: E402
from loguru import logger  # noqa: E402

# 项目根目录
BASE_DIR = _BASE_DIR

# 数据库配置
DATABASE_DIR = os.path.join(BASE_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "crypto_data.db")

# 数据库域拆分配置
DATABASE_SPLIT_ENABLED = os.getenv("DB_SPLIT_ENABLED", "1").strip() != "0"
EXCHANGE_DATA_DB_PATH = os.path.join(DATABASE_DIR, "exchange_data.db")
MARKET_DATA_DB_PATH = os.path.join(DATABASE_DIR, "market_data.db")
ANALYTICS_DB_PATH = os.path.join(DATABASE_DIR, "analytics.db")

# 数据库后端配置 (sqlite | postgres)
DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower()

# PostgreSQL 连接配置
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "evoquant")
PG_USER = os.getenv("PG_USER", "evoquant")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "10"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "50"))
DB_POOL_OVERFLOW = int(os.getenv("DB_POOL_OVERFLOW", "10"))
DB_POOL_IDLE_TIMEOUT = int(os.getenv("DB_POOL_IDLE_TIMEOUT", "300"))

# PostgreSQL Schema 映射
PG_SCHEMA_EXCHANGE = os.getenv("PG_SCHEMA_EXCHANGE", "exchange_data")
PG_SCHEMA_MARKET = os.getenv("PG_SCHEMA_MARKET", "market_data")
PG_SCHEMA_ANALYTICS = os.getenv("PG_SCHEMA_ANALYTICS", "analytics")

# World-model quality / selective prediction (paper-aligned, API-safe defaults)
# Production baseline WMI abstains below this threshold.
WMI_ABSTAIN_THRESHOLD = float(os.getenv("WMI_ABSTAIN_THRESHOLD", "0.2"))
# Optional ACWMI path: "wmi" (default product) or "acwmi" (geometric mean with S/C).
WORLD_MODEL_INDEX_MODE = os.getenv("WORLD_MODEL_INDEX_MODE", "wmi").strip().lower()
ACWMI_ABSTAIN_THRESHOLD = float(os.getenv("ACWMI_ABSTAIN_THRESHOLD", "0.35"))
# Band scope for WMI breadth/stability:
# - full: all schema bands (empty slots outside the consumer contract still drag B/U)
# - eval_archive / declared: only the declared consumer-archive bands (default for
#   paper handoff). Quality is relative to the world the bundle claims to deliver.
WORLD_MODEL_BAND_SCOPE = os.getenv("WORLD_MODEL_BAND_SCOPE", "eval_archive").strip().lower()
EVAL_ARCHIVE_BANDS = tuple(
    b.strip()
    for b in os.getenv(
        "EVAL_ARCHIVE_BANDS",
        "exchange,macro,alternative",
    ).split(",")
    if b.strip()
)


def _default_tracked_asset_entity_keys() -> str:
    assets: list[str] = []
    seen: set[str] = set()
    for symbol in TARGET_SYMBOLS:
        asset = str(symbol).split("/", 1)[0].strip().upper()
        if not asset or asset in seen:
            continue
        seen.add(asset)
        assets.append(asset)
    return ",".join(assets) or "BTC,ETH,SOL,SUI"


DEFAULT_TRACKED_ASSET_ENTITY_KEYS = _default_tracked_asset_entity_keys()

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.path.join(BASE_DIR, "logs")

# 交易所配置
EXCHANGE_CONFIG = {
    "binance": {
        "enabled": True,
        "rate_limit": True,
        "options": {
            "defaultType": "spot",
        },
    },
    "okx": {
        "enabled": True,
        "rate_limit": True,
        "options": {
            "defaultType": "spot",
        },
    },
    "bybit": {
        "enabled": True,
        "rate_limit": True,
        "options": {
            "defaultType": "spot",
        },
    },
}

# Binance spot public market-data host. api.binance.com is often HTTP 451 from
# restricted regions; data-api.binance.vision serves the same public spot
# endpoints without that eligibility gate. Override/empty to use ccxt defaults.
BINANCE_PUBLIC_API_BASE = os.getenv(
    "BINANCE_PUBLIC_API_BASE",
    "https://data-api.binance.vision",
).strip().rstrip("/")
# When using the public data host (or when futures are geo-blocked), only load
# spot markets so load_markets() does not call fapi/dapi (also 451).
BINANCE_LOAD_SPOT_MARKETS_ONLY = os.getenv(
    "BINANCE_LOAD_SPOT_MARKETS_ONLY",
    "1" if BINANCE_PUBLIC_API_BASE else "0",
).strip().lower() in {"1", "true", "yes", "on"}

# API Key 配置（生产环境应使用环境变量或密钥管理）
API_KEYS = {
    "binance": {
        "apiKey": os.getenv("BINANCE_API_KEY", ""),
        "secret": os.getenv("BINANCE_SECRET", ""),
    },
    "okx": {
        "apiKey": os.getenv("OKX_API_KEY", ""),
        "secret": os.getenv("OKX_SECRET", ""),
        "password": os.getenv("OKX_PASSWORD", ""),
    },
    "bybit": {
        "apiKey": os.getenv("BYBIT_API_KEY", ""),
        "secret": os.getenv("BYBIT_SECRET", ""),
    },
}

# 调度配置（秒）
SCHEDULER_CONFIG = {
    "market_info_interval": 86400,   # 静态信息：每日1次
    "kline_interval": 60,            # K线增量：每分钟
    "ticker_interval": int(os.getenv("TICKER_INTERVAL_SECONDS", "5")),        # 行情：默认每5秒
    "funding_interval": int(os.getenv("FUNDING_INTERVAL_SECONDS", "900")),    # 资金费率：默认每15分钟
    "orderbook_interval": int(os.getenv("ORDERBOOK_INTERVAL_SECONDS", "3")),  # 深度：默认每3秒
    "news_interval": int(os.getenv("NEWS_INTERVAL_SECONDS", "300")),          # 新闻：默认每5分钟
    "macro_market_interval": int(
        os.getenv("MACRO_MARKET_INTERVAL_SECONDS", "900")
    ),  # 宏观行情：默认每15分钟
    "macro_level_interval": int(
        os.getenv("MACRO_LEVEL_INTERVAL_SECONDS", "86400")
    ),  # 宏观利率/政策：默认每日1次
    "event_calendar_interval": int(
        os.getenv("EVENT_CALENDAR_INTERVAL_SECONDS", "21600")
    ),  # 事件日历：默认每6小时
    "onchain_exchange_flow_interval": int(
        os.getenv("ONCHAIN_EXCHANGE_FLOW_INTERVAL_SECONDS", "1800")
    ),  # 链上交易所净流：默认每30分钟
    "onchain_whale_activity_interval": int(
        os.getenv("ONCHAIN_WHALE_ACTIVITY_INTERVAL_SECONDS", "1800")
    ),  # 鲸鱼异动：默认每30分钟
    "onchain_stablecoin_flow_interval": int(
        os.getenv("ONCHAIN_STABLECOIN_FLOW_INTERVAL_SECONDS", "900")
    ),  # 稳定币流入交易所：默认每15分钟
    "exchange_trade_flow_interval": int(
        os.getenv("EXCHANGE_TRADE_FLOW_INTERVAL_SECONDS", "60")
    ),  # 成交/主动买卖流：默认每1分钟
    "exchange_open_interest_interval": int(
        os.getenv("EXCHANGE_OPEN_INTEREST_INTERVAL_SECONDS", "300")
    ),  # 持仓量：默认每5分钟
    "exchange_basis_interval": int(
        os.getenv("EXCHANGE_BASIS_INTERVAL_SECONDS", "300")
    ),  # basis：默认每5分钟
    "exchange_liquidation_interval": int(
        os.getenv("EXCHANGE_LIQUIDATION_INTERVAL_SECONDS", "300")
    ),  # 清算：默认每5分钟
    "exchange_positioning_interval": int(
        os.getenv("EXCHANGE_POSITIONING_INTERVAL_SECONDS", "900")
    ),  # 多空比：默认每15分钟
    "tokenomics_circulating_supply_interval": int(
        os.getenv("TOKENOMICS_CIRCULATING_SUPPLY_INTERVAL_SECONDS", "21600")
    ),
    "tokenomics_unlock_schedule_interval": int(
        os.getenv("TOKENOMICS_UNLOCK_SCHEDULE_INTERVAL_SECONDS", "21600")
    ),
    "tokenomics_unlock_realization_interval": int(
        os.getenv("TOKENOMICS_UNLOCK_REALIZATION_INTERVAL_SECONDS", "3600")
    ),
    "tokenomics_treasury_wallet_flow_interval": int(
        os.getenv("TOKENOMICS_TREASURY_WALLET_FLOW_INTERVAL_SECONDS", "3600")
    ),
    "tokenomics_staking_ratio_interval": int(
        os.getenv("TOKENOMICS_STAKING_RATIO_INTERVAL_SECONDS", "21600")
    ),
    "options_vol_surface_interval": int(
        os.getenv("OPTIONS_VOL_SURFACE_INTERVAL_SECONDS", "3600")
    ),
    "options_positioning_interval": int(
        os.getenv("OPTIONS_POSITIONING_INTERVAL_SECONDS", "3600")
    ),
    "options_relative_value_interval": int(
        os.getenv("OPTIONS_RELATIVE_VALUE_INTERVAL_SECONDS", "3600")
    ),
    "options_strike_concentration_interval": int(
        os.getenv("OPTIONS_STRIKE_CONCENTRATION_INTERVAL_SECONDS", "3600")
    ),
    "options_gamma_exposure_interval": int(
        os.getenv("OPTIONS_GAMMA_EXPOSURE_INTERVAL_SECONDS", "3600")
    ),
    "options_flow_activity_interval": int(
        os.getenv("OPTIONS_FLOW_ACTIVITY_INTERVAL_SECONDS", "3600")
    ),
    "options_expiry_structure_interval": int(
        os.getenv("OPTIONS_EXPIRY_STRUCTURE_INTERVAL_SECONDS", "3600")
    ),
    "options_hedge_pressure_interval": int(
        os.getenv("OPTIONS_HEDGE_PRESSURE_INTERVAL_SECONDS", "3600")
    ),
    "data_quality_audit_interval": int(
        os.getenv("DATA_QUALITY_AUDIT_INTERVAL_SECONDS", "300")
    ),  # 跨模块数据质量审计：默认每5分钟
    "perpetual_dex_interval": int(
        os.getenv("PERPETUAL_DEX_INTERVAL_SECONDS", "900")
    ),  # 永续 DEX 数据：默认每15分钟
    "onchain_address_interval": int(
        os.getenv("ONCHAIN_ADDRESS_INTERVAL_SECONDS", "600")
    ),  # 链上地址画像：默认每10分钟
    "dex_liquidity_interval": int(
        os.getenv("DEX_LIQUIDITY_INTERVAL_SECONDS", "1200")
    ),  # DEX 流动性：默认每20分钟
    "gas_network_interval": int(
        os.getenv("GAS_NETWORK_INTERVAL_SECONDS", "300")
    ),  # Gas/网络：默认每5分钟
    "governance_interval": int(
        os.getenv("GOVERNANCE_INTERVAL_SECONDS", "1800")
    ),  # 治理投票：默认每30分钟
    "liquidation_cascade_interval": int(
        os.getenv("LIQUIDATION_CASCADE_INTERVAL_SECONDS", "600")
    ),  # 清算级联分析：默认每10分钟
    "cross_venue_arb_interval": int(
        os.getenv("CROSS_VENUE_ARB_INTERVAL_SECONDS", "300")
    ),  # 跨所套利检测：默认每5分钟
    "onchain_lead_lag_interval": int(
        os.getenv("ONCHAIN_LEAD_LAG_INTERVAL_SECONDS", "1800")
    ),  # 链上领先滞后分析：默认每30分钟
    "stablecoin_flow_interval": int(
        os.getenv("STABLECOIN_FLOW_INTERVAL_SECONDS", "300")
    ),  # 稳定币事件流：默认每5分钟
    "token_unlock_interval": int(
        os.getenv("TOKEN_UNLOCK_INTERVAL_SECONDS", "3600")
    ),  # 代币解锁监控：默认每1小时
    "cex_orderbook_depth_interval": int(
        os.getenv("CEX_ORDERBOOK_DEPTH_INTERVAL_SECONDS", "30")
    ),  # 深度盘口：默认每30秒
    "whale_wallet_pnl_interval": int(
        os.getenv("WHALE_WALLET_PNL_INTERVAL_SECONDS", "1800")
    ),  # 巨鲸 PnL：默认每30分钟
    "nft_market_interval": int(
        os.getenv("NFT_MARKET_INTERVAL_SECONDS", "900")
    ),  # NFT 市场：默认每15分钟
    "defi_liquidation_interval": int(
        os.getenv("DEFI_LIQUIDATION_INTERVAL_SECONDS", "120")
    ),  # DeFi 清算：默认每2分钟
    "dex_trade_flow_interval": int(
        os.getenv("DEX_TRADE_FLOW_INTERVAL_SECONDS", "300")
    ),  # DEX 大单：默认每5分钟
    "cross_chain_messaging_interval": int(
        os.getenv("CROSS_CHAIN_MESSAGING_INTERVAL_SECONDS", "600")
    ),  # 跨链消息：默认每10分钟
    "lending_utilization_interval": int(
        os.getenv("LENDING_UTILIZATION_INTERVAL_SECONDS", "300")
    ),  # 借贷利用率：默认每5分钟
    "search_trend_interval": int(
        os.getenv("SEARCH_TREND_INTERVAL_SECONDS", "14400")
    ),  # 搜索趋势：默认每4小时
    "exchange_announcement_interval": int(
        os.getenv("EXCHANGE_ANNOUNCEMENT_INTERVAL_SECONDS", "900")
    ),  # 交易所公告：默认每15分钟
}

# 交易所数据保留策略（天）
EXCHANGE_DATA_RETENTION = {
    "ticker_days": int(os.getenv("TICKER_RETENTION_DAYS", "30")),
    "orderbook_days": int(os.getenv("ORDERBOOK_RETENTION_DAYS", "14")),
    "funding_days": int(os.getenv("FUNDING_RETENTION_DAYS", "365")),
    "trade_flow_days": int(os.getenv("TRADE_FLOW_RETENTION_DAYS", "30")),
    "open_interest_days": int(os.getenv("OPEN_INTEREST_RETENTION_DAYS", "365")),
    "basis_days": int(os.getenv("BASIS_RETENTION_DAYS", "365")),
    "liquidation_days": int(os.getenv("LIQUIDATION_RETENTION_DAYS", "90")),
    "positioning_days": int(os.getenv("POSITIONING_RETENTION_DAYS", "365")),
    "cleanup_interval": int(
        os.getenv(
            "EXCHANGE_DATA_CLEANUP_INTERVAL_SECONDS",
            "86400",
        )
    ),
}

# 代理配置（解决交易所地域封锁问题）
# ccxt 使用 HTTP/HTTPS/SOCKS 代理，格式示例：
#   HTTP:   http://127.0.0.1:7890
#   SOCKS5: socks5://127.0.0.1:1080
#   也支持带认证: socks5://user:pass@host:port
# 设为 None 表示不使用代理
PROXY_URL = os.getenv("CRYPTO_PROXY_URL", None)

# 网络请求配置
REQUEST_TIMEOUT = 60000  # 毫秒（代理环境下 load_markets 需要更长时间）
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def enabled_target_exchanges(target_exchanges: list[str] | None = None) -> list[str]:
    """Return TARGET_EXCHANGES entries that are enabled in EXCHANGE_CONFIG."""
    from config.symbols import TARGET_EXCHANGES as _DEFAULT_TARGETS

    names = list(target_exchanges if target_exchanges is not None else _DEFAULT_TARGETS)
    return [
        name
        for name in names
        if EXCHANGE_CONFIG.get(name, {}).get("enabled", False)
    ]

EXCHANGE_DERIVATIVES_CONFIG = {
    "trade_flow_interval_seconds": SCHEDULER_CONFIG["exchange_trade_flow_interval"],
    "open_interest_interval_seconds": SCHEDULER_CONFIG["exchange_open_interest_interval"],
    "basis_interval_seconds": SCHEDULER_CONFIG["exchange_basis_interval"],
    "liquidation_interval_seconds": SCHEDULER_CONFIG["exchange_liquidation_interval"],
    "positioning_interval_seconds": SCHEDULER_CONFIG["exchange_positioning_interval"],
    "trade_fetch_limit": int(os.getenv("EXCHANGE_TRADE_FETCH_LIMIT", "200")),
    "trade_bar_interval": os.getenv("EXCHANGE_TRADE_BAR_INTERVAL", "1m").strip() or "1m",
    "liquidation_bar_interval": os.getenv("EXCHANGE_LIQUIDATION_BAR_INTERVAL", "5m").strip() or "5m",
    "positioning_interval": os.getenv("EXCHANGE_POSITIONING_INTERVAL", "1h").strip() or "1h",
    "open_interest_interval": os.getenv("EXCHANGE_OPEN_INTEREST_INTERVAL", "5m").strip() or "5m",
    "basis_interval": os.getenv("EXCHANGE_BASIS_INTERVAL", "5m").strip() or "5m",
    "liquidation_url": os.getenv("EXCHANGE_LIQUIDATION_URL", "").strip(),
    "long_short_ratio_url": os.getenv("EXCHANGE_LONG_SHORT_RATIO_URL", "").strip(),
    "user_agent": os.getenv(
        "EXCHANGE_DERIVATIVES_USER_AGENT",
        "crypto-quant-derivatives-bot/1.0 (+https://local.quant.system)",
    ),
}

# 新闻采集配置
NEWS_CONFIG = {
    "interval_seconds": SCHEDULER_CONFIG["news_interval"],
    "timeout_seconds": int(os.getenv("NEWS_TIMEOUT_SECONDS", "20")),
    "max_items_per_source": int(os.getenv("NEWS_MAX_ITEMS_PER_SOURCE", "50")),
    "lookback_hours": int(os.getenv("NEWS_LOOKBACK_HOURS", "72")),
    "fetch_concurrency": int(os.getenv("NEWS_FETCH_CONCURRENCY", "8")),
    "max_connections_per_host": int(
        os.getenv("NEWS_MAX_CONNECTIONS_PER_HOST", "4")
    ),
    "resolver_mode": os.getenv("NEWS_RESOLVER_MODE", "auto").strip().lower(),
    "source_failure_threshold": int(
        os.getenv("NEWS_SOURCE_FAILURE_THRESHOLD", "2")
    ),
    "source_cooldown_base_seconds": int(
        os.getenv("NEWS_SOURCE_COOLDOWN_BASE_SECONDS", "300")
    ),
    "source_cooldown_max_seconds": int(
        os.getenv("NEWS_SOURCE_COOLDOWN_MAX_SECONDS", "3600")
    ),
    "user_agent": os.getenv(
        "NEWS_USER_AGENT",
        "crypto-quant-news-bot/1.0 (+https://local.quant.system)",
    ),
    "extra_feeds_json": os.getenv("NEWS_EXTRA_FEEDS_JSON", ""),
}

# 宏观数据采集配置
MACRO_CONFIG = {
    "market_interval_seconds": SCHEDULER_CONFIG["macro_market_interval"],
    "level_interval_seconds": SCHEDULER_CONFIG["macro_level_interval"],
    "enable_fed_funds_upper": os.getenv("MACRO_ENABLE_FED_FUNDS_UPPER", "1").strip() != "0",
    "enable_sp500": os.getenv("MACRO_ENABLE_SP500", "1").strip() != "0",
    "enable_vix": os.getenv("MACRO_ENABLE_VIX", "1").strip() != "0",
    "enable_ust_3m_yield": os.getenv("MACRO_ENABLE_UST_3M_YIELD", "1").strip() != "0",
    "enable_ust_30y_yield": os.getenv("MACRO_ENABLE_UST_30Y_YIELD", "1").strip() != "0",
    "enable_ust_10y_real_yield": os.getenv(
        "MACRO_ENABLE_UST_10Y_REAL_YIELD",
        "1",
    ).strip() != "0",
    "enable_us_10y_breakeven_inflation": os.getenv(
        "MACRO_ENABLE_US_10Y_BREAKEVEN_INFLATION",
        "1",
    ).strip() != "0",
    "enable_us_bbb_oas": os.getenv("MACRO_ENABLE_US_BBB_OAS", "1").strip() != "0",
    "enable_us_high_yield_oas": os.getenv(
        "MACRO_ENABLE_US_HIGH_YIELD_OAS",
        "1",
    ).strip() != "0",
    "enable_wti_crude": os.getenv("MACRO_ENABLE_WTI_CRUDE", "1").strip() != "0",
    "timeout_seconds": int(os.getenv("MACRO_TIMEOUT_SECONDS", "20")),
    "bootstrap_market_history_days": int(
        os.getenv("MACRO_MARKET_HISTORY_DAYS", "90")
    ),
    "bootstrap_daily_history_years": int(
        os.getenv("MACRO_DAILY_HISTORY_YEARS", "5")
    ),
    "recent_market_lookback_days": int(
        os.getenv("MACRO_RECENT_MARKET_LOOKBACK_DAYS", "10")
    ),
    "recent_rate_lookback_days": int(
        os.getenv("MACRO_RECENT_RATE_LOOKBACK_DAYS", "30")
    ),
    "user_agent": os.getenv(
        "MACRO_USER_AGENT",
        "crypto-quant-macro-bot/1.0 (+https://local.quant.system)",
    ),
}

# 补充特征采集配置
# GitHub Search API 的匿名配额很低；无令牌时默认关闭，用户可显式设置
# ALTERNATIVE_ENABLE_GITHUB=1 保留匿名采集行为。
_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
ALTERNATIVE_CONFIG = {
    "enable_github": os.getenv(
        "ALTERNATIVE_ENABLE_GITHUB", "1" if _GITHUB_TOKEN else "0"
    ).strip() != "0",
    "enable_stablecoin": os.getenv("ALTERNATIVE_ENABLE_STABLECOIN", "1").strip() != "0",
    "enable_google_trends": os.getenv(
        "ALTERNATIVE_ENABLE_GOOGLE_TRENDS",
        "1",
    ).strip() != "0",
    "github_interval_seconds": int(
        os.getenv("ALTERNATIVE_GITHUB_INTERVAL_SECONDS", "21600")
    ),
    "github_timeout_seconds": int(
        os.getenv("ALTERNATIVE_GITHUB_TIMEOUT_SECONDS", "20")
    ),
    "github_token": _GITHUB_TOKEN,
    "github_rest_base_url": os.getenv(
        "ALTERNATIVE_GITHUB_REST_BASE_URL",
        "https://api.github.com",
    ).rstrip("/"),
    "github_repo_group_version": os.getenv(
        "ALTERNATIVE_GITHUB_REPO_GROUP_VERSION",
        "v1",
    ).strip() or "v1",
    "stablecoin_interval_seconds": int(
        os.getenv("ALTERNATIVE_STABLECOIN_INTERVAL_SECONDS", "3600")
    ),
    "stablecoin_timeout_seconds": int(
        os.getenv("ALTERNATIVE_STABLECOIN_TIMEOUT_SECONDS", "20")
    ),
    "stablecoin_lookback_days": int(
        os.getenv("ALTERNATIVE_STABLECOIN_LOOKBACK_DAYS", "30")
    ),
    "stablecoin_rest_base_url": os.getenv(
        "ALTERNATIVE_STABLECOIN_REST_BASE_URL",
        "https://stablecoins.llama.fi",
    ).rstrip("/"),
    "google_trends_interval_seconds": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_INTERVAL_SECONDS", "43200")
    ),
    "google_trends_timeout_seconds": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_TIMEOUT_SECONDS", "20")
    ),
    "google_trends_base_url": os.getenv(
        "ALTERNATIVE_GOOGLE_TRENDS_BASE_URL",
        "https://trends.google.com/trends",
    ).rstrip("/"),
    "google_trends_geo": os.getenv(
        "ALTERNATIVE_GOOGLE_TRENDS_GEO",
        "US",
    ).strip().upper(),
    "google_trends_hl": os.getenv(
        "ALTERNATIVE_GOOGLE_TRENDS_HL",
        "en-US",
    ).strip() or "en-US",
    "google_trends_tz": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_TZ", "0")
    ),
    "google_trends_category": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_CATEGORY", "0")
    ),
    "google_trends_property": os.getenv(
        "ALTERNATIVE_GOOGLE_TRENDS_PROPERTY",
        "",
    ).strip(),
    "google_trends_window_days": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_WINDOW_DAYS", "90")
    ),
    "google_trends_bootstrap_history_days": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_BOOTSTRAP_HISTORY_DAYS", "1095")
    ),
    "google_trends_history_segment_days": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_HISTORY_SEGMENT_DAYS", "90")
    ),
    "google_trends_history_overlap_days": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_HISTORY_OVERLAP_DAYS", "30")
    ),
    "google_trends_related_limit": int(
        os.getenv("ALTERNATIVE_GOOGLE_TRENDS_RELATED_LIMIT", "10")
    ),
    "google_trends_query_version": os.getenv(
        "ALTERNATIVE_GOOGLE_TRENDS_QUERY_VERSION",
        "v1",
    ).strip() or "v1",
    "user_agent": os.getenv(
        "ALTERNATIVE_USER_AGENT",
        "crypto-quant-alternative-bot/1.0 (+https://local.quant.system)",
    ),
}

# 事件日历采集配置
EVENT_CALENDAR_CONFIG = {
    "interval_seconds": SCHEDULER_CONFIG["event_calendar_interval"],
    "timeout_seconds": int(os.getenv("EVENT_CALENDAR_TIMEOUT_SECONDS", "20")),
    "lookahead_days": int(os.getenv("EVENT_CALENDAR_LOOKAHEAD_DAYS", "90")),
    "history_lookback_days": int(
        os.getenv("EVENT_CALENDAR_HISTORY_LOOKBACK_DAYS", "7")
    ),
    "macro_source_url": os.getenv("EVENT_CALENDAR_MACRO_SOURCE_URL", "").strip(),
    "etf_source_url": os.getenv("EVENT_CALENDAR_ETF_SOURCE_URL", "").strip(),
    "unlock_source_url": os.getenv("EVENT_CALENDAR_UNLOCK_SOURCE_URL", "").strip(),
    "upgrade_source_url": os.getenv("EVENT_CALENDAR_UPGRADE_SOURCE_URL", "").strip(),
    "extra_sources_json": os.getenv(
        "EVENT_CALENDAR_EXTRA_SOURCES_JSON",
        "",
    ).strip(),
    "user_agent": os.getenv(
        "EVENT_CALENDAR_USER_AGENT",
        "crypto-quant-calendar-bot/1.0 (+https://local.quant.system)",
    ),
}

# 链上数据采集配置
ONCHAIN_CONFIG = {
    "enable_exchange_flow": os.getenv("ONCHAIN_ENABLE_EXCHANGE_FLOW", "1").strip() != "0",
    "enable_whale_activity": os.getenv("ONCHAIN_ENABLE_WHALE_ACTIVITY", "1").strip() != "0",
    "enable_stablecoin_flow": os.getenv("ONCHAIN_ENABLE_STABLECOIN_FLOW", "1").strip() != "0",
    "enable_bridge_netflow": os.getenv("ONCHAIN_ENABLE_BRIDGE_NETFLOW", "1").strip() != "0",
    "enable_exchange_reserve": os.getenv("ONCHAIN_ENABLE_EXCHANGE_RESERVE", "1").strip() != "0",
    "enable_protocol_tvl": os.getenv("ONCHAIN_ENABLE_PROTOCOL_TVL", "1").strip() != "0",
    "enable_network_usage": os.getenv("ONCHAIN_ENABLE_NETWORK_USAGE", "1").strip() != "0",
    "enable_staking_flow": os.getenv("ONCHAIN_ENABLE_STAKING_FLOW", "1").strip() != "0",
    "enable_dex_volume": os.getenv("ONCHAIN_ENABLE_DEX_VOLUME", "1").strip() != "0",
    "enable_stablecoin_supply": os.getenv("ONCHAIN_ENABLE_STABLECOIN_SUPPLY", "1").strip() != "0",
    "enable_market_sentiment": os.getenv("ONCHAIN_ENABLE_MARKET_SENTIMENT", "1").strip() != "0",
    "enable_global_market": os.getenv("ONCHAIN_ENABLE_GLOBAL_MARKET", "1").strip() != "0",
    "enable_defi_yields": os.getenv("ONCHAIN_ENABLE_DEFI_YIELDS", "1").strip() != "0",
    "timeout_seconds": int(os.getenv("ONCHAIN_TIMEOUT_SECONDS", "20")),
    "exchange_flow_interval_seconds": SCHEDULER_CONFIG["onchain_exchange_flow_interval"],
    "whale_activity_interval_seconds": SCHEDULER_CONFIG["onchain_whale_activity_interval"],
    "stablecoin_flow_interval_seconds": SCHEDULER_CONFIG["onchain_stablecoin_flow_interval"],
    "bridge_netflow_interval_seconds": int(
        os.getenv("ONCHAIN_BRIDGE_NETFLOW_INTERVAL_SECONDS", "1800")
    ),
    "exchange_reserve_interval_seconds": int(
        os.getenv("ONCHAIN_EXCHANGE_RESERVE_INTERVAL_SECONDS", "1800")
    ),
    "protocol_tvl_interval_seconds": int(
        os.getenv("ONCHAIN_PROTOCOL_TVL_INTERVAL_SECONDS", "1800")
    ),
    "network_usage_interval_seconds": int(
        os.getenv("ONCHAIN_NETWORK_USAGE_INTERVAL_SECONDS", "1800")
    ),
    "staking_flow_interval_seconds": int(
        os.getenv("ONCHAIN_STAKING_FLOW_INTERVAL_SECONDS", "1800")
    ),
    "dex_volume_interval_seconds": int(
        os.getenv("ONCHAIN_DEX_VOLUME_INTERVAL_SECONDS", "1800")
    ),
    "stablecoin_supply_interval_seconds": int(
        os.getenv("ONCHAIN_STABLECOIN_SUPPLY_INTERVAL_SECONDS", "1800")
    ),
    "market_sentiment_interval_seconds": int(
        os.getenv("ONCHAIN_MARKET_SENTIMENT_INTERVAL_SECONDS", "3600")
    ),
    "global_market_interval_seconds": int(
        os.getenv("ONCHAIN_GLOBAL_MARKET_INTERVAL_SECONDS", "1800")
    ),
    "defi_yields_interval_seconds": int(
        os.getenv("ONCHAIN_DEFI_YIELDS_INTERVAL_SECONDS", "3600")
    ),
    "default_interval": os.getenv("ONCHAIN_DEFAULT_INTERVAL", "1h").strip() or "1h",
    "default_lookback_hours": int(os.getenv("ONCHAIN_DEFAULT_LOOKBACK_HOURS", "48")),
    "exchange_flow_url": os.getenv("ONCHAIN_EXCHANGE_FLOW_URL", "").strip(),
    "whale_activity_url": os.getenv("ONCHAIN_WHALE_ACTIVITY_URL", "").strip(),
    "stablecoin_flow_url": os.getenv("ONCHAIN_STABLECOIN_FLOW_URL", "").strip(),
    "bridge_netflow_url": os.getenv("ONCHAIN_BRIDGE_NETFLOW_URL", "").strip(),
    "exchange_reserve_url": os.getenv("ONCHAIN_EXCHANGE_RESERVE_URL", "").strip(),
    "protocol_tvl_url": os.getenv("ONCHAIN_PROTOCOL_TVL_URL", "").strip(),
    "network_usage_url": os.getenv("ONCHAIN_NETWORK_USAGE_URL", "").strip(),
    "staking_flow_url": os.getenv("ONCHAIN_STAKING_FLOW_URL", "").strip(),
    "asset_entity_keys": os.getenv(
        "ONCHAIN_ASSET_ENTITY_KEYS",
        DEFAULT_TRACKED_ASSET_ENTITY_KEYS,
    ).strip(),
    "stablecoin_entity_keys": os.getenv(
        "ONCHAIN_STABLECOIN_ENTITY_KEYS",
        "USDT,USDC,FDUSD",
    ).strip(),
    "chain_entity_keys": os.getenv(
        "ONCHAIN_CHAIN_ENTITY_KEYS",
        "BITCOIN,ETHEREUM,SOLANA,ARBITRUM,BASE,SUI",
    ).strip(),
    "protocol_entity_keys": os.getenv(
        "ONCHAIN_PROTOCOL_ENTITY_KEYS",
        "AAVE,UNISWAP,JUPITER,CETUS",
    ).strip(),
    "extra_entities_json": os.getenv("ONCHAIN_EXTRA_ENTITIES_JSON", "").strip(),
    "user_agent": os.getenv(
        "ONCHAIN_USER_AGENT",
        "crypto-quant-onchain-bot/1.0 (+https://local.quant.system)",
    ),
}

TOKENOMICS_CONFIG = {
    "enable_circulating_supply": os.getenv(
        "TOKENOMICS_ENABLE_CIRCULATING_SUPPLY",
        "1",
    ).strip() != "0",
    "enable_unlock_schedule": os.getenv(
        "TOKENOMICS_ENABLE_UNLOCK_SCHEDULE",
        "1",
    ).strip() != "0",
    "enable_unlock_realization": os.getenv(
        "TOKENOMICS_ENABLE_UNLOCK_REALIZATION",
        "1",
    ).strip() != "0",
    "enable_treasury_wallet_flow": os.getenv(
        "TOKENOMICS_ENABLE_TREASURY_WALLET_FLOW",
        "1",
    ).strip() != "0",
    "enable_staking_ratio": os.getenv(
        "TOKENOMICS_ENABLE_STAKING_RATIO",
        "1",
    ).strip() != "0",
    "timeout_seconds": int(os.getenv("TOKENOMICS_TIMEOUT_SECONDS", "20")),
    "default_interval": os.getenv("TOKENOMICS_DEFAULT_INTERVAL", "1d").strip() or "1d",
    "default_lookback_hours": int(os.getenv("TOKENOMICS_DEFAULT_LOOKBACK_HOURS", "168")),
    "circulating_supply_interval_seconds": SCHEDULER_CONFIG["tokenomics_circulating_supply_interval"],
    "unlock_schedule_interval_seconds": SCHEDULER_CONFIG["tokenomics_unlock_schedule_interval"],
    "unlock_realization_interval_seconds": SCHEDULER_CONFIG["tokenomics_unlock_realization_interval"],
    "treasury_wallet_flow_interval_seconds": SCHEDULER_CONFIG["tokenomics_treasury_wallet_flow_interval"],
    "staking_ratio_interval_seconds": SCHEDULER_CONFIG["tokenomics_staking_ratio_interval"],
    "circulating_supply_url": os.getenv("TOKENOMICS_CIRCULATING_SUPPLY_URL", "").strip(),
    "unlock_schedule_url": os.getenv("TOKENOMICS_UNLOCK_SCHEDULE_URL", "").strip(),
    "unlock_realization_url": os.getenv("TOKENOMICS_UNLOCK_REALIZATION_URL", "").strip(),
    "treasury_wallet_flow_url": os.getenv("TOKENOMICS_TREASURY_WALLET_FLOW_URL", "").strip(),
    "staking_ratio_url": os.getenv("TOKENOMICS_STAKING_RATIO_URL", "").strip(),
    "asset_entity_keys": os.getenv(
        "TOKENOMICS_ASSET_ENTITY_KEYS",
        DEFAULT_TRACKED_ASSET_ENTITY_KEYS,
    ).strip(),
    "extra_entities_json": os.getenv("TOKENOMICS_EXTRA_ENTITIES_JSON", "").strip(),
    "user_agent": os.getenv(
        "TOKENOMICS_USER_AGENT",
        "crypto-quant-tokenomics-bot/1.0 (+https://local.quant.system)",
    ),
}

OPTIONS_CONFIG = {
    "enable_vol_surface": os.getenv("OPTIONS_ENABLE_VOL_SURFACE", "1").strip() != "0",
    "enable_positioning": os.getenv("OPTIONS_ENABLE_POSITIONING", "1").strip() != "0",
    "enable_relative_value": os.getenv("OPTIONS_ENABLE_RELATIVE_VALUE", "1").strip() != "0",
    "enable_strike_concentration": os.getenv(
        "OPTIONS_ENABLE_STRIKE_CONCENTRATION",
        "1",
    ).strip() != "0",
    "enable_gamma_exposure": os.getenv(
        "OPTIONS_ENABLE_GAMMA_EXPOSURE",
        "1",
    ).strip() != "0",
    "enable_flow_activity": os.getenv(
        "OPTIONS_ENABLE_FLOW_ACTIVITY",
        "1",
    ).strip() != "0",
    "enable_expiry_structure": os.getenv(
        "OPTIONS_ENABLE_EXPIRY_STRUCTURE",
        "1",
    ).strip() != "0",
    "enable_hedge_pressure": os.getenv(
        "OPTIONS_ENABLE_HEDGE_PRESSURE",
        "1",
    ).strip() != "0",
    "timeout_seconds": int(os.getenv("OPTIONS_TIMEOUT_SECONDS", "20")),
    "default_interval": os.getenv("OPTIONS_DEFAULT_INTERVAL", "1h").strip() or "1h",
    "default_lookback_hours": int(os.getenv("OPTIONS_DEFAULT_LOOKBACK_HOURS", "72")),
    "vol_surface_interval_seconds": SCHEDULER_CONFIG["options_vol_surface_interval"],
    "positioning_interval_seconds": SCHEDULER_CONFIG["options_positioning_interval"],
    "relative_value_interval_seconds": SCHEDULER_CONFIG["options_relative_value_interval"],
    "strike_concentration_interval_seconds": SCHEDULER_CONFIG[
        "options_strike_concentration_interval"
    ],
    "gamma_exposure_interval_seconds": SCHEDULER_CONFIG[
        "options_gamma_exposure_interval"
    ],
    "flow_activity_interval_seconds": SCHEDULER_CONFIG[
        "options_flow_activity_interval"
    ],
    "expiry_structure_interval_seconds": SCHEDULER_CONFIG[
        "options_expiry_structure_interval"
    ],
    "hedge_pressure_interval_seconds": SCHEDULER_CONFIG[
        "options_hedge_pressure_interval"
    ],
    "vol_surface_url": os.getenv("OPTIONS_VOL_SURFACE_URL", "").strip(),
    "positioning_url": os.getenv("OPTIONS_POSITIONING_URL", "").strip(),
    "relative_value_url": os.getenv("OPTIONS_RELATIVE_VALUE_URL", "").strip(),
    "strike_concentration_url": os.getenv(
        "OPTIONS_STRIKE_CONCENTRATION_URL",
        "",
    ).strip(),
    "gamma_exposure_url": os.getenv(
        "OPTIONS_GAMMA_EXPOSURE_URL",
        "",
    ).strip(),
    "flow_activity_url": os.getenv(
        "OPTIONS_FLOW_ACTIVITY_URL",
        "",
    ).strip(),
    "expiry_structure_url": os.getenv(
        "OPTIONS_EXPIRY_STRUCTURE_URL",
        "",
    ).strip(),
    "hedge_pressure_url": os.getenv(
        "OPTIONS_HEDGE_PRESSURE_URL",
        "",
    ).strip(),
    "asset_entity_keys": os.getenv(
        "OPTIONS_ASSET_ENTITY_KEYS",
        DEFAULT_TRACKED_ASSET_ENTITY_KEYS,
    ).strip(),
    "extra_entities_json": os.getenv("OPTIONS_EXTRA_ENTITIES_JSON", "").strip(),
    "user_agent": os.getenv(
        "OPTIONS_USER_AGENT",
        "crypto-quant-options-bot/1.0 (+https://local.quant.system)",
    ),
}

DATA_QUALITY_CONFIG = {
    "audit_interval_seconds": SCHEDULER_CONFIG["data_quality_audit_interval"],
    "default_audit_scope": os.getenv(
        "DATA_QUALITY_AUDIT_SCOPE",
        "market_world_model",
    ).strip() or "market_world_model",
}


# ---------------------------------------------------------------------------
# 启动时配置验证
# ---------------------------------------------------------------------------

def validate_config() -> list[str]:
    """校验调度/网络/保留策略配置的合理性，返回告警列表。

    不抛异常 — 只记录警告并返回，让调用方决定是否中止。
    """
    warnings: list[str] = []

    # 调度间隔合理性检查
    for key, value in SCHEDULER_CONFIG.items():
        if value < 1:
            warnings.append(f"SCHEDULER_CONFIG[{key}]={value} 不合法（必须 >= 1s）")
        elif value < 3 and "interval" in key:
            warnings.append(
                f"SCHEDULER_CONFIG[{key}]={value}s 过短，可能导致 API 限流"
            )

    # 保留天数合理性
    for key, value in EXCHANGE_DATA_RETENTION.items():
        if value < 1:
            warnings.append(f"EXCHANGE_DATA_RETENTION[{key}]={value} 不合法（必须 >= 1）")

    # 网络超时合理性
    if REQUEST_TIMEOUT < 5000:
        warnings.append(f"REQUEST_TIMEOUT={REQUEST_TIMEOUT}ms 过短，代理环境下建议 >= 30000")
    if MAX_RETRIES < 1:
        warnings.append(f"MAX_RETRIES={MAX_RETRIES} 不合法（必须 >= 1）")

    for w in warnings:
        logger.warning("配置校验: {}", w)

    return warnings
