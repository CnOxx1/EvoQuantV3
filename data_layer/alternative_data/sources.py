import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from loguru import logger

from config.settings import ALTERNATIVE_CONFIG
from data_layer.alternative_data.models import AlternativeFactorDefinition, utc_now_naive


REGISTRY_DIR = Path(__file__).resolve().parent / "registry"
GITHUB_REPO_GROUPS_FILE = "github_repo_groups.json"
STABLECOIN_ASSETS_FILE = "stablecoin_assets.json"
GOOGLE_TRENDS_QUERY_GROUPS_FILE = "google_trends_query_groups.json"

REGISTRY_SOURCE_SPECS = {
    "google_trends": {
        "phase": "P1",
        "entity_type": "query_group",
        "filename": GOOGLE_TRENDS_QUERY_GROUPS_FILE,
        "required_fields": {"entity_key", "name", "query", "group_type"},
        "description": "Google Trends 搜索热度，当前为实验性 source。",
    },
    "github": {
        "phase": "P0",
        "entity_type": "repo_group",
        "filename": GITHUB_REPO_GROUPS_FILE,
        "required_fields": {"entity_key", "name", "asset", "repos"},
        "description": "GitHub repo group 开发者活跃度。",
    },
    "stablecoin": {
        "phase": "P0",
        "entity_type": "stablecoin_asset / stablecoin_chain",
        "filename": STABLECOIN_ASSETS_FILE,
        "required_fields": {"entity_key", "name", "aliases"},
        "description": "稳定币供给、净变化与链分布。",
    },
}

_REGISTRY_CACHE: dict[str, dict[str, object]] = {}
_REGISTRY_LOCK = RLock()


def _normalize_filter(values: list[str] | None) -> set[str]:
    return {
        value.strip().lower()
        for value in (values or [])
        if value.strip()
    }


def _registry_path(filename: str) -> Path:
    return REGISTRY_DIR / filename


def _serialize_registry_records(records: list[dict[str, object]]) -> str:
    return json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_registry_records(
    path: Path,
    required_fields: set[str],
) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError(f"registry 文件必须是 list: {path}")

    records: list[dict[str, object]] = []
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
        records.append(dict(item))
    return records


def _build_registry_snapshot(
    source_name: str,
    spec: dict[str, object],
    stat_result,
) -> dict[str, object]:
    path = _registry_path(str(spec["filename"]))
    records = _load_registry_records(
        path=path,
        required_fields=set(spec["required_fields"]),
    )
    serialized = _serialize_registry_records(records)
    modified_at = datetime.fromtimestamp(
        stat_result.st_mtime,
        tz=timezone.utc,
    ).replace(tzinfo=None)
    return {
        "source_name": source_name,
        "phase": spec["phase"],
        "entity_type": spec["entity_type"],
        "description": spec["description"],
        "registry_file": spec["filename"],
        "registry_path": str(path),
        "registry_version": hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:12],
        "registry_record_count": len(records),
        "registry_loaded_at": utc_now_naive().isoformat(),
        "registry_modified_at": modified_at.isoformat(),
        "modified_ns": stat_result.st_mtime_ns,
        "records": records,
    }


def _build_registry_meta(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "source_name": snapshot["source_name"],
        "phase": snapshot["phase"],
        "entity_type": snapshot["entity_type"],
        "description": snapshot["description"],
        "registry_file": snapshot["registry_file"],
        "registry_path": snapshot["registry_path"],
        "registry_version": snapshot["registry_version"],
        "registry_record_count": snapshot["registry_record_count"],
        "registry_loaded_at": snapshot["registry_loaded_at"],
        "registry_modified_at": snapshot["registry_modified_at"],
    }


def _ensure_registry_snapshot(
    source_name: str,
    force: bool = False,
) -> dict[str, object]:
    if source_name not in REGISTRY_SOURCE_SPECS:
        raise ValueError(f"未知补充特征 source: {source_name}")

    spec = REGISTRY_SOURCE_SPECS[source_name]
    path = _registry_path(str(spec["filename"]))

    with _REGISTRY_LOCK:
        cached = _REGISTRY_CACHE.get(source_name)
        try:
            stat_result = path.stat()
        except FileNotFoundError:
            if cached and not force and cached.get("registry_path") == str(path):
                logger.warning(
                    f"registry 文件暂不可用，继续使用旧缓存 "
                    f"[{source_name}] [{path}]"
                )
                return cached
            raise

        try:
            snapshot = _build_registry_snapshot(
                source_name=source_name,
                spec=spec,
                stat_result=stat_result,
            )
        except Exception as exc:
            if cached and not force and cached.get("registry_path") == str(path):
                logger.warning(
                    f"registry 热刷新失败，继续使用旧缓存 "
                    f"[{source_name}] [{path}]: {exc}"
                )
                return cached
            raise

        if (
            cached
            and cached.get("registry_path") == str(path)
            and cached.get("modified_ns") == snapshot["modified_ns"]
            and cached.get("registry_version") == snapshot["registry_version"]
        ):
            return cached

        _REGISTRY_CACHE[source_name] = snapshot
        return snapshot


