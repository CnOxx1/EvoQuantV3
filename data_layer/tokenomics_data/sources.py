import json
from pathlib import Path

from loguru import logger

from config.settings import TOKENOMICS_CONFIG
from data_layer.tokenomics_data.models import (
    TokenomicsFactorDefinition,
    TokenomicsSourceDefinition,
)


REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
TOKEN_PROFILES_FILE = "token_profiles.json"
TREASURY_WALLET_GROUPS_FILE = "treasury_wallet_groups.json"


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


def _registry_path(filename: str) -> Path:
    return REGISTRY_DIR / filename


def _load_registry_items(
    filename: str,
    *,
    required_fields: set[str],
) -> list[dict[str, object]]:
    path = _registry_path(filename)
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError(f"registry 文件必须是 list: {path}")

    rows: list[dict[str, object]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"registry 项必须是 dict: {path}#{index}")
        missing_fields = [
            field
            for field in sorted(required_fields)
            if field not in item
        ]
        if missing_fields:
            raise ValueError(
                f"registry 项缺少字段 {missing_fields}: {path}#{index}"
            )
        rows.append(dict(item))
    return rows


def load_token_profiles(
    entity_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    normalized_entity_keys = {
        value.strip().upper()
        for value in (entity_keys or [])
        if value.strip()
    }
    rows = _load_registry_items(
        TOKEN_PROFILES_FILE,
        required_fields={"entity_key", "name", "description"},
    )
    results: list[dict[str, object]] = []
    for row in rows:
        entity_key = str(row["entity_key"]).strip().upper()
        if normalized_entity_keys and entity_key not in normalized_entity_keys:
            continue
        results.append(
            {
                "entity_key": entity_key,
                "name": str(row.get("name") or entity_key).strip(),
                "description": str(row.get("description") or "").strip(),
            }
        )
    return results


def load_treasury_wallet_groups(
    entity_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    normalized_entity_keys = {
        value.strip().upper()
        for value in (entity_keys or [])
        if value.strip()
    }
    rows = _load_registry_items(
        TREASURY_WALLET_GROUPS_FILE,
        required_fields={
            "entity_key",
            "name",
            "description",
            "verification_status",
            "address_count",
            "source_refs",
        },
    )
    results: list[dict[str, object]] = []
    for row in rows:
        entity_key = str(row["entity_key"]).strip().upper()
        if normalized_entity_keys and entity_key not in normalized_entity_keys:
            continue
        verification_status = str(
            row.get("verification_status") or "unknown"
        ).strip().lower()
        address_count = max(0, int(row.get("address_count") or 0))
        source_refs = [
            str(item).strip()
            for item in (row.get("source_refs") or [])
            if str(item).strip()
        ]
        has_real_addresses = address_count > 0
        is_verified = verification_status in {"verified", "maintained"}
        quality_notes: list[str] = []
        if verification_status == "placeholder":
            quality_notes.append("wallet group 当前仍是 placeholder，尚未绑定真实地址集合。")
        elif not is_verified:
            quality_notes.append("wallet group 还没有达到 verified/maintained 状态。")
        if not has_real_addresses:
            quality_notes.append("wallet group 当前 address_count=0，缺少可核验的钱包样本。")
        if not source_refs:
            quality_notes.append("wallet group 当前没有维护来源引用，无法追溯口径。")
        results.append(
            {
                "entity_key": entity_key,
                "name": str(row.get("name") or entity_key).strip(),
                "description": str(row.get("description") or "").strip(),
                "wallet_group_type": str(
                    row.get("wallet_group_type") or "foundation_or_treasury"
                ).strip(),
                "verification_status": verification_status,
                "address_count": address_count,
                "source_refs": source_refs,
                "source_ref_count": len(source_refs),
                "has_real_addresses": has_real_addresses,
                "is_verified": is_verified,
                "is_ready_for_ai": is_verified and has_real_addresses and bool(source_refs),
                "quality_notes": quality_notes,
            }
        )
    return results


DEFAULT_TOKENOMICS_SOURCES = [
    TokenomicsSourceDefinition(
        source_name="circulating_supply",
        name="Circulating Supply API",
        description="流通盘、自由流通盘和通胀率标准化接口。",
        collector_key="circulating_supply",
        primary_factor_id="circulating_supply",
        entity_type="asset",
        default_interval=TOKENOMICS_CONFIG["default_interval"],
        endpoint=TOKENOMICS_CONFIG["circulating_supply_url"] or None,
        enabled=TOKENOMICS_CONFIG["enable_circulating_supply"],
        raw_meta={
            "entity_registry": "token_profiles",
        },
    ),
    TokenomicsSourceDefinition(
        source_name="unlock_schedule",
        name="Unlock Schedule API",
        description="未来解锁压力与解锁事件标准化接口。",
        collector_key="unlock_schedule",
        primary_factor_id="scheduled_unlock_usd_7d",
        entity_type="asset",
        default_interval=TOKENOMICS_CONFIG["default_interval"],
        endpoint=TOKENOMICS_CONFIG["unlock_schedule_url"] or None,
        enabled=TOKENOMICS_CONFIG["enable_unlock_schedule"],
        raw_meta={
            "entity_registry": "token_profiles",
        },
    ),
    TokenomicsSourceDefinition(
        source_name="unlock_realization",
        name="Unlock Realization API",
        description="已实现解锁与短期供给释放标准化接口。",
        collector_key="unlock_realization",
        primary_factor_id="realized_unlock_usd_24h",
        entity_type="asset",
        default_interval=TOKENOMICS_CONFIG["default_interval"],
        endpoint=TOKENOMICS_CONFIG["unlock_realization_url"] or None,
        enabled=TOKENOMICS_CONFIG["enable_unlock_realization"],
        raw_meta={
            "entity_registry": "token_profiles",
        },
    ),
    TokenomicsSourceDefinition(
        source_name="treasury_wallet_flow",
        name="Treasury Wallet Flow API",
        description="基金会/国库钱包净流标准化接口。",
        collector_key="treasury_wallet_flow",
        primary_factor_id="foundation_wallet_netflow",
        entity_type="asset",
        default_interval=TOKENOMICS_CONFIG["default_interval"],
        endpoint=TOKENOMICS_CONFIG["treasury_wallet_flow_url"] or None,
        enabled=TOKENOMICS_CONFIG["enable_treasury_wallet_flow"],
        raw_meta={
            "entity_registry": "treasury_wallet_groups",
            "requires_verified_registry": True,
        },
    ),
    TokenomicsSourceDefinition(
        source_name="staking_ratio",
        name="Staking Ratio API",
        description="质押率与质押率变化标准化接口。",
        collector_key="staking_ratio",
        primary_factor_id="staking_ratio",
        entity_type="asset",
        default_interval=TOKENOMICS_CONFIG["default_interval"],
        endpoint=TOKENOMICS_CONFIG["staking_ratio_url"] or None,
        enabled=TOKENOMICS_CONFIG["enable_staking_ratio"],
        raw_meta={
            "entity_registry": "token_profiles",
        },
    ),
]


def _load_extra_entities() -> list[dict[str, object]]:
    raw_value = TOKENOMICS_CONFIG.get("extra_entities_json", "").strip()
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        logger.error(f"解析 TOKENOMICS_EXTRA_ENTITIES_JSON 失败: {exc}")
        return []
    if not isinstance(payload, list):
        logger.error("TOKENOMICS_EXTRA_ENTITIES_JSON 必须是 JSON 数组")
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]


def load_tokenomics_sources(
    source_names: list[str] | None = None,
    enabled_only: bool = True,
) -> list[TokenomicsSourceDefinition]:
    normalized_names = _normalize_filter(source_names)
    selected: list[TokenomicsSourceDefinition] = []
    for source in DEFAULT_TOKENOMICS_SOURCES:
        if enabled_only and not source.enabled:
            continue
        if normalized_names and source.source_name.lower() not in normalized_names:
            continue
        selected.append(source)
    return selected


def load_tokenomics_factors(
    factor_ids: list[str] | None = None,
    source_names: list[str] | None = None,
    enabled_only: bool = True,
) -> list[TokenomicsFactorDefinition]:
    normalized_factor_ids = _normalize_filter(factor_ids)
    normalized_source_names = _normalize_filter(source_names)
    definitions = [
        TokenomicsFactorDefinition(
            factor_id="circulating_supply",
            name="Circulating Supply",
            category="supply",
            factor_type="level",
            entity_scope="asset",
            entity_type="asset",
            description="流通盘规模。",
            default_interval="1d",
            unit="tokens",
            source_name="circulating_supply",
            source_symbol="asset",
            staleness_ttl_seconds=172800,
            enabled=TOKENOMICS_CONFIG["enable_circulating_supply"],
        ),
        TokenomicsFactorDefinition(
            factor_id="float_supply",
            name="Float Supply",
            category="supply",
            factor_type="level",
            entity_scope="asset",
            entity_type="asset",
            description="自由流通盘规模。",
            default_interval="1d",
            unit="tokens",
            source_name="circulating_supply",
            source_symbol="asset",
            staleness_ttl_seconds=172800,
            enabled=TOKENOMICS_CONFIG["enable_circulating_supply"],
        ),
        TokenomicsFactorDefinition(
            factor_id="inflation_rate_annualized",
            name="Inflation Rate Annualized",
            category="inflation",
            factor_type="rate",
            entity_scope="asset",
            entity_type="asset",
            description="年化通胀率。",
            default_interval="1d",
            unit="percent",
            source_name="circulating_supply",
            source_symbol="asset",
            staleness_ttl_seconds=172800,
            enabled=TOKENOMICS_CONFIG["enable_circulating_supply"],
        ),
        TokenomicsFactorDefinition(
            factor_id="scheduled_unlock_usd_7d",
            name="Scheduled Unlock USD 7D",
            category="unlock_pressure",
            factor_type="forward_window_sum",
            entity_scope="asset",
            entity_type="asset",
            description="未来 7 天计划解锁美元价值。",
            default_interval="1d",
            unit="usd",
            source_name="unlock_schedule",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_unlock_schedule"],
        ),
        TokenomicsFactorDefinition(
            factor_id="scheduled_unlock_pct_float_7d",
            name="Scheduled Unlock Pct Float 7D",
            category="unlock_pressure",
            factor_type="forward_window_ratio",
            entity_scope="asset",
            entity_type="asset",
            description="未来 7 天计划解锁占自由流通盘比例。",
            default_interval="1d",
            unit="percent",
            source_name="unlock_schedule",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_unlock_schedule"],
        ),
        TokenomicsFactorDefinition(
            factor_id="scheduled_unlock_usd_30d",
            name="Scheduled Unlock USD 30D",
            category="unlock_pressure",
            factor_type="forward_window_sum",
            entity_scope="asset",
            entity_type="asset",
            description="未来 30 天计划解锁美元价值。",
            default_interval="1d",
            unit="usd",
            source_name="unlock_schedule",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_unlock_schedule"],
        ),
        TokenomicsFactorDefinition(
            factor_id="realized_unlock_usd_24h",
            name="Realized Unlock USD 24H",
            category="unlock_realization",
            factor_type="rolling_sum",
            entity_scope="asset",
            entity_type="asset",
            description="最近 24 小时已实现解锁美元价值。",
            default_interval="1d",
            unit="usd",
            source_name="unlock_realization",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_unlock_realization"],
        ),
        TokenomicsFactorDefinition(
            factor_id="treasury_wallet_inflow",
            name="Treasury Wallet Inflow",
            category="treasury_flow",
            factor_type="inflow",
            entity_scope="asset",
            entity_type="asset",
            description="基金会/国库钱包流入规模。",
            default_interval="1d",
            unit="usd",
            source_name="treasury_wallet_flow",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_treasury_wallet_flow"],
        ),
        TokenomicsFactorDefinition(
            factor_id="treasury_wallet_outflow",
            name="Treasury Wallet Outflow",
            category="treasury_flow",
            factor_type="outflow",
            entity_scope="asset",
            entity_type="asset",
            description="基金会/国库钱包流出规模。",
            default_interval="1d",
            unit="usd",
            source_name="treasury_wallet_flow",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_treasury_wallet_flow"],
        ),
        TokenomicsFactorDefinition(
            factor_id="foundation_wallet_netflow",
            name="Foundation Wallet Netflow",
            category="treasury_flow",
            factor_type="netflow",
            entity_scope="asset",
            entity_type="asset",
            description="基金会/国库钱包净流。",
            default_interval="1d",
            unit="usd",
            source_name="treasury_wallet_flow",
            source_symbol="asset",
            staleness_ttl_seconds=86400,
            enabled=TOKENOMICS_CONFIG["enable_treasury_wallet_flow"],
        ),
        TokenomicsFactorDefinition(
            factor_id="staking_ratio",
            name="Staking Ratio",
            category="staking",
            factor_type="ratio",
            entity_scope="asset",
            entity_type="asset",
            description="质押率。",
            default_interval="1d",
            unit="percent",
            source_name="staking_ratio",
            source_symbol="asset",
            staleness_ttl_seconds=172800,
            enabled=TOKENOMICS_CONFIG["enable_staking_ratio"],
        ),
        TokenomicsFactorDefinition(
            factor_id="staking_ratio_change_7d",
            name="Staking Ratio Change 7D",
            category="staking",
            factor_type="change",
            entity_scope="asset",
            entity_type="asset",
            description="质押率 7 日变化。",
            default_interval="1d",
            unit="pct_points",
            source_name="staking_ratio",
            source_symbol="asset",
            staleness_ttl_seconds=172800,
            enabled=TOKENOMICS_CONFIG["enable_staking_ratio"],
        ),
    ]

    results: list[TokenomicsFactorDefinition] = []
    for definition in definitions:
        if enabled_only and not definition.enabled:
            continue
        if normalized_factor_ids and definition.factor_id.lower() not in normalized_factor_ids:
            continue
        if normalized_source_names and definition.source_name.lower() not in normalized_source_names:
            continue
        results.append(definition)
    return results


def load_tokenomics_entities(
    source_names: list[str] | None = None,
    entity_keys: list[str] | None = None,
) -> list[dict[str, str]]:
    normalized_source_names = _normalize_filter(source_names)
    normalized_entity_keys = {
        value.strip().upper()
        for value in (entity_keys or [])
        if value.strip()
    }
    configured_entity_keys = _split_csv(TOKENOMICS_CONFIG["asset_entity_keys"])
    token_profile_map = {
        str(row["entity_key"]): row
        for row in load_token_profiles(configured_entity_keys)
    }
    treasury_wallet_group_map = {
        str(row["entity_key"]): row
        for row in load_treasury_wallet_groups(configured_entity_keys)
    }

    rows: list[dict[str, object]] = []
    for entity_key in configured_entity_keys:
        token_profile = token_profile_map.get(entity_key, {})
        default_name = str(token_profile.get("name") or entity_key)
        default_description = str(
            token_profile.get("description") or f"{entity_key} tokenomics 观察对象"
        )
        for source_name in (
            "circulating_supply",
            "unlock_schedule",
            "unlock_realization",
            "treasury_wallet_flow",
            "staking_ratio",
        ):
            if normalized_source_names and source_name not in normalized_source_names:
                continue
            if normalized_entity_keys and entity_key not in normalized_entity_keys:
                continue
            row: dict[str, object] = {
                "source_name": source_name,
                "entity_type": "asset",
                "entity_key": entity_key,
                "name": default_name,
                "description": default_description,
            }
            if source_name == "treasury_wallet_flow":
                wallet_group = treasury_wallet_group_map.get(entity_key)
                if wallet_group:
                    row.update(
                        {
                            "name": str(wallet_group.get("name") or default_name),
                            "description": str(
                                wallet_group.get("description") or default_description
                            ),
                            "wallet_group_registry_present": True,
                            "wallet_group_type": wallet_group.get("wallet_group_type"),
                            "wallet_group_verification_status": wallet_group.get(
                                "verification_status"
                            ),
                            "wallet_group_address_count": wallet_group.get(
                                "address_count",
                                0,
                            ),
                            "wallet_group_source_ref_count": wallet_group.get(
                                "source_ref_count",
                                0,
                            ),
                            "wallet_group_has_real_addresses": wallet_group.get(
                                "has_real_addresses",
                                False,
                            ),
                            "wallet_group_ready_for_ai": wallet_group.get(
                                "is_ready_for_ai",
                                False,
                            ),
                            "wallet_group_quality_notes": list(
                                wallet_group.get("quality_notes") or []
                            ),
                        }
                    )
                else:
                    row.update(
                        {
                            "wallet_group_registry_present": False,
                            "wallet_group_type": "foundation_or_treasury",
                            "wallet_group_verification_status": "missing",
                            "wallet_group_address_count": 0,
                            "wallet_group_source_ref_count": 0,
                            "wallet_group_has_real_addresses": False,
                            "wallet_group_ready_for_ai": False,
                            "wallet_group_quality_notes": [
                                "wallet group registry 缺少该资产记录，当前钱包口径不可核验。"
                            ],
                        }
                    )
            rows.append(row)
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
