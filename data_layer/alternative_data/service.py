import json
from collections import Counter
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from loguru import logger

from config.settings import ALTERNATIVE_CONFIG
from database.db_manager import DBManager
from data_layer.alternative_data.client import AlternativeDataClient
from data_layer.alternative_data.google_trends import GoogleTrendsCollector
from data_layer.alternative_data.github_activity import GitHubActivityCollector
from data_layer.alternative_data.sources import (
    load_alternative_entities,
    load_alternative_factors,
    refresh_alternative_registries,
    load_alternative_sources,
)
from data_layer.alternative_data.stablecoin_supply import StablecoinSupplyCollector
from data_layer.data_quality import (
    is_quality_summary_ai_ready,
    resolve_source_health_status,
    summarize_health_rows,
    summarize_quality_flag_counts,
)


class AlternativeDataService:
    """补充特征模块统一编排入口。"""

    AI_EXCLUDED_SOURCE_REASON = "source_not_ready_for_ai"
    MINIMUM_MARKET_BREADTH_THRESHOLDS = {
        "query_group": 10,
        "repo_group": 6,
        "stablecoin_asset": 6,
    }

    CONTEXT_INTERVAL_PREFERENCES = {
        "stablecoin_total_supply": "1h",
        "stablecoin_net_supply_change_24h": "1h",
        "stablecoin_net_supply_change_7d": "1h",
        "stablecoin_chain_supply": "1h",
        "stablecoin_chain_supply_share": "1h",
        "stablecoin_mint_volume": "1d",
        "stablecoin_burn_volume": "1d",
        "stablecoin_bridge_inflow": "1d",
        "stablecoin_bridge_outflow": "1d",
    }
    CONTEXT_INTERVAL_RANK = {
        "1h": 3,
        "1d": 2,
        "1w": 1,
    }

    def __init__(
        self,
        client: AlternativeDataClient | None = None,
        db: DBManager | None = None,
        google_trends_collector: GoogleTrendsCollector | None = None,
        github_collector: GitHubActivityCollector | None = None,
        stablecoin_collector: StablecoinSupplyCollector | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain

            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or AlternativeDataClient()
        self.google_trends_collector = google_trends_collector or GoogleTrendsCollector(
            self.client,
            self.db,
        )
        self.github_collector = github_collector or GitHubActivityCollector(self.client, self.db)
        self.stablecoin_collector = stablecoin_collector or StablecoinSupplyCollector(
            self.client,
            self.db,
        )

    @staticmethod
    def _normalize_sources(source_names: list[str] | None) -> set[str]:
        return {
            source_name.strip().lower()
            for source_name in (source_names or [])
            if source_name.strip()
        }

    @staticmethod
    def _normalize_entity_keys(entity_keys: list[str] | None) -> list[str] | None:
        normalized = [
            entity_key.strip()
            for entity_key in (entity_keys or [])
            if entity_key.strip()
        ]
        return normalized or None

    @staticmethod
    def _requested_sources_reduce_configured_universe(
        requested_source_names: set[str] | list[str] | None,
    ) -> bool:
        normalized_requested = {
            str(source_name).strip().lower()
            for source_name in (requested_source_names or [])
            if str(source_name).strip()
        }
        if not normalized_requested:
            return False
        default_sources = {
            str(row["source_name"]).strip().lower()
            for row in load_alternative_sources()
        }
        return normalized_requested != default_sources

    @staticmethod
    def _should_run_source(
        requested_sources: set[str],
        source_name: str,
        enabled: bool,
    ) -> bool:
        if not enabled:
            return False
        if not requested_sources:
            return True
        return source_name in requested_sources

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_db_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _count_rows_by_source(rows: list[dict]) -> dict[str, int]:
        counter: Counter = Counter()
        for row in rows:
            counter[str(row["source_name"])] += 1
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
            raw_rows_by_source.setdefault(str(row["source_name"]), []).append(row)

        excluded: list[dict] = []
        for coverage_row in coverage_rows:
            source_name = str(coverage_row["source_name"])
            source_rows = raw_rows_by_source.get(source_name) or []
            if not source_rows or coverage_row.get("is_ready_for_ai"):
                continue
            excluded.append(
                {
                    "source_name": source_name,
                    "entity_type": coverage_row.get("entity_type"),
                    "phase": coverage_row.get("phase"),
                    "excluded_reason": cls.AI_EXCLUDED_SOURCE_REASON,
                    "raw_row_count": len(source_rows),
                    "raw_entity_count": len(
                        {
                            str(row["entity_key"])
                            for row in source_rows
                        }
                    ),
                    "raw_factor_ids": sorted(
                        {
                            str(row["factor_id"])
                            for row in source_rows
                        }
                    ),
                    "latest_quality_flag_breakdown": coverage_row.get(
                        "latest_quality_flag_breakdown"
                    ),
                    "latest_quality_ready_ratio": coverage_row.get(
                        "latest_quality_ready_ratio"
                    ),
                    "data_quality_flags": list(coverage_row.get("data_quality_flags") or []),
                    "quality_notes": list(coverage_row.get("quality_notes") or []),
                }
            )
        return excluded

    @staticmethod
    def _loads_json(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _count_collection_items(result) -> int:
        if result is None:
            return 0
        if isinstance(result, dict):
            return sum(
                int(value)
                for value in result.values()
                if isinstance(value, int | float)
            )
        if isinstance(result, str | bytes):
            return int(bool(result))
        return len(result)

    @staticmethod
    def _source_interval_seconds(source_name: str) -> int:
        return {
            "google_trends": ALTERNATIVE_CONFIG["google_trends_interval_seconds"],
            "github": ALTERNATIVE_CONFIG["github_interval_seconds"],
            "stablecoin": ALTERNATIVE_CONFIG["stablecoin_interval_seconds"],
        }.get(source_name, 3600)

    @staticmethod
    def _source_label(source_name: str) -> str:
        return {
            "google_trends": "Google Trends",
            "github": "GitHub",
            "stablecoin": "Stablecoin Supply",
        }.get(source_name, source_name)

    @staticmethod
    def _is_source_ready_for_ai(
        *,
        health_status: str,
        phase: str | None,
        expected_entity_count: int,
        latest_entity_count: int,
        quality_summary: dict[str, object],
    ) -> bool:
        if health_status != "ready":
            return False
        if str(phase or "").upper() == "P1":
            return False
        if expected_entity_count > 0 and latest_entity_count < expected_entity_count:
            return False
        return is_quality_summary_ai_ready(quality_summary)

    def _run_collection_job(
        self,
        *,
        source_name: str,
        job_name: str,
        func,
        metadata: dict[str, object] | None = None,
        db: DBManager | None = None,
        configuration_ready: bool = True,
        unconfigured_message: str | None = None,
    ):
        run_db = db or self.db
        started_at = self._utc_now_naive()
        status = "success"
        message = None
        item_count = 0
        result = None
        captured_exception = None

        if not configuration_ready:
            status = "unconfigured"
            message = unconfigured_message or f"补充特征来源 {source_name} 的 registry 为空"
        else:
            try:
                result = func()
                item_count = self._count_collection_items(result)
                if item_count == 0:
                    status = "empty"
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                captured_exception = exc
                logger.error(f"补充特征来源采集失败 [{source_name}]: {message}")

        finished_at = self._utc_now_naive()
        run_db.record_collection_run(
            module_name="alternative_data",
            source_name=source_name,
            job_name=job_name,
            status=status,
            item_count=item_count,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_seconds=(finished_at - started_at).total_seconds(),
            message=message,
            metadata_json=json.dumps(
                metadata or {},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        if captured_exception is not None:
            raise captured_exception
        return result

    @classmethod
    def _context_row_rank(cls, row: dict) -> tuple:
        preferred_interval = cls.CONTEXT_INTERVAL_PREFERENCES.get(row["factor_id"])
        observation_time = row.get("observation_time_dt") or datetime.min
        is_preferred_interval = (
            1
            if preferred_interval is None or row.get("interval") == preferred_interval
            else 0
        )
        interval_rank = cls.CONTEXT_INTERVAL_RANK.get(str(row.get("interval") or ""), 0)
        return (
            is_preferred_interval,
            observation_time,
            interval_rank,
        )

    @classmethod
    def _select_preferred_context_rows(
        cls,
        rows: list[dict],
    ) -> list[dict]:
        selected: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (str(row["factor_id"]), str(row["entity_key"]))
            previous = selected.get(key)
            if previous is None or cls._context_row_rank(row) >= cls._context_row_rank(previous):
                selected[key] = row
        return list(selected.values())

    @staticmethod
    def _entity_observation_time(row_map: dict[str, dict]) -> str | None:
        timestamps = [
            row.get("observation_time_dt")
            for row in row_map.values()
            if row.get("observation_time_dt") is not None
        ]
        if not timestamps:
            return None
        return max(timestamps).isoformat()

    @staticmethod
    def _entity_quality_flag(row_map: dict[str, dict], preferred_factor_ids: list[str]) -> str:
        for factor_id in preferred_factor_ids:
            row = row_map.get(factor_id)
            if row is not None:
                return str(row.get("quality_flag") or "ok")
        for row in row_map.values():
            return str(row.get("quality_flag") or "ok")
        return "ok"

    @staticmethod
    def _matches_context_entity_filter(
        entity_key: str,
        requested_entity_keys: list[str] | None,
    ) -> bool:
        if not requested_entity_keys:
            return True
        normalized_requested = {
            item.strip().lower()
            for item in requested_entity_keys
            if item.strip()
        }
        normalized_entity_key = entity_key.strip().lower()
        if normalized_entity_key in normalized_requested:
            return True
        if ":" in normalized_entity_key:
            parent_entity_key = normalized_entity_key.split(":", 1)[0]
            if parent_entity_key in normalized_requested:
                return True
        return False

    @staticmethod
    def _top_titles(entries: list[dict], limit: int = 5) -> list[str]:
        seen: set[str] = set()
        titles: list[str] = []
        for entry in entries:
            title = str(entry.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) >= limit:
                break
        return titles

    def _build_google_trends_context(
        self,
        rows: list[dict],
        entity_name_map: dict[tuple[str, str], dict[str, str]],
    ) -> dict:
        rows_by_entity: dict[str, dict[str, dict]] = {}
        for row in rows:
            rows_by_entity.setdefault(str(row["entity_key"]), {})[str(row["factor_id"])] = row

        entities: list[dict] = []
        for entity_key, row_map in rows_by_entity.items():
            meta = entity_name_map.get(("google_trends", entity_key), {})
            concentration_row = row_map.get("google_trends_narrative_concentration") or {}
            concentration_payload = concentration_row.get("raw_payload") or {}
            narrative_summary = concentration_payload.get("narrative_summary") or {}
            classified_entries = concentration_payload.get("classified_entries") or []
            entities.append(
                {
                    "entity_key": entity_key,
                    "name": meta.get("name") or entity_key,
                    "description": meta.get("description"),
                    "observation_time": self._entity_observation_time(row_map),
                    "quality_flag": self._entity_quality_flag(
                        row_map,
                        ["google_trends_search_interest"],
                    ),
                    "search_interest": (row_map.get("google_trends_search_interest") or {}).get("value"),
                    "attention_shock_7d": (row_map.get("google_trends_attention_shock_7d") or {}).get("value"),
                    "cross_query_zscore": (row_map.get("google_trends_cross_query_zscore") or {}).get("value"),
                    "cross_query_percentile": (row_map.get("google_trends_cross_query_percentile") or {}).get("value"),
                    "related_query_breakout_count": (row_map.get("google_trends_related_query_breakout_count") or {}).get("value"),
                    "related_query_rising_max_score": (row_map.get("google_trends_related_query_rising_max_score") or {}).get("value"),
                    "related_topic_breakout_count": (row_map.get("google_trends_related_topic_breakout_count") or {}).get("value"),
                    "related_topic_rising_max_score": (row_map.get("google_trends_related_topic_rising_max_score") or {}).get("value"),
                    "dominant_narrative": narrative_summary.get("dominant_narrative"),
                    "dominant_narrative_share": narrative_summary.get("dominant_share"),
                    "active_narrative_count": narrative_summary.get("active_narrative_count"),
                    "narrative_entropy": narrative_summary.get("normalized_entropy"),
                    "narrative_shares": {
                        "speculation": (row_map.get("google_trends_narrative_speculation_share") or {}).get("value"),
                        "builder": (row_map.get("google_trends_narrative_builder_share") or {}).get("value"),
                        "institutional": (row_map.get("google_trends_narrative_institutional_share") or {}).get("value"),
                        "risk": (row_map.get("google_trends_narrative_risk_share") or {}).get("value"),
                    },
                    "top_related_terms": self._top_titles(classified_entries, limit=5),
                }
            )

        entities.sort(
            key=lambda item: (
                -(float(item["cross_query_zscore"]) if item["cross_query_zscore"] is not None else -999999.0),
                -(float(item["search_interest"]) if item["search_interest"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return {
            "query_group_count": len(entities),
            "attention_leaders": entities[:5],
            "risk_watchlist": [
                entity
                for entity in sorted(
                    entities,
                    key=lambda item: (
                        -(float(item["narrative_shares"]["risk"]) if item["narrative_shares"]["risk"] is not None else -999999.0),
                        -(float(item["cross_query_zscore"]) if item["cross_query_zscore"] is not None else -999999.0),
                        item["entity_key"],
                    ),
                )
                if (entity["narrative_shares"]["risk"] or 0.0) > 0
            ][:5],
            "entities": entities,
        }

    def _build_github_context(
        self,
        rows: list[dict],
        entity_name_map: dict[tuple[str, str], dict[str, str]],
    ) -> dict:
        rows_by_entity: dict[str, dict[str, dict]] = {}
        for row in rows:
            rows_by_entity.setdefault(str(row["entity_key"]), {})[str(row["factor_id"])] = row

        entities: list[dict] = []
        for entity_key, row_map in rows_by_entity.items():
            meta = entity_name_map.get(("github", entity_key), {})
            entities.append(
                {
                    "entity_key": entity_key,
                    "name": meta.get("name") or entity_key,
                    "description": meta.get("description"),
                    "observation_time": self._entity_observation_time(row_map),
                    "quality_flag": self._entity_quality_flag(
                        row_map,
                        ["github_commit_count_7d", "github_commit_count_1d"],
                    ),
                    "commit_count_1d": (row_map.get("github_commit_count_1d") or {}).get("value"),
                    "commit_count_7d": (row_map.get("github_commit_count_7d") or {}).get("value"),
                    "active_contributors_7d": (row_map.get("github_active_contributors_7d") or {}).get("value"),
                    "opened_pr_count_7d": (row_map.get("github_opened_pr_count_7d") or {}).get("value"),
                    "merged_pr_count_7d": (row_map.get("github_merged_pr_count_7d") or {}).get("value"),
                    "release_count_30d": (row_map.get("github_release_count_30d") or {}).get("value"),
                }
            )

        entities.sort(
            key=lambda item: (
                -(float(item["commit_count_7d"]) if item["commit_count_7d"] is not None else -999999.0),
                -(float(item["active_contributors_7d"]) if item["active_contributors_7d"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        return {
            "repo_group_count": len(entities),
            "leaders_by_commit_7d": entities[:5],
            "entities": entities,
        }

    def _build_stablecoin_context(
        self,
        rows: list[dict],
        entity_name_map: dict[tuple[str, str], dict[str, str]],
    ) -> dict:
        rows_by_entity: dict[str, dict[str, dict]] = {}
        for row in rows:
            rows_by_entity.setdefault(str(row["entity_key"]), {})[str(row["factor_id"])] = row

        asset_keys = sorted(
            entity_key
            for entity_key, row_map in rows_by_entity.items()
            if "stablecoin_total_supply" in row_map
        )
        assets: list[dict] = []
        bridge_hotspots: list[dict] = []
        total_supply_tracked = 0.0
        total_mint_volume = 0.0
        total_burn_volume = 0.0

        for asset_key in asset_keys:
            row_map = rows_by_entity.get(asset_key, {})
            meta = entity_name_map.get(("stablecoin", asset_key), {})
            total_supply = float((row_map.get("stablecoin_total_supply") or {}).get("value") or 0.0)
            mint_volume = float((row_map.get("stablecoin_mint_volume") or {}).get("value") or 0.0)
            burn_volume = float((row_map.get("stablecoin_burn_volume") or {}).get("value") or 0.0)
            total_supply_tracked += total_supply
            total_mint_volume += mint_volume
            total_burn_volume += burn_volume

            chains: list[dict] = []
            chain_prefix = f"{asset_key}:"
            for entity_key, chain_row_map in rows_by_entity.items():
                if not entity_key.startswith(chain_prefix):
                    continue
                supply_row = chain_row_map.get("stablecoin_chain_supply") or {}
                supply_payload = supply_row.get("raw_payload") or {}
                chain_name = (
                    supply_payload.get("chain")
                    or str((supply_row.get("dimensions_json") or {}).get("chain") or entity_key.split(":", 1)[-1])
                )
                chain_item = {
                    "entity_key": entity_key,
                    "chain": str(chain_name),
                    "supply": supply_row.get("value"),
                    "supply_share": (chain_row_map.get("stablecoin_chain_supply_share") or {}).get("value"),
                    "bridge_inflow": (chain_row_map.get("stablecoin_bridge_inflow") or {}).get("value"),
                    "bridge_outflow": (chain_row_map.get("stablecoin_bridge_outflow") or {}).get("value"),
                    "bridge_netflow": (
                        float((chain_row_map.get("stablecoin_bridge_inflow") or {}).get("value") or 0.0)
                        - float((chain_row_map.get("stablecoin_bridge_outflow") or {}).get("value") or 0.0)
                    ),
                    "observation_time": self._entity_observation_time(chain_row_map),
                }
                chains.append(chain_item)
                bridge_hotspots.append(
                    {
                        "asset": asset_key,
                        "asset_name": meta.get("name") or asset_key,
                        **chain_item,
                    }
                )

            chains.sort(
                key=lambda item: (
                    -(float(item["supply"]) if item["supply"] is not None else -999999.0),
                    item["entity_key"],
                )
            )
            assets.append(
                {
                    "entity_key": asset_key,
                    "name": meta.get("name") or asset_key,
                    "description": meta.get("description"),
                    "observation_time": self._entity_observation_time(row_map),
                    "quality_flag": self._entity_quality_flag(
                        row_map,
                        ["stablecoin_total_supply"],
                    ),
                    "total_supply": row_map.get("stablecoin_total_supply", {}).get("value"),
                    "net_supply_change_24h": row_map.get("stablecoin_net_supply_change_24h", {}).get("value"),
                    "net_supply_change_7d": row_map.get("stablecoin_net_supply_change_7d", {}).get("value"),
                    "mint_volume_1d": mint_volume,
                    "burn_volume_1d": burn_volume,
                    "net_mint_minus_burn_1d": mint_volume - burn_volume,
                    "chains": chains,
                    "dominant_chain": chains[0]["chain"] if chains else None,
                }
            )

        assets.sort(
            key=lambda item: (
                -(float(item["total_supply"]) if item["total_supply"] is not None else -999999.0),
                item["entity_key"],
            )
        )
        bridge_hotspots.sort(
            key=lambda item: (
                -max(
                    abs(float(item["bridge_netflow"] or 0.0)),
                    float(item["bridge_inflow"] or 0.0),
                    float(item["bridge_outflow"] or 0.0),
                ),
                item["entity_key"],
            )
        )
        return {
            "asset_count": len(assets),
            "summary": {
                "tracked_total_supply": total_supply_tracked,
                "total_mint_volume_1d": total_mint_volume,
                "total_burn_volume_1d": total_burn_volume,
                "net_mint_minus_burn_1d": total_mint_volume - total_burn_volume,
            },
            "bridge_hotspots": bridge_hotspots[:5],
            "assets": assets,
        }

    @staticmethod
    def _missing_entity_count(
        items: list[dict],
        required_fields: tuple[str, ...],
    ) -> int:
        return sum(
            1
            for item in items
            if any(item.get(field_name) is None for field_name in required_fields)
        )

    def _build_context_quality(
        self,
        *,
        preferred_rows: list[dict],
        raw_row_count: int,
        ai_excluded_source_count: int,
        requested_sources: set[str],
        requested_entity_keys: list[str] | None,
        coverage_rows: list[dict],
        bundle_sources: dict[str, dict],
        configured_universe_summary: dict[str, object] | None = None,
    ) -> tuple[list[str], list[str]]:
        flags: list[str] = []
        notes: list[str] = []

        if not preferred_rows:
            flags.append("alternative_context_empty")
            if raw_row_count > 0 and ai_excluded_source_count > 0:
                notes.append(
                    "当前 alternative 虽然已有真实已落库快照，但它们全部来自尚未达到 AI-ready 门槛的 source，"
                    "当前没有任何可直接给 AI 使用的补充特征。"
                )
            else:
                notes.append("当前 alternative bundle 没有任何最新快照，AI 不能把补充特征视为已覆盖。")
            return flags, notes

        quality_summary = summarize_quality_flag_counts(preferred_rows)
        if quality_summary["partial_count"]:
            flags.append("alternative_partial_present")
            notes.append("latest alternative 快照里存在 partial 样本，说明部分补充特征仍是临时值或未完全收敛。")
        if quality_summary["fallback_count"]:
            flags.append("alternative_fallback_present")
            notes.append("latest alternative 快照里存在 fallback 样本，说明部分补充特征来自降级路径或近似值。")
        if quality_summary["stale_count"]:
            flags.append("alternative_stale_present")
            notes.append("latest alternative 快照里存在 stale 样本，不应把这些字段视为当前最新状态。")
        if quality_summary["unknown_count"]:
            flags.append("alternative_unknown_quality_flag_present")
            notes.append("latest alternative 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")

        non_ready_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if row.get("health_status") != "ready"
        ]
        if non_ready_sources:
            flags.append("alternative_source_not_ready_present")
            notes.append(
                "当前仍有未 ready 的 alternative source: "
                f"{', '.join(non_ready_sources)}。"
            )
        not_ready_for_ai_sources = [
            str(row["source_name"])
            for row in coverage_rows
            if not row.get("is_ready_for_ai")
        ]
        if not_ready_for_ai_sources:
            flags.append("alternative_source_not_ready_for_ai_present")
            notes.append(
                "当前仍有 alternative source 虽然最近任务成功，但 latest 快照还不适合直接作为 AI 的补充证据: "
                f"{', '.join(not_ready_for_ai_sources)}。"
            )

        if (
            configured_universe_summary
            and configured_universe_summary.get("scope_kind") == "default"
            and configured_universe_summary.get("breadth_status") == "limited"
        ):
            flags.append("alternative_configured_market_breadth_limited")
            entity_type_counts = configured_universe_summary.get("entity_type_counts") or {}
            minimum_counts = (
                configured_universe_summary.get(
                    "minimum_entity_type_counts_for_market_breadth"
                )
                or {}
            )
            narrow_segments = []
            for entity_type, minimum_count in minimum_counts.items():
                current_count = int(entity_type_counts.get(entity_type) or 0)
                if current_count < int(minimum_count):
                    narrow_segments.append(
                        f"{entity_type}={current_count}/{int(minimum_count)}"
                    )
            notes.append(
                "当前 alternative 默认配置宇宙仍偏向核心关注对象，"
                "尚未达到更广市场 breadth 视角的建议门槛: "
                f"{', '.join(narrow_segments) if narrow_segments else 'breadth 不足'}。"
            )

        for row in coverage_rows:
            source_name = str(row["source_name"])
            expected_entity_count = int(row.get("expected_entity_count") or 0)
            latest_entity_count = int(row.get("latest_entity_count") or 0)
            if expected_entity_count and latest_entity_count < expected_entity_count:
                flags.append(f"{source_name}_entity_coverage_incomplete")
                notes.append(
                    f"{source_name} 当前只覆盖了 {latest_entity_count}/{expected_entity_count} 个注册实体，AI 看到的该类补充特征仍不完整。"
                )
            if str(row.get("phase") or "").upper() == "P1":
                flags.append(f"{source_name}_experimental_source")
                notes.append(
                    f"{source_name} 当前仍处于 P1/experimental 阶段，建议 AI 把它视为补充证据而不是唯一依据。"
                )

        requested_or_default_sources = requested_sources or {"google_trends", "github", "stablecoin"}
        if "google_trends" in requested_or_default_sources:
            google_context = bundle_sources.get("google_trends") or {}
            google_entities = google_context.get("entities") or []
            if not google_entities:
                flags.append("google_trends_context_missing")
                notes.append("当前 bundle 缺少 Google Trends section，AI 看不到搜索热度与叙事拥挤度证据。")
            else:
                missing_google = self._missing_entity_count(
                    google_entities,
                    ("search_interest", "attention_shock_7d", "cross_query_zscore"),
                )
                if missing_google:
                    flags.append(f"google_trends_signal_missing_for_{missing_google}_entities")
                    notes.append("部分 query group 缺少 search / shock / cross-query 特征，AI 对注意力变化的判断会变弱。")

        if "github" in requested_or_default_sources:
            github_context = bundle_sources.get("github") or {}
            github_entities = github_context.get("entities") or []
            if not github_entities:
                flags.append("github_context_missing")
                notes.append("当前 bundle 缺少 GitHub section，AI 看不到开发活跃度证据。")
            else:
                missing_github = self._missing_entity_count(
                    github_entities,
                    ("commit_count_7d", "active_contributors_7d"),
                )
                if missing_github:
                    flags.append(f"github_activity_missing_for_{missing_github}_entities")
                    notes.append("部分 repo group 缺少 commit 或 contributor 特征，AI 无法完整判断开发活跃度是否真实提升。")

        if "stablecoin" in requested_or_default_sources:
            stablecoin_context = bundle_sources.get("stablecoin") or {}
            stablecoin_assets = stablecoin_context.get("assets") or []
            if not stablecoin_assets:
                flags.append("stablecoin_context_missing")
                notes.append("当前 bundle 缺少 stablecoin section，AI 看不到稳定币库存与链间迁移证据。")
            else:
                missing_stablecoin_supply = self._missing_entity_count(
                    stablecoin_assets,
                    ("total_supply", "net_supply_change_24h"),
                )
                if missing_stablecoin_supply:
                    flags.append(
                        f"stablecoin_supply_signal_missing_for_{missing_stablecoin_supply}_entities"
                    )
                    notes.append("部分稳定币资产缺少 total supply 或 24h 供给变化，AI 无法判断链上美元弹药是否扩张。")
                missing_stablecoin_chain = sum(
                    1
                    for asset in stablecoin_assets
                    if not asset.get("chains")
                )
                if missing_stablecoin_chain:
                    flags.append(
                        f"stablecoin_chain_distribution_missing_for_{missing_stablecoin_chain}_entities"
                    )
                    notes.append("部分稳定币资产缺少链分布，AI 无法判断资金是否正在向特定生态迁移。")

        if not requested_entity_keys and len(preferred_rows) <= 6:
            flags.append("alternative_context_narrow")
            notes.append("当前 alternative bundle 覆盖实体较少，横向比较能力有限。")
        return flags, notes

    @classmethod
    def _build_configured_universe_summary(
        cls,
        *,
        entity_rows: list[dict],
        requested_entity_keys: list[str] | None = None,
        requested_factor_ids: list[str] | None = None,
        requested_source_names: set[str] | list[str] | None = None,
    ) -> dict[str, object]:
        entity_type_counts: dict[str, int] = {}
        entity_keys_by_type: dict[str, list[str]] = {}
        for row in entity_rows:
            entity_type = str(row.get("entity_type") or "unknown")
            entity_key = str(row.get("entity_key") or "")
            entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1
            entity_keys_by_type.setdefault(entity_type, []).append(entity_key)
        entity_keys_by_type = {
            entity_type: sorted(keys)
            for entity_type, keys in entity_keys_by_type.items()
        }
        source_names_reduce_universe = cls._requested_sources_reduce_configured_universe(
            requested_source_names
        )
        scope_kind = (
            "filtered"
            if requested_entity_keys or requested_factor_ids or source_names_reduce_universe
            else "default"
        )
        breadth_status = "filtered"
        if scope_kind == "default":
            breadth_status = "sufficient"
            for entity_type, minimum_count in cls.MINIMUM_MARKET_BREADTH_THRESHOLDS.items():
                if int(entity_type_counts.get(entity_type) or 0) < int(minimum_count):
                    breadth_status = "limited"
                    break
        return {
            "scope_kind": scope_kind,
            "entity_type_counts": entity_type_counts,
            "entity_keys_by_type": entity_keys_by_type,
            "minimum_entity_type_counts_for_market_breadth": dict(
                cls.MINIMUM_MARKET_BREADTH_THRESHOLDS
            ),
            "breadth_status": breadth_status,
            "is_market_breadth_sufficient": (
                None if scope_kind == "filtered" else breadth_status == "sufficient"
            ),
        }

    @staticmethod
    def _summarize_entity_type_coverage(
        coverage_rows: list[dict],
    ) -> list[dict]:
        rows_by_entity_type: dict[str, dict[str, int]] = {}
        for row in coverage_rows:
            entity_type = str(row.get("entity_type") or "unknown")
            summary = rows_by_entity_type.setdefault(
                entity_type,
                {
                    "expected_entity_count": 0,
                    "observed_entity_count": 0,
                    "source_count": 0,
                    "ready_source_count": 0,
                    "problem_source_count": 0,
                },
            )
            summary["expected_entity_count"] += int(row.get("expected_entity_count") or 0)
            summary["observed_entity_count"] += int(row.get("latest_entity_count") or 0)
            summary["source_count"] += 1
            if row.get("health_status") == "ready":
                summary["ready_source_count"] += 1
            else:
                summary["problem_source_count"] += 1
        return [
            {
                "entity_type": entity_type,
                **summary,
            }
            for entity_type, summary in sorted(rows_by_entity_type.items())
        ]

    def init_storage(self):
        self.db.init_market_data_tables()
        self.sync_factor_catalog()

    def describe_registry(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
        force_reload: bool = False,
    ) -> dict[str, list[dict]]:
        normalized_sources = self._normalize_sources(source_names)
        normalized_source_list = sorted(normalized_sources) or None
        normalized_entity_keys = self._normalize_entity_keys(entity_keys)
        if force_reload:
            self.refresh_registry(
                source_names=normalized_source_list,
                force=True,
            )
        factors = load_alternative_factors(
            enabled_only=False,
            source_names=normalized_source_list,
        )
        return {
            "sources": load_alternative_sources(
                source_names=normalized_source_list,
                force_reload=force_reload,
            ),
            "factors": [
                {
                    "factor_id": factor.factor_id,
                    "name": factor.name,
                    "source_name": factor.source_name,
                    "entity_type": factor.entity_type,
                    "default_interval": factor.default_interval,
                    "enabled": factor.enabled,
                    "phase": factor.raw_meta.get("phase"),
                }
                for factor in factors
            ],
            "entities": load_alternative_entities(
                source_names=normalized_source_list,
                entity_keys=normalized_entity_keys,
            ),
        }

    def refresh_registry(
        self,
        source_names: list[str] | None = None,
        force: bool = False,
    ) -> list[dict]:
        normalized_sources = self._normalize_sources(source_names)
        normalized_source_list = sorted(normalized_sources) or None
        return refresh_alternative_registries(
            source_names=normalized_source_list,
            force=force,
        )

    def sync_factor_catalog(self):
        factors = load_alternative_factors(enabled_only=False)
        if not factors:
            return

        sql = """
            INSERT INTO alternative_factor_catalog (
                factor_id, name, category, factor_type, entity_scope, entity_type,
                description, default_interval, unit, source_name, source_symbol,
                source_priority, config_version, staleness_ttl_seconds, enabled,
                raw_meta_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                factor_type=excluded.factor_type,
                entity_scope=excluded.entity_scope,
                entity_type=excluded.entity_type,
                description=excluded.description,
                default_interval=excluded.default_interval,
                unit=excluded.unit,
                source_name=excluded.source_name,
                source_symbol=excluded.source_symbol,
                source_priority=excluded.source_priority,
                config_version=excluded.config_version,
                staleness_ttl_seconds=excluded.staleness_ttl_seconds,
                enabled=excluded.enabled,
                raw_meta_json=excluded.raw_meta_json,
                updated_at=excluded.updated_at
        """
        self.db.execute_many(sql, [factor.to_catalog_tuple() for factor in factors])
        self.db.commit()

    def _bootstrap_source(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
    ) -> list:
        if source_name == "google_trends":
            points = self.google_trends_collector.bootstrap_history(entity_keys=entity_keys)
            if points:
                self.google_trends_collector.save_to_db(points)
            return points
        if source_name == "github":
            points = self.github_collector.bootstrap_history(entity_keys=entity_keys)
            if points:
                self.github_collector.save_to_db(points)
            return points
        if source_name == "stablecoin":
            points = self.stablecoin_collector.bootstrap_history(entity_keys=entity_keys)
            if points:
                self.stablecoin_collector.save_to_db(points)
            return points
        raise ValueError(f"未知补充特征 source: {source_name}")

    def _collect_source(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
    ) -> list:
        if source_name == "google_trends":
            return self.google_trends_collector.collect(entity_keys=entity_keys)
        if source_name == "github":
            return self.github_collector.collect(entity_keys=entity_keys)
        if source_name == "stablecoin":
            return self.stablecoin_collector.collect(entity_keys=entity_keys)
        raise ValueError(f"未知补充特征 source: {source_name}")

    def bootstrap(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        self.sync_factor_catalog()
        requested_sources = self._normalize_sources(source_names)
        entity_keys = self._normalize_entity_keys(entity_keys)
        source_registry_map = {
            row["source_name"]: row
            for row in load_alternative_sources(
                source_names=sorted(requested_sources) or None
            )
        }
        summary = {
            "google_trends_points": 0,
            "github_points": 0,
            "stablecoin_points": 0,
        }
        source_specs = (
            ("google_trends", "google_trends_points", ALTERNATIVE_CONFIG["enable_google_trends"]),
            ("github", "github_points", ALTERNATIVE_CONFIG["enable_github"]),
            ("stablecoin", "stablecoin_points", ALTERNATIVE_CONFIG["enable_stablecoin"]),
        )
        for source_name, summary_key, enabled in source_specs:
            if not self._should_run_source(requested_sources, source_name, enabled):
                continue
            source_meta = source_registry_map.get(source_name, {})
            points = self._run_collection_job(
                source_name=source_name,
                job_name="alternative_bootstrap",
                func=lambda source_name=source_name: self._bootstrap_source(
                    source_name,
                    entity_keys=entity_keys,
                ),
                metadata={
                    "mode": "bootstrap",
                    "entity_keys": entity_keys,
                    "registry_version": source_meta.get("registry_version"),
                },
                configuration_ready=int(source_meta.get("registry_record_count") or 0) > 0,
                unconfigured_message=(
                    f"补充特征来源 {source_name} 的 registry 为空，无法执行 bootstrap"
                ),
            ) or []
            summary[summary_key] = len(points)
        return summary

    def collect_once(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        self.sync_factor_catalog()
        requested_sources = self._normalize_sources(source_names)
        entity_keys = self._normalize_entity_keys(entity_keys)
        source_registry_map = {
            row["source_name"]: row
            for row in load_alternative_sources(
                source_names=sorted(requested_sources) or None
            )
        }
        summary = {
            "google_trends_points": 0,
            "github_points": 0,
            "stablecoin_points": 0,
        }
        source_specs = (
            ("google_trends", "google_trends_points", ALTERNATIVE_CONFIG["enable_google_trends"]),
            ("github", "github_points", ALTERNATIVE_CONFIG["enable_github"]),
            ("stablecoin", "stablecoin_points", ALTERNATIVE_CONFIG["enable_stablecoin"]),
        )
        for source_name, summary_key, enabled in source_specs:
            if not self._should_run_source(requested_sources, source_name, enabled):
                continue
            source_meta = source_registry_map.get(source_name, {})
            points = self._run_collection_job(
                source_name=source_name,
                job_name="alternative_timeseries",
                func=lambda source_name=source_name: self._collect_source(
                    source_name,
                    entity_keys=entity_keys,
                ),
                metadata={
                    "mode": "once",
                    "entity_keys": entity_keys,
                    "registry_version": source_meta.get("registry_version"),
                },
                configuration_ready=int(source_meta.get("registry_record_count") or 0) > 0,
                unconfigured_message=(
                    f"补充特征来源 {source_name} 的 registry 为空，无法执行采集"
                ),
            ) or []
            summary[summary_key] = len(points)
        return summary

    def load_source_coverage(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> dict:
        sources = load_alternative_sources(source_names=source_names)
        now = self._utc_now_naive()
        if not sources:
            return {
                "generated_at": now.isoformat(),
                "source_count": 0,
                "sources": [],
            }

        requested_entity_keys = self._normalize_entity_keys(entity_keys)
        source_name_list = [str(source["source_name"]) for source in sources]
        placeholders = ",".join("?" for _ in source_name_list)

        latest_rows = self.db.fetch_all(
            f"""
            SELECT source_name, factor_id, entity_key, interval, observation_time, quality_flag
            FROM latest_alternative_timeseries
            WHERE source_name IN ({placeholders})
            ORDER BY source_name, observation_time DESC, factor_id, entity_key
            """,
            tuple(source_name_list),
        )
        latest_rows_by_source: dict[str, list[dict]] = {}
        for row in latest_rows:
            row_dict = dict(row)
            if not self._matches_context_entity_filter(
                str(row_dict["entity_key"]),
                requested_entity_keys,
            ):
                continue
            latest_rows_by_source.setdefault(str(row_dict["source_name"]), []).append(row_dict)

        run_rows = self.db.fetch_all(
            f"""
            SELECT runs.*
            FROM collection_runs AS runs
            INNER JOIN (
                SELECT source_name, MAX(id) AS latest_id
                FROM collection_runs
                WHERE module_name = 'alternative_data'
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

        entity_registry_rows = load_alternative_entities(
            source_names=source_names,
            entity_keys=requested_entity_keys,
        )
        expected_entity_map: dict[str, set[str]] = {}
        for row in entity_registry_rows:
            expected_entity_map.setdefault(str(row["source_name"]), set()).add(
                str(row["entity_key"])
            )

        rows: list[dict] = []
        for source in sources:
            source_name = str(source["source_name"])
            filtered_latest_rows = latest_rows_by_source.get(source_name, [])
            latest_entity_keys = {
                str(row["entity_key"])
                for row in filtered_latest_rows
            }
            latest_factor_ids = {
                str(row["factor_id"])
                for row in filtered_latest_rows
            }
            quality_summary = summarize_quality_flag_counts(filtered_latest_rows)
            latest_observation_dt = max(
                (
                    self._parse_db_timestamp(str(row["observation_time"]))
                    for row in filtered_latest_rows
                    if row.get("observation_time")
                ),
                default=None,
            )
            run_meta = run_map.get(source_name, {})
            last_run_finished_at = run_meta.get("finished_at")
            last_run_dt = (
                self._parse_db_timestamp(str(last_run_finished_at))
                if last_run_finished_at
                else None
            )
            staleness_anchor = last_run_dt or latest_observation_dt
            is_stale = staleness_anchor is None or (
                now - staleness_anchor
            ).total_seconds() > self._source_interval_seconds(source_name) * 3
            configuration_ready = int(source.get("registry_record_count") or 0) > 0
            health_status = resolve_source_health_status(
                enabled=bool(source.get("enabled")),
                configuration_ready=configuration_ready,
                last_run_status=run_meta.get("status"),
                latest_point_count=len(filtered_latest_rows),
                is_stale=is_stale,
            )
            quality_notes: list[str] = []
            quality_flags: list[str] = []
            if str(source.get("phase") or "").upper() == "P1":
                quality_flags.append("experimental_source")
                quality_notes.append(
                    "当前 source 仍处于 P1/experimental 阶段，建议与其他数据源交叉验证。"
                )
            expected_entity_count = len(expected_entity_map.get(source_name, set()))
            latest_entity_count = len(latest_entity_keys)
            if expected_entity_count and latest_entity_count < expected_entity_count:
                quality_flags.append("entity_coverage_incomplete")
                quality_notes.append(
                    f"当前 source 只覆盖了 {latest_entity_count}/{expected_entity_count} 个注册实体，AI 看到的补充特征仍不完整。"
                )
            is_ready_for_ai = self._is_source_ready_for_ai(
                health_status=health_status,
                phase=source.get("phase"),
                expected_entity_count=expected_entity_count,
                latest_entity_count=latest_entity_count,
                quality_summary=quality_summary,
            )
            if health_status == "ready" and not is_ready_for_ai:
                quality_notes.append(
                    "当前 source 虽然最近运行成功，但 latest 快照仍未达到可直接给 AI 使用的质量门槛。"
                )
            if quality_summary["partial_count"]:
                quality_flags.append("partial_points_present")
                quality_notes.append("latest 快照里存在 partial 样本，说明部分补充特征仍是临时值或未完全收敛。")
            if quality_summary["fallback_count"]:
                quality_flags.append("fallback_points_present")
                quality_notes.append("latest 快照里存在 fallback 样本，说明部分补充特征来自降级路径或近似值。")
            if quality_summary["stale_count"]:
                quality_flags.append("stale_points_present")
                quality_notes.append("latest 快照里存在 stale 样本，即使最近任务成功也不应视为当前最新状态。")
            if quality_summary["unknown_count"]:
                quality_flags.append("unknown_quality_flag_present")
                quality_notes.append("latest 快照里存在未知 quality_flag，说明质量标签还未完全标准化。")
            rows.append(
                {
                    "source_name": source_name,
                    "name": self._source_label(source_name),
                    "enabled": bool(source.get("enabled")),
                    "phase": source.get("phase"),
                    "description": source.get("description"),
                    "entity_type": source.get("entity_type"),
                    "registry_file": source.get("registry_file"),
                    "registry_path": source.get("registry_path"),
                    "registry_version": source.get("registry_version"),
                    "registry_record_count": int(source.get("registry_record_count") or 0),
                    "registry_loaded_at": source.get("registry_loaded_at"),
                    "registry_modified_at": source.get("registry_modified_at"),
                    "configuration_ready": configuration_ready,
                    "expected_entity_count": expected_entity_count,
                    "latest_entity_count": latest_entity_count,
                    "latest_factor_count": len(latest_factor_ids),
                    "latest_point_count": len(filtered_latest_rows),
                    "latest_observation_time": (
                        latest_observation_dt.isoformat()
                        if latest_observation_dt is not None
                        else None
                    ),
                    "last_run_status": run_meta.get("status"),
                    "last_run_item_count": int(run_meta.get("item_count") or 0),
                    "last_run_finished_at": last_run_finished_at,
                    "last_run_message": run_meta.get("message"),
                    "last_run_metadata": self._loads_json(run_meta.get("metadata_json")),
                    "is_stale": is_stale,
                    "health_status": health_status,
                    "is_ready_for_ai": is_ready_for_ai,
                    "latest_quality_flag_breakdown": quality_summary["breakdown"],
                    "latest_ok_point_count": quality_summary["ok_count"],
                    "latest_partial_point_count": quality_summary["partial_count"],
                    "latest_fallback_point_count": quality_summary["fallback_count"],
                    "latest_stale_point_count": quality_summary["stale_count"],
                    "latest_unknown_quality_point_count": quality_summary["unknown_count"],
                    "latest_non_ok_point_count": quality_summary["non_ok_count"],
                    "latest_quality_ready_ratio": quality_summary["ready_ratio"],
                    "data_quality_flags": quality_flags,
                    "quality_notes": quality_notes,
                }
            )

        rows.sort(
            key=lambda item: (
                item["health_status"] != "ready",
                item["is_stale"],
                item["source_name"],
            )
        )
        health_summary = summarize_health_rows(rows)
        ready_for_ai_source_count = sum(1 for item in rows if item["is_ready_for_ai"])
        return {
            "generated_at": now.isoformat(),
            "source_count": len(rows),
            "stale_source_count": sum(1 for item in rows if item["is_stale"]),
            "total_latest_entity_count": sum(item["latest_entity_count"] for item in rows),
            "total_latest_point_count": sum(item["latest_point_count"] for item in rows),
            "ready_for_ai_source_count": ready_for_ai_source_count,
            "not_ready_for_ai_source_count": len(rows) - ready_for_ai_source_count,
            **health_summary,
            "sources": rows,
        }

    def load_latest_context(
        self,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
        source_names: list[str] | None = None,
    ) -> list[dict]:
        sql = """
            SELECT factor_id, category, factor_type, entity_type, entity_key,
                   interval, observation_time, value, unit, quality_flag,
                   dimensions_key, dimensions_json, config_version, source_name,
                   source_symbol, raw_payload_json, collected_at, updated_at
            FROM latest_alternative_timeseries
        """
        clauses: list[str] = []
        params: list[str] = []
        if factor_ids:
            placeholders = ",".join("?" for _ in factor_ids)
            clauses.append(f"factor_id IN ({placeholders})")
            params.extend(factor_ids)
        if entity_keys:
            placeholders = ",".join("?" for _ in entity_keys)
            clauses.append(f"entity_key IN ({placeholders})")
            params.extend(entity_keys)
        if source_names:
            placeholders = ",".join("?" for _ in source_names)
            clauses.append(f"source_name IN ({placeholders})")
            params.extend(source_names)
        if clauses:
            sql = f"{sql} WHERE {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY source_name, factor_id, entity_key, interval"
        rows = self.db.fetch_all(sql, tuple(params))
        return [dict(row) for row in rows]

    def load_latest_context_bundle(
        self,
        factor_ids: list[str] | None = None,
        entity_keys: list[str] | None = None,
        source_names: list[str] | None = None,
    ) -> dict:
        raw_rows = self.load_latest_context(
            factor_ids=factor_ids,
            source_names=source_names,
        )
        parsed_rows: list[dict] = []
        for row in raw_rows:
            if not self._matches_context_entity_filter(
                str(row["entity_key"]),
                entity_keys,
            ):
                continue
            parsed_rows.append(
                {
                    **row,
                    "observation_time_dt": self._parse_db_timestamp(row.get("observation_time")),
                    "collected_at_dt": self._parse_db_timestamp(row.get("collected_at")),
                    "dimensions_json": self._loads_json(row.get("dimensions_json")) or {},
                    "raw_payload": self._loads_json(row.get("raw_payload_json")) or {},
                }
            )

        raw_preferred_rows = self._select_preferred_context_rows(parsed_rows)
        entity_meta_rows = load_alternative_entities(
            source_names=source_names,
            entity_keys=entity_keys,
        )
        requested_sources = self._normalize_sources(source_names)
        configured_universe_summary = self._build_configured_universe_summary(
            entity_rows=entity_meta_rows,
            requested_entity_keys=self._normalize_entity_keys(entity_keys),
            requested_factor_ids=factor_ids,
            requested_source_names=requested_sources,
        )
        entity_name_map = {
            (str(row["source_name"]), str(row["entity_key"])): {
                "name": str(row["name"]),
                "description": str(row.get("description") or ""),
            }
            for row in entity_meta_rows
        }
        coverage = self.load_source_coverage(
            source_names=source_names,
            entity_keys=entity_keys,
        )
        coverage_rows = coverage.get("sources", [])
        ai_ready_source_names = self._ai_ready_source_names(coverage_rows)
        ai_excluded_sources = self._build_ai_excluded_sources(
            raw_rows=raw_preferred_rows,
            coverage_rows=coverage_rows,
        )
        preferred_rows = [
            row
            for row in raw_preferred_rows
            if str(row["source_name"]) in ai_ready_source_names
        ]
        latest_observation_time = max(
            (
                row["observation_time_dt"]
                for row in preferred_rows
                if row.get("observation_time_dt") is not None
            ),
            default=None,
        )
        raw_latest_observation_time = max(
            (
                row["observation_time_dt"]
                for row in raw_preferred_rows
                if row.get("observation_time_dt") is not None
            ),
            default=None,
        )
        source_counts = self._count_rows_by_source(preferred_rows)
        raw_source_counts = self._count_rows_by_source(raw_preferred_rows)
        bundle = {
            "as_of": (
                latest_observation_time.isoformat()
                if latest_observation_time is not None
                else None
            ),
            "raw_as_of": (
                raw_latest_observation_time.isoformat()
                if raw_latest_observation_time is not None
                else None
            ),
            "latest_observation_time": (
                latest_observation_time.isoformat()
                if latest_observation_time is not None
                else None
            ),
            "raw_latest_observation_time": (
                raw_latest_observation_time.isoformat()
                if raw_latest_observation_time is not None
                else None
            ),
            "row_count": len(preferred_rows),
            "raw_row_count": len(raw_preferred_rows),
            "source_counts": source_counts,
            "raw_source_counts": raw_source_counts,
            "ai_ready_source_names": sorted(ai_ready_source_names),
            "ai_excluded_source_names": [
                str(item["source_name"])
                for item in ai_excluded_sources
            ],
            "ai_excluded_sources": ai_excluded_sources,
            "sources": {},
        }

        if (
            (not requested_sources or "google_trends" in requested_sources)
            and "google_trends" in ai_ready_source_names
        ):
            google_rows = [row for row in preferred_rows if row["source_name"] == "google_trends"]
            bundle["sources"]["google_trends"] = self._build_google_trends_context(
                google_rows,
                entity_name_map,
            )
        if (
            (not requested_sources or "github" in requested_sources)
            and "github" in ai_ready_source_names
        ):
            github_rows = [row for row in preferred_rows if row["source_name"] == "github"]
            bundle["sources"]["github"] = self._build_github_context(
                github_rows,
                entity_name_map,
            )
        if (
            (not requested_sources or "stablecoin" in requested_sources)
            and "stablecoin" in ai_ready_source_names
        ):
            stablecoin_rows = [row for row in preferred_rows if row["source_name"] == "stablecoin"]
            bundle["sources"]["stablecoin"] = self._build_stablecoin_context(
                stablecoin_rows,
                entity_name_map,
            )

        quality_summary = summarize_quality_flag_counts(preferred_rows)
        raw_quality_summary = summarize_quality_flag_counts(raw_preferred_rows)
        data_quality_flags, quality_notes = self._build_context_quality(
            preferred_rows=preferred_rows,
            raw_row_count=len(raw_preferred_rows),
            ai_excluded_source_count=len(ai_excluded_sources),
            requested_sources=requested_sources,
            requested_entity_keys=self._normalize_entity_keys(entity_keys),
            coverage_rows=coverage_rows,
            bundle_sources=bundle["sources"],
            configured_universe_summary=configured_universe_summary,
        )
        expected_entity_count = sum(
            int(row.get("expected_entity_count") or 0)
            for row in coverage_rows
        )
        observed_entity_count = sum(
            int(row.get("latest_entity_count") or 0)
            for row in coverage_rows
        )
        observed_factor_count = sum(
            int(row.get("latest_factor_count") or 0)
            for row in coverage_rows
        )
        coverage_by_source = [
            {
                "source_name": row["source_name"],
                "entity_type": row["entity_type"],
                "phase": row["phase"],
                "expected_entity_count": row["expected_entity_count"],
                "observed_entity_count": row["latest_entity_count"],
                "observed_factor_count": row["latest_factor_count"],
                "observed_point_count": row["latest_point_count"],
                "is_ready_for_ai": row["is_ready_for_ai"],
            }
            for row in coverage_rows
        ]
        coverage_by_entity_type = self._summarize_entity_type_coverage(
            coverage_rows
        )
        bundle["coverage_summary"] = {
            "expected_entity_count": expected_entity_count,
            "observed_entity_count": observed_entity_count,
            "observed_factor_count": observed_factor_count,
            "observed_point_count": len(raw_preferred_rows),
            "observed_source_count": len(raw_source_counts),
            "coverage_by_source": coverage_by_source,
            "coverage_by_entity_type": coverage_by_entity_type,
        }
        bundle["configured_universe_summary"] = configured_universe_summary
        bundle["latest_quality_flag_breakdown"] = quality_summary["breakdown"]
        bundle["latest_ok_point_count"] = quality_summary["ok_count"]
        bundle["latest_partial_point_count"] = quality_summary["partial_count"]
        bundle["latest_fallback_point_count"] = quality_summary["fallback_count"]
        bundle["latest_stale_point_count"] = quality_summary["stale_count"]
        bundle["latest_unknown_quality_point_count"] = quality_summary["unknown_count"]
        bundle["latest_non_ok_point_count"] = quality_summary["non_ok_count"]
        bundle["latest_quality_ready_ratio"] = quality_summary["ready_ratio"]
        bundle["raw_latest_quality_flag_breakdown"] = raw_quality_summary["breakdown"]
        bundle["raw_latest_quality_ready_ratio"] = raw_quality_summary["ready_ratio"]
        bundle["source_health_summary"] = {
            "source_count": coverage.get("source_count", 0),
            "ready_source_count": coverage.get("ready_source_count", 0),
            "problem_source_count": coverage.get("problem_source_count", 0),
            "stale_source_count": coverage.get("stale_source_count", 0),
            "ready_for_ai_source_count": coverage.get("ready_for_ai_source_count", 0),
            "not_ready_for_ai_source_count": coverage.get(
                "not_ready_for_ai_source_count",
                0,
            ),
        }
        bundle["source_health"] = [
            {
                "source_name": row["source_name"],
                "health_status": row["health_status"],
                "is_ready_for_ai": row["is_ready_for_ai"],
                "phase": row["phase"],
                "entity_type": row["entity_type"],
                "expected_entity_count": row["expected_entity_count"],
                "latest_entity_count": row["latest_entity_count"],
                "latest_factor_count": row["latest_factor_count"],
                "latest_point_count": row["latest_point_count"],
                "latest_quality_ready_ratio": row["latest_quality_ready_ratio"],
                "data_quality_flags": row["data_quality_flags"],
                "quality_notes": row["quality_notes"],
            }
            for row in coverage_rows
        ]
        bundle["data_quality_flags"] = data_quality_flags
        bundle["quality_notes"] = quality_notes
        return bundle

    def _run_source_job(
        self,
        source_name: str,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        local_db = DBManager(self.db.db_path)
        local_service = AlternativeDataService(
            client=self.client,
            db=local_db,
        )
        try:
            return local_service.collect_once(
                source_names=[source_name],
                entity_keys=entity_keys,
            )
        finally:
            local_service.close()

    def _run_github_job(
        self,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        return self._run_source_job(
            source_name="github",
            entity_keys=entity_keys,
        )

    def _run_google_trends_job(
        self,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        return self._run_source_job(
            source_name="google_trends",
            entity_keys=entity_keys,
        )

    def _run_stablecoin_job(
        self,
        entity_keys: list[str] | None = None,
    ) -> dict[str, int]:
        return self._run_source_job(
            source_name="stablecoin",
            entity_keys=entity_keys,
        )

    def build_scheduler(
        self,
        source_names: list[str] | None = None,
        entity_keys: list[str] | None = None,
    ) -> BlockingScheduler:
        requested_sources = self._normalize_sources(source_names)
        entity_keys = self._normalize_entity_keys(entity_keys)
        scheduler = BlockingScheduler()

        if self._should_run_source(
            requested_sources,
            "google_trends",
            ALTERNATIVE_CONFIG["enable_google_trends"],
        ):
            scheduler.add_job(
                self._run_google_trends_job,
                "interval",
                seconds=ALTERNATIVE_CONFIG["google_trends_interval_seconds"],
                id="alternative_google_trends",
                name="Google Trends 搜索热度采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(
                    300,
                    ALTERNATIVE_CONFIG["google_trends_interval_seconds"],
                ),
                kwargs={"entity_keys": entity_keys},
            )

        if self._should_run_source(
            requested_sources,
            "github",
            ALTERNATIVE_CONFIG["enable_github"],
        ):
            scheduler.add_job(
                self._run_github_job,
                "interval",
                seconds=ALTERNATIVE_CONFIG["github_interval_seconds"],
                id="alternative_github",
                name="GitHub 开发者活跃度采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(300, ALTERNATIVE_CONFIG["github_interval_seconds"]),
                kwargs={"entity_keys": entity_keys},
            )

        if self._should_run_source(
            requested_sources,
            "stablecoin",
            ALTERNATIVE_CONFIG["enable_stablecoin"],
        ):
            scheduler.add_job(
                self._run_stablecoin_job,
                "interval",
                seconds=ALTERNATIVE_CONFIG["stablecoin_interval_seconds"],
                id="alternative_stablecoin",
                name="稳定币供给与链分布采集",
                coalesce=True,
                max_instances=1,
                misfire_grace_time=max(300, ALTERNATIVE_CONFIG["stablecoin_interval_seconds"]),
                kwargs={"entity_keys": entity_keys},
            )
        return scheduler

    def close(self):
        self.db.close()