def refresh_alternative_registries(
    source_names: list[str] | None = None,
    force: bool = False,
) -> list[dict[str, object]]:
    normalized_sources = _normalize_filter(source_names)
    results: list[dict[str, object]] = []
    for source_name in REGISTRY_SOURCE_SPECS:
        if normalized_sources and source_name not in normalized_sources:
            continue
        snapshot = _ensure_registry_snapshot(source_name, force=force)
        results.append(_build_registry_meta(snapshot))
    return results


def _load_registry_items(
    source_name: str,
    entity_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    normalized = _normalize_filter(entity_keys)
    records = _ensure_registry_snapshot(source_name).get("records", [])
    results: list[dict[str, object]] = []
    for record in records:
        if normalized and str(record["entity_key"]).lower() not in normalized:
            continue
        results.append(dict(record))
    return results


def _build_github_factors() -> list[AlternativeFactorDefinition]:
    registry_meta = _build_registry_meta(_ensure_registry_snapshot("github"))
    raw_meta = {
        "phase": "P0",
        "repo_group_version": ALTERNATIVE_CONFIG["github_repo_group_version"],
        "registry_version": registry_meta["registry_version"],
        "registry_record_count": registry_meta["registry_record_count"],
    }
    return [
        AlternativeFactorDefinition(
            factor_id="github_commit_count_1d",
            name="GitHub Commit Count 1D",
            category="developer_activity",
            factor_type="rolling_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 24 小时提交数。",
            default_interval="1d",
            unit="count",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="github_commit_count_7d",
            name="GitHub Commit Count 7D",
            category="developer_activity",
            factor_type="rolling_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 7 天提交数。",
            default_interval="1d",
            unit="count",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="github_active_contributors_7d",
            name="GitHub Active Contributors 7D",
            category="developer_activity",
            factor_type="distinct_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 7 天活跃贡献者数。",
            default_interval="1d",
            unit="contributors",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="github_opened_pr_count_7d",
            name="GitHub Opened PR Count 7D",
            category="developer_activity",
            factor_type="rolling_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 7 天新开 PR 数。",
            default_interval="1d",
            unit="count",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="github_merged_pr_count_7d",
            name="GitHub Merged PR Count 7D",
            category="developer_activity",
            factor_type="rolling_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 7 天合并 PR 数。",
            default_interval="1d",
            unit="count",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="github_release_count_30d",
            name="GitHub Release Count 30D",
            category="developer_activity",
            factor_type="rolling_count",
            entity_scope="repo_group",
            entity_type="repo_group",
            description="repo group 最近 30 天 release 数。",
            default_interval="1d",
            unit="count",
            source_name="github",
            source_symbol="repo_group",
            config_version="v1",
            staleness_ttl_seconds=172800,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
    ]


def _build_stablecoin_factors() -> list[AlternativeFactorDefinition]:
    tracked_assets = [
        asset["entity_key"]
        for asset in _load_registry_items("stablecoin")
    ]
    raw_meta = {
        "phase": "P0",
        "tracked_assets": tracked_assets,
        "registry_version": _ensure_registry_snapshot("stablecoin")["registry_version"],
        "registry_record_count": len(tracked_assets),
    }
    return [
        AlternativeFactorDefinition(
            factor_id="stablecoin_total_supply",
            name="Stablecoin Total Supply",
            category="stablecoin_liquidity",
            factor_type="stock_level",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币资产总供给。",
            default_interval="1h",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_net_supply_change_24h",
            name="Stablecoin Net Supply Change 24H",
            category="stablecoin_liquidity",
            factor_type="flow_change",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币资产过去 24 小时净供给变化。",
            default_interval="1h",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_net_supply_change_7d",
            name="Stablecoin Net Supply Change 7D",
            category="stablecoin_liquidity",
            factor_type="flow_change",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币资产过去 7 天净供给变化。",
            default_interval="1h",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_chain_supply",
            name="Stablecoin Chain Supply",
            category="stablecoin_liquidity",
            factor_type="stock_level",
            entity_scope="stablecoin_asset_chain",
            entity_type="stablecoin_chain",
            description="稳定币在具体链上的供给。",
            default_interval="1h",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_chain",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_chain_supply_share",
            name="Stablecoin Chain Supply Share",
            category="stablecoin_liquidity",
            factor_type="share_ratio",
            entity_scope="stablecoin_asset_chain",
            entity_type="stablecoin_chain",
            description="稳定币在具体链上的供给占比。",
            default_interval="1h",
            unit="ratio",
            source_name="stablecoin",
            source_symbol="stablecoin_chain",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta=dict(raw_meta),
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_mint_volume",
            name="Stablecoin Mint Volume",
            category="stablecoin_liquidity",
            factor_type="event_flow",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币资产按快照差分推断的 mint 事件量。",
            default_interval="1d",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta={
                **raw_meta,
                "eventization_mode": "snapshot_delta_inference",
            },
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_burn_volume",
            name="Stablecoin Burn Volume",
            category="stablecoin_liquidity",
            factor_type="event_flow",
            entity_scope="stablecoin_asset",
            entity_type="stablecoin_asset",
            description="稳定币资产按快照差分推断的 burn 事件量。",
            default_interval="1d",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_asset",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta={
                **raw_meta,
                "eventization_mode": "snapshot_delta_inference",
            },
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_bridge_inflow",
            name="Stablecoin Bridge Inflow",
            category="stablecoin_liquidity",
            factor_type="event_flow",
            entity_scope="stablecoin_asset_chain",
            entity_type="stablecoin_chain",
            description="稳定币链级按快照差分推断的 bridge inflow。",
            default_interval="1d",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_chain",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta={
                **raw_meta,
                "eventization_mode": "snapshot_delta_inference",
                "allocation_method": "proportional_reallocation",
            },
        ),
        AlternativeFactorDefinition(
            factor_id="stablecoin_bridge_outflow",
            name="Stablecoin Bridge Outflow",
            category="stablecoin_liquidity",
            factor_type="event_flow",
            entity_scope="stablecoin_asset_chain",
            entity_type="stablecoin_chain",
            description="稳定币链级按快照差分推断的 bridge outflow。",
            default_interval="1d",
            unit="tokens",
            source_name="stablecoin",
            source_symbol="stablecoin_chain",
            config_version="v1",
            staleness_ttl_seconds=86400,
            enabled=True,
            raw_meta={
                **raw_meta,
                "eventization_mode": "snapshot_delta_inference",
                "allocation_method": "proportional_reallocation",
            },
        ),
    ]


