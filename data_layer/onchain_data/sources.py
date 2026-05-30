import json

from loguru import logger

from config.settings import ONCHAIN_CONFIG
from data_layer.onchain_data.models import (
    OnchainFactorDefinition,
    OnchainSourceDefinition,
)


def _normalize_filter(values: list[str] | None) -> set[str]:
    return {
        value.strip().lower()
        for value in (values or [])
        if value.strip()
    }


def _split_csv(raw_value: str) -> list[str]:
    return [
        item.strip().upper()
        for item in raw_value.split(",")
        if item.strip()
    ]


DEFAULT_ONCHAIN_SOURCES = [
    OnchainSourceDefinition(
        source_name="exchange_flow",
        name="Exchange Flow API",
        description="资产级交易所净流入流出标准化接口。",
        collector_key="exchange_flow",
        factor_id="exchange_netflow",
        entity_type="asset",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["exchange_flow_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_exchange_flow"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="whale_activity",
        name="Whale Activity API",
        description="资产级大额转账次数标准化接口。",
        collector_key="whale_activity",
        factor_id="whale_transfer_count",
        entity_type="asset",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["whale_activity_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_whale_activity"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="stablecoin_flow",
        name="Stablecoin Flow API",
        description="稳定币流入交易所标准化接口。",
        collector_key="stablecoin_flow",
        factor_id="stablecoin_exchange_inflow",
        entity_type="stablecoin_asset",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["stablecoin_flow_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_stablecoin_flow"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["stablecoin_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="bridge_netflow",
        name="Bridge Netflow API",
        description="资产-链级跨链桥净流标准化接口。",
        collector_key="bridge_netflow",
        factor_id="bridge_netflow",
        entity_type="asset_chain",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["bridge_netflow_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_bridge_netflow"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="exchange_reserve",
        name="Exchange Reserve API",
        description="资产级交易所储备标准化接口。",
        collector_key="exchange_reserve",
        factor_id="exchange_reserve_balance",
        entity_type="asset",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["exchange_reserve_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_exchange_reserve"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="protocol_tvl",
        name="Protocol TVL API",
        description="协议级 TVL 与变化标准化接口。",
        collector_key="protocol_tvl",
        factor_id="protocol_tvl",
        entity_type="protocol",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint="https://api.llama.fi/protocols",
        enabled=ONCHAIN_CONFIG["enable_protocol_tvl"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["protocol_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="network_usage",
        name="Network Usage API",
        description="链级活跃地址、交易数和手续费标准化接口。",
        collector_key="network_usage",
        factor_id="active_addresses",
        entity_type="chain",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint="https://api.llama.fi/overview/fees",
        enabled=ONCHAIN_CONFIG["enable_network_usage"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["chain_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="staking_flow",
        name="Staking Flow API",
        description="资产级质押净流标准化接口。",
        collector_key="staking_flow",
        factor_id="staking_netflow",
        entity_type="asset",
        default_interval=ONCHAIN_CONFIG["default_interval"],
        endpoint=ONCHAIN_CONFIG["staking_flow_url"] or None,
        enabled=ONCHAIN_CONFIG["enable_staking_flow"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="dex_volume",
        name="DEX Volume (DeFiLlama)",
        description="链级 DEX 交易量，来源 DeFiLlama 公开 API。",
        collector_key="dex_volume",
        factor_id="dex_volume_24h",
        entity_type="chain",
        default_interval="1d",
        endpoint="https://api.llama.fi/overview/dexs",
        enabled=ONCHAIN_CONFIG["enable_dex_volume"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["chain_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="stablecoin_supply",
        name="Stablecoin Supply (DeFiLlama)",
        description="稳定币市值与 7d 变化，来源 DeFiLlama 公开 API。",
        collector_key="stablecoin_supply",
        factor_id="stablecoin_mcap",
        entity_type="stablecoin_asset",
        default_interval="1d",
        endpoint="https://stablecoins.llama.fi/stablecoins?includePrices=true",
        enabled=ONCHAIN_CONFIG["enable_stablecoin_supply"],
        raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["stablecoin_entity_keys"])},
    ),
    OnchainSourceDefinition(
        source_name="market_sentiment",
        name="Market Sentiment (Fear & Greed)",
        description="加密市场恐惧贪婪指数，来源 alternative.me 免费 API。",
        collector_key="market_sentiment",
        factor_id="fear_greed_index",
        entity_type="market",
        default_interval="1d",
        endpoint="https://api.alternative.me/fng/?limit=1&format=json",
        enabled=ONCHAIN_CONFIG["enable_market_sentiment"],
        raw_meta={"default_entities": ["CRYPTO"]},
    ),
    OnchainSourceDefinition(
        source_name="global_market",
        name="Global Market (CoinGecko)",
        description="全球加密市场总览数据，来源 CoinGecko 免费 API。",
        collector_key="global_market",
        factor_id="total_market_cap",
        entity_type="market",
        default_interval="1h",
        endpoint="https://api.coingecko.com/api/v3/global",
        enabled=ONCHAIN_CONFIG["enable_global_market"],
        raw_meta={"default_entities": ["CRYPTO"]},
    ),
    OnchainSourceDefinition(
        source_name="defi_yields",
        name="DeFi Yields (DeFiLlama)",
        description="DeFi 稳定币收益率中位数与总 TVL，来源 DeFiLlama 免费 API。",
        collector_key="defi_yields",
        factor_id="defi_stablecoin_yield_median",
        entity_type="market",
        default_interval="1d",
        endpoint="https://yields.llama.fi/pools",
        enabled=ONCHAIN_CONFIG["enable_defi_yields"],
        raw_meta={"default_entities": ["CRYPTO"]},
    ),
]


def _load_extra_entities() -> list[dict[str, object]]:
    raw_value = ONCHAIN_CONFIG.get("extra_entities_json", "").strip()
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        logger.error(f"解析 ONCHAIN_EXTRA_ENTITIES_JSON 失败: {exc}")
        return []
    if not isinstance(payload, list):
        logger.error("ONCHAIN_EXTRA_ENTITIES_JSON 必须是 JSON 数组")
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def load_onchain_sources(
    source_names: list[str] | None = None,
    enabled_only: bool = True,
) -> list[OnchainSourceDefinition]:
    normalized_names = _normalize_filter(source_names)
    selected: list[OnchainSourceDefinition] = []
    for source in DEFAULT_ONCHAIN_SOURCES:
        if enabled_only and not source.enabled:
            continue
        if normalized_names and source.source_name.lower() not in normalized_names:
            continue
        selected.append(source)
    return selected


def load_onchain_factors(
    factor_ids: list[str] | None = None,
    source_names: list[str] | None = None,
    enabled_only: bool = True,
) -> list[OnchainFactorDefinition]:
    normalized_factor_ids = _normalize_filter(factor_ids)
    normalized_source_names = _normalize_filter(source_names)

    definitions = [
        OnchainFactorDefinition(
            factor_id="exchange_netflow",
            name="Exchange Netflow",
            category="exchange_flow",
            factor_type="netflow",
            entity_scope="asset",
            entity_type="asset",
            description="资产级交易所净流入流出，负值代表净流出。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="exchange_flow",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_exchange_flow"],
            raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
        ),
        OnchainFactorDefinition(
            factor_id="whale_transfer_count",
            name="Whale Transfer Count",
            category="whale_activity",
            factor_type="event_count",
            entity_scope="asset",
            entity_type="asset",
            description="大额链上转账次数。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="count",
            source_name="whale_activity",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_whale_activity"],
            raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["asset_entity_keys"])},
        ),
        OnchainFactorDefinition(
            factor_id="stablecoin_exchange_inflow",
            name="Stablecoin Exchange Inflow",
            category="stablecoin_flow",
            factor_type="inflow",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币流入交易所规模。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="stablecoin_flow",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=3600,
            enabled=ONCHAIN_CONFIG["enable_stablecoin_flow"],
            raw_meta={"default_entities": _split_csv(ONCHAIN_CONFIG["stablecoin_entity_keys"])},
        ),
        OnchainFactorDefinition(
            factor_id="bridge_inflow",
            name="Bridge Inflow",
            category="bridge_flow",
            factor_type="inflow",
            entity_scope="asset_chain",
            entity_type="asset_chain",
            description="资产-链级桥流入。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="bridge_netflow",
            source_symbol="asset_chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_bridge_netflow"],
        ),
        OnchainFactorDefinition(
            factor_id="bridge_outflow",
            name="Bridge Outflow",
            category="bridge_flow",
            factor_type="outflow",
            entity_scope="asset_chain",
            entity_type="asset_chain",
            description="资产-链级桥流出。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="bridge_netflow",
            source_symbol="asset_chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_bridge_netflow"],
        ),
        OnchainFactorDefinition(
            factor_id="bridge_netflow",
            name="Bridge Netflow",
            category="bridge_flow",
            factor_type="netflow",
            entity_scope="asset_chain",
            entity_type="asset_chain",
            description="资产-链级桥净流。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="bridge_netflow",
            source_symbol="asset_chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_bridge_netflow"],
        ),
        OnchainFactorDefinition(
            factor_id="exchange_reserve_balance",
            name="Exchange Reserve Balance",
            category="exchange_reserve",
            factor_type="level",
            entity_scope="asset",
            entity_type="asset",
            description="资产级交易所储备余额。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="exchange_reserve",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_exchange_reserve"],
        ),
        OnchainFactorDefinition(
            factor_id="exchange_reserve_change_24h",
            name="Exchange Reserve Change 24H",
            category="exchange_reserve",
            factor_type="change",
            entity_scope="asset",
            entity_type="asset",
            description="资产级交易所储备 24 小时变化。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="exchange_reserve",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_exchange_reserve"],
        ),
        OnchainFactorDefinition(
            factor_id="protocol_tvl",
            name="Protocol TVL",
            category="protocol_tvl",
            factor_type="level",
            entity_scope="protocol",
            entity_type="protocol",
            description="协议 TVL。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="protocol_tvl",
            source_symbol="protocol",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_protocol_tvl"],
        ),
        OnchainFactorDefinition(
            factor_id="protocol_tvl_change_24h",
            name="Protocol TVL Change 24H",
            category="protocol_tvl",
            factor_type="change",
            entity_scope="protocol",
            entity_type="protocol",
            description="协议 TVL 24 小时变化。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="protocol_tvl",
            source_symbol="protocol",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_protocol_tvl"],
        ),
        OnchainFactorDefinition(
            factor_id="protocol_tvl_change_7d",
            name="Protocol TVL Change 7D",
            category="protocol_tvl",
            factor_type="change",
            entity_scope="protocol",
            entity_type="protocol",
            description="协议 TVL 7 日变化。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="protocol_tvl",
            source_symbol="protocol",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_protocol_tvl"],
        ),
        OnchainFactorDefinition(
            factor_id="active_addresses",
            name="Active Addresses",
            category="network_usage",
            factor_type="count",
            entity_scope="chain",
            entity_type="chain",
            description="链级活跃地址数。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="count",
            source_name="network_usage",
            source_symbol="chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_network_usage"],
        ),
        OnchainFactorDefinition(
            factor_id="transaction_count",
            name="Transaction Count",
            category="network_usage",
            factor_type="count",
            entity_scope="chain",
            entity_type="chain",
            description="链级交易数。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="count",
            source_name="network_usage",
            source_symbol="chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_network_usage"],
        ),
        OnchainFactorDefinition(
            factor_id="fees_paid",
            name="Fees Paid",
            category="network_usage",
            factor_type="sum",
            entity_scope="chain",
            entity_type="chain",
            description="链级手续费总额。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="network_usage",
            source_symbol="chain",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_network_usage"],
        ),
        OnchainFactorDefinition(
            factor_id="staking_inflow",
            name="Staking Inflow",
            category="staking_flow",
            factor_type="inflow",
            entity_scope="asset",
            entity_type="asset",
            description="质押流入。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="staking_flow",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_staking_flow"],
        ),
        OnchainFactorDefinition(
            factor_id="staking_outflow",
            name="Staking Outflow",
            category="staking_flow",
            factor_type="outflow",
            entity_scope="asset",
            entity_type="asset",
            description="质押流出。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="staking_flow",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_staking_flow"],
        ),
        OnchainFactorDefinition(
            factor_id="staking_netflow",
            name="Staking Netflow",
            category="staking_flow",
            factor_type="netflow",
            entity_scope="asset",
            entity_type="asset",
            description="质押净流。",
            default_interval=ONCHAIN_CONFIG["default_interval"],
            unit="usd",
            source_name="staking_flow",
            source_symbol="asset",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_staking_flow"],
        ),
        # --- DEX Volume (DeFiLlama) ---
        OnchainFactorDefinition(
            factor_id="dex_volume_24h",
            name="DEX Volume 24H",
            category="dex_volume",
            factor_type="sum",
            entity_scope="chain",
            entity_type="chain",
            description="链级 DEX 24 小时交易量。",
            default_interval="1d",
            unit="usd",
            source_name="dex_volume",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_dex_volume"],
        ),
        OnchainFactorDefinition(
            factor_id="dex_volume_change_1d",
            name="DEX Volume Change 1D",
            category="dex_volume",
            factor_type="change",
            entity_scope="chain",
            entity_type="chain",
            description="全市场 DEX 交易量日变化率。",
            default_interval="1d",
            unit="percent",
            source_name="dex_volume",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_dex_volume"],
        ),
        # --- Stablecoin Supply (DeFiLlama) ---
        OnchainFactorDefinition(
            factor_id="stablecoin_mcap",
            name="Stablecoin Market Cap",
            category="stablecoin_supply",
            factor_type="level",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币流通市值。",
            default_interval="1d",
            unit="usd",
            source_name="stablecoin_supply",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_stablecoin_supply"],
        ),
        OnchainFactorDefinition(
            factor_id="stablecoin_mcap_change_7d",
            name="Stablecoin Market Cap Change 7D",
            category="stablecoin_supply",
            factor_type="change",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币市值 7 日变化率（铸造/赎回指标）。",
            default_interval="1d",
            unit="percent",
            source_name="stablecoin_supply",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_stablecoin_supply"],
        ),
        # --- Market Sentiment (Fear & Greed) ---
        OnchainFactorDefinition(
            factor_id="fear_greed_index",
            name="Fear & Greed Index",
            category="market_sentiment",
            factor_type="level",
            entity_scope="market",
            entity_type="market",
            description="加密市场恐惧贪婪指数 (0=极度恐惧, 100=极度贪婪)。",
            default_interval="1d",
            unit="index",
            source_name="market_sentiment",
            source_symbol="alternative_me",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=ONCHAIN_CONFIG["enable_market_sentiment"],
        ),
        # --- Global Market (CoinGecko) ---
        OnchainFactorDefinition(
            factor_id="total_market_cap",
            name="Total Crypto Market Cap",
            category="global_market",
            factor_type="level",
            entity_scope="market",
            entity_type="market",
            description="加密市场总市值。",
            default_interval="1h",
            unit="usd",
            source_name="global_market",
            source_symbol="coingecko",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_global_market"],
        ),
        OnchainFactorDefinition(
            factor_id="btc_dominance",
            name="BTC Dominance",
            category="global_market",
            factor_type="level",
            entity_scope="market",
            entity_type="market",
            description="BTC 市值占比。",
            default_interval="1h",
            unit="percent",
            source_name="global_market",
            source_symbol="coingecko",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_global_market"],
        ),
        OnchainFactorDefinition(
            factor_id="market_cap_change_24h",
            name="Market Cap Change 24H",
            category="global_market",
            factor_type="change",
            entity_scope="market",
            entity_type="market",
            description="加密市场总市值 24 小时变化率。",
            default_interval="1h",
            unit="percent",
            source_name="global_market",
            source_symbol="coingecko",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_global_market"],
        ),
        OnchainFactorDefinition(
            factor_id="total_volume_24h",
            name="Total Volume 24H",
            category="global_market",
            factor_type="sum",
            entity_scope="market",
            entity_type="market",
            description="加密市场 24 小时总成交量。",
            default_interval="1h",
            unit="usd",
            source_name="global_market",
            source_symbol="coingecko",
            config_version="v1",
            staleness_ttl_seconds=7200,
            enabled=ONCHAIN_CONFIG["enable_global_market"],
        ),
        # --- DeFi Yields (DeFiLlama) ---
        OnchainFactorDefinition(
            factor_id="defi_stablecoin_yield_median",
            name="DeFi Stablecoin Yield Median",
            category="defi_yields",
            factor_type="level",
            entity_scope="market",
            entity_type="market",
            description="DeFi 稳定币池中位数收益率 (TVL>$10M)，流动性松紧指标。",
            default_interval="1d",
            unit="percent",
            source_name="defi_yields",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=ONCHAIN_CONFIG["enable_defi_yields"],
        ),
        OnchainFactorDefinition(
            factor_id="defi_total_tvl",
            name="DeFi Total TVL",
            category="defi_yields",
            factor_type="level",
            entity_scope="market",
            entity_type="market",
            description="DeFi 全市场总锁仓量。",
            default_interval="1d",
            unit="usd",
            source_name="defi_yields",
            source_symbol="defillama",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=ONCHAIN_CONFIG["enable_defi_yields"],
        ),
    ]

    results: list[OnchainFactorDefinition] = []
    for definition in definitions:
        if enabled_only and not definition.enabled:
            continue
        if normalized_factor_ids and definition.factor_id.lower() not in normalized_factor_ids:
            continue
        if normalized_source_names and definition.source_name.lower() not in normalized_source_names:
            continue
        results.append(definition)
    return results