def _build_google_trends_factors() -> list[AlternativeFactorDefinition]:
    tracked_query_groups = [
        query_group["entity_key"]
        for query_group in _load_registry_items("google_trends")
    ]
    return [
        AlternativeFactorDefinition(
            factor_id="google_trends_search_interest",
            name="Google Trends Search Interest",
            category="search_attention",
            factor_type="search_interest",
            entity_scope="query_group",
            entity_type="query_group",
            description="Google Trends query group 的标准化搜索热度。",
            default_interval="1d",
            unit="index_points",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "bootstrap_history_days": ALTERNATIVE_CONFIG["google_trends_bootstrap_history_days"],
                "history_segment_days": ALTERNATIVE_CONFIG["google_trends_history_segment_days"],
                "history_overlap_days": ALTERNATIVE_CONFIG["google_trends_history_overlap_days"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_attention_shock_7d",
            name="Google Trends Attention Shock 7D",
            category="search_attention",
            factor_type="attention_shock",
            entity_scope="query_group",
            entity_type="query_group",
            description="当前搜索热度相对过去 7 天滚动均值的相对偏离。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "baseline_days": 7,
                "min_baseline_observations": 2,
                "shock_formula": "relative_delta_from_trailing_mean",
                "bootstrap_history_days": ALTERNATIVE_CONFIG["google_trends_bootstrap_history_days"],
                "history_segment_days": ALTERNATIVE_CONFIG["google_trends_history_segment_days"],
                "history_overlap_days": ALTERNATIVE_CONFIG["google_trends_history_overlap_days"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_related_query_breakout_count",
            name="Google Trends Related Query Breakout Count",
            category="search_attention",
            factor_type="breakout_count",
            entity_scope="query_group",
            entity_type="query_group",
            description="related queries 中 breakout 条目数量。",
            default_interval="1d",
            unit="count",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_related_query_rising_max_score",
            name="Google Trends Related Query Rising Max Score",
            category="search_attention",
            factor_type="rising_score",
            entity_scope="query_group",
            entity_type="query_group",
            description="related queries 中 rising 列表最高热度分值。",
            default_interval="1d",
            unit="score",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_related_topic_breakout_count",
            name="Google Trends Related Topic Breakout Count",
            category="search_attention",
            factor_type="breakout_count",
            entity_scope="query_group",
            entity_type="query_group",
            description="related topics 中 breakout 条目数量。",
            default_interval="1d",
            unit="count",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_related_topic_rising_max_score",
            name="Google Trends Related Topic Rising Max Score",
            category="search_attention",
            factor_type="rising_score",
            entity_scope="query_group",
            entity_type="query_group",
            description="related topics 中 rising 列表最高热度分值。",
            default_interval="1d",
            unit="score",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_cross_query_zscore",
            name="Google Trends Cross Query Z-Score",
            category="search_attention",
            factor_type="cross_sectional_zscore",
            entity_scope="query_group",
            entity_type="query_group",
            description="同批 query group 内相对搜索热度的横截面 z-score。",
            default_interval="1d",
            unit="zscore",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "cross_query_mode": "loaded_query_groups_batch",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_cross_query_percentile",
            name="Google Trends Cross Query Percentile",
            category="search_attention",
            factor_type="cross_sectional_percentile",
            entity_scope="query_group",
            entity_type="query_group",
            description="同批 query group 内相对搜索热度的横截面百分位。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "cross_query_mode": "loaded_query_groups_batch",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_narrative_concentration",
            name="Google Trends Narrative Concentration",
            category="search_attention",
            factor_type="narrative_share",
            entity_scope="query_group",
            entity_type="query_group",
            description="related query/topic 聚合后，主导叙事占总权重的比例。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "narrative_weight_mode": "log1p_value",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_narrative_speculation_share",
            name="Google Trends Narrative Speculation Share",
            category="search_attention",
            factor_type="narrative_share",
            entity_scope="query_group",
            entity_type="query_group",
            description="related query/topic 聚合后，投机/价格叙事占比。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "narrative_weight_mode": "log1p_value",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_narrative_builder_share",
            name="Google Trends Narrative Builder Share",
            category="search_attention",
            factor_type="narrative_share",
            entity_scope="query_group",
            entity_type="query_group",
            description="related query/topic 聚合后，建设/生态叙事占比。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "narrative_weight_mode": "log1p_value",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_narrative_institutional_share",
            name="Google Trends Narrative Institutional Share",
            category="search_attention",
            factor_type="narrative_share",
            entity_scope="query_group",
            entity_type="query_group",
            description="related query/topic 聚合后，机构/监管叙事占比。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "narrative_weight_mode": "log1p_value",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
        AlternativeFactorDefinition(
            factor_id="google_trends_narrative_risk_share",
            name="Google Trends Narrative Risk Share",
            category="search_attention",
            factor_type="narrative_share",
            entity_scope="query_group",
            entity_type="query_group",
            description="related query/topic 聚合后，风险/应激叙事占比。",
            default_interval="1d",
            unit="ratio",
            source_name="google_trends",
            source_symbol="query_group",
            config_version="v1",
            staleness_ttl_seconds=604800,
            enabled=True,
            raw_meta={
                "phase": "P1",
                "default_geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
                "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
                "window_days": ALTERNATIVE_CONFIG["google_trends_window_days"],
                "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
                "narrative_weight_mode": "log1p_value",
                "tracked_query_groups": tracked_query_groups,
                "registry_version": _ensure_registry_snapshot("google_trends")["registry_version"],
                "registry_record_count": len(tracked_query_groups),
            },
        ),
    ]


def _build_all_alternative_factors() -> list[AlternativeFactorDefinition]:
    return [
        *_build_github_factors(),
        *_build_stablecoin_factors(),
        *_build_google_trends_factors(),
    ]


def load_alternative_factors(
    enabled_only: bool = True,
    source_names: list[str] | None = None,
    factor_type: str | None = None,
    factor_ids: list[str] | None = None,
) -> list[AlternativeFactorDefinition]:
    """加载补充特征因子配置。"""

    normalized_sources = _normalize_filter(source_names)
    normalized_ids = _normalize_filter(factor_ids)
    results: list[AlternativeFactorDefinition] = []
    for factor in _build_all_alternative_factors():
        if enabled_only and not factor.enabled:
            continue
        if normalized_sources and factor.source_name.lower() not in normalized_sources:
            continue
        if factor_type and factor.factor_type != factor_type:
            continue
        if normalized_ids and factor.factor_id.lower() not in normalized_ids:
            continue
        results.append(factor)
    return results


def load_github_repo_groups(entity_keys: list[str] | None = None) -> list[dict[str, object]]:
    return _load_registry_items("github", entity_keys=entity_keys)


def load_stablecoin_assets(entity_keys: list[str] | None = None) -> list[dict[str, object]]:
    return _load_registry_items("stablecoin", entity_keys=entity_keys)


def load_google_trends_query_groups(
    entity_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    return _load_registry_items("google_trends", entity_keys=entity_keys)


def load_alternative_sources(
    source_names: list[str] | None = None,
    force_reload: bool = False,
) -> list[dict[str, object]]:
    normalized_sources = _normalize_filter(source_names)
    registry_meta_by_source = {
        row["source_name"]: row
        for row in refresh_alternative_registries(
            source_names=source_names,
            force=force_reload,
        )
    }
    source_rows = [
        {
            "source_name": "google_trends",
            "enabled": ALTERNATIVE_CONFIG["enable_google_trends"],
        },
        {
            "source_name": "github",
            "enabled": ALTERNATIVE_CONFIG["enable_github"],
        },
        {
            "source_name": "stablecoin",
            "enabled": ALTERNATIVE_CONFIG["enable_stablecoin"],
        },
    ]
    sources: list[dict[str, object]] = []
    for source_row in source_rows:
        source_name = str(source_row["source_name"])
        if normalized_sources and source_name.lower() not in normalized_sources:
            continue
        sources.append(
            {
                **source_row,
                **registry_meta_by_source[source_name],
            }
        )
    return sources


def load_alternative_entities(
    source_names: list[str] | None = None,
    entity_keys: list[str] | None = None,
) -> list[dict[str, object]]:
    normalized_sources = _normalize_filter(source_names)
    normalized_entity_keys = _normalize_filter(entity_keys)
    results: list[dict[str, object]] = []

    if not normalized_sources or "google_trends" in normalized_sources:
        for query_group in load_google_trends_query_groups():
            if normalized_entity_keys and str(query_group["entity_key"]).lower() not in normalized_entity_keys:
                continue
            results.append(
                {
                    "source_name": "google_trends",
                    "entity_type": "query_group",
                    "entity_key": query_group["entity_key"],
                    "name": query_group["name"],
                    "description": f"query={query_group['query']}; type={query_group['group_type']}",
                }
            )

    if not normalized_sources or "github" in normalized_sources:
        for repo_group in load_github_repo_groups():
            if normalized_entity_keys and str(repo_group["entity_key"]).lower() not in normalized_entity_keys:
                continue
            results.append(
                {
                    "source_name": "github",
                    "entity_type": "repo_group",
                    "entity_key": repo_group["entity_key"],
                    "name": repo_group["name"],
                    "description": f"repos={len(repo_group.get('repos', []))}",
                }
            )

    if not normalized_sources or "stablecoin" in normalized_sources:
        for asset in load_stablecoin_assets():
            if normalized_entity_keys and str(asset["entity_key"]).lower() not in normalized_entity_keys:
                continue
            results.append(
                {
                    "source_name": "stablecoin",
                    "entity_type": "stablecoin_asset",
                    "entity_key": asset["entity_key"],
                    "name": asset["name"],
                    "description": "tracked stablecoin asset",
                }
            )

    results.sort(
        key=lambda item: (
            str(item["source_name"]),
            str(item["entity_type"]),
            str(item["entity_key"]),
        )
    )
    return results


# 向后兼容：保留模块级快照常量，运行时调用方应优先使用 load_* 系列函数。
P0_GITHUB_REPO_GROUPS = load_github_repo_groups()
P0_STABLECOIN_ASSETS = load_stablecoin_assets()
P1_GOOGLE_TRENDS_QUERY_GROUPS = load_google_trends_query_groups()
P0_ALTERNATIVE_FACTORS = load_alternative_factors(
    enabled_only=False,
    source_names=["github", "stablecoin"],
)
P1_ALTERNATIVE_FACTORS = load_alternative_factors(
    enabled_only=False,
    source_names=["google_trends"],
)
ALL_ALTERNATIVE_FACTORS = load_alternative_factors(enabled_only=False)