def load_onchain_entities(
    source_names: list[str] | None = None,
    entity_keys: list[str] | None = None,
) -> list[dict[str, str]]:
    normalized_source_names = _normalize_filter(source_names)
    normalized_entity_keys = {
        value.strip().upper()
        for value in (entity_keys or [])
        if value.strip()
    }

    rows: list[dict[str, str]] = []
    for entity_key in _split_csv(ONCHAIN_CONFIG["asset_entity_keys"]):
        for source_name in ("exchange_flow", "whale_activity"):
            if normalized_source_names and source_name not in normalized_source_names:
                continue
            if normalized_entity_keys and entity_key not in normalized_entity_keys:
                continue
            rows.append(
                {
                    "source_name": source_name,
                    "entity_type": "asset",
                    "entity_key": entity_key,
                    "name": entity_key,
                    "description": f"{entity_key} 链上观察对象",
                }
            )

    for entity_key in _split_csv(ONCHAIN_CONFIG["stablecoin_entity_keys"]):
        if normalized_source_names and "stablecoin_flow" not in normalized_source_names:
            continue
        if normalized_entity_keys and entity_key not in normalized_entity_keys:
            continue
        rows.append(
            {
                "source_name": "stablecoin_flow",
                "entity_type": "stablecoin_asset",
                "entity_key": entity_key,
                "name": entity_key,
                "description": f"{entity_key} 稳定币链上观察对象",
            }
        )

    for asset_key in _split_csv(ONCHAIN_CONFIG["asset_entity_keys"]):
        for source_name in ("exchange_reserve", "staking_flow"):
            if normalized_source_names and source_name not in normalized_source_names:
                continue
            if normalized_entity_keys and asset_key not in normalized_entity_keys:
                continue
            rows.append(
                {
                    "source_name": source_name,
                    "entity_type": "asset",
                    "entity_key": asset_key,
                    "name": asset_key,
                    "description": f"{asset_key} 链上扩展观察对象",
                }
            )

    for protocol_key in _split_csv(ONCHAIN_CONFIG["protocol_entity_keys"]):
        if normalized_source_names and "protocol_tvl" not in normalized_source_names:
            continue
        if normalized_entity_keys and protocol_key not in normalized_entity_keys:
            continue
        rows.append(
            {
                "source_name": "protocol_tvl",
                "entity_type": "protocol",
                "entity_key": protocol_key,
                "name": protocol_key,
                "description": f"{protocol_key} TVL 观察对象",
            }
        )

    for chain_key in _split_csv(ONCHAIN_CONFIG["chain_entity_keys"]):
        if normalized_source_names and "network_usage" not in normalized_source_names:
            continue
        if normalized_entity_keys and chain_key not in normalized_entity_keys:
            continue
        rows.append(
            {
                "source_name": "network_usage",
                "entity_type": "chain",
                "entity_key": chain_key,
                "name": chain_key,
                "description": f"{chain_key} 链使用率观察对象",
            }
        )

    chain_keys = _split_csv(ONCHAIN_CONFIG["chain_entity_keys"])
    for asset_key in _split_csv(ONCHAIN_CONFIG["asset_entity_keys"]):
        for chain_key in chain_keys:
            entity_key = f"{asset_key}:{chain_key}"
            if normalized_source_names and "bridge_netflow" not in normalized_source_names:
                continue
            if normalized_entity_keys and entity_key not in normalized_entity_keys:
                continue
            rows.append(
                {
                    "source_name": "bridge_netflow",
                    "entity_type": "asset_chain",
                    "entity_key": entity_key,
                    "name": entity_key,
                    "description": f"{asset_key} 在 {chain_key} 的桥资金观察对象",
                }
            )

    for item in _load_extra_entities():
        source_name = str(item.get("source_name") or "").strip().lower()
        entity_key = str(item.get("entity_key") or "").strip().upper()
        if not source_name or not entity_key:
            continue
        if normalized_source_names and source_name not in normalized_source_names:
            continue
        if normalized_entity_keys and entity_key not in normalized_entity_keys:
            continue
        rows.append(
            {
                "source_name": source_name,
                "entity_type": str(item.get("entity_type") or "asset"),
                "entity_key": entity_key,
                "name": str(item.get("name") or entity_key),
                "description": str(item.get("description") or ""),
            }
        )
    return rows
