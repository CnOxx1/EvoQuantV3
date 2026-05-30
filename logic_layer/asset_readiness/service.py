from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from database.db_manager import DBManager
from data_layer.alternative_data.service import AlternativeDataService
from data_layer.data_quality.audit import DataLayerAuditService
from data_layer.event_calendar_data.service import EventCalendarDataService
from data_layer.exchange_data.service import ExchangeDataService
from data_layer.news_data.service import NewsDataService
from data_layer.onchain_data.service import OnchainDataService
from data_layer.options_data.service import OptionsDataService
from data_layer.tokenomics_data.service import TokenomicsDataService


class AssetReadinessService:
    """基于真实已落库数据构建资产级证据可用性矩阵。"""

    BAND_WEIGHTS = {
        "exchange": 0.30,
        "news": 0.15,
        "event_calendar": 0.10,
        "onchain": 0.15,
        "tokenomics": 0.10,
        "options": 0.10,
        "alternative": 0.05,
        "macro": 0.05,
    }
    REQUIRED_BANDS = (
        "exchange",
        "news",
        "event_calendar",
        "onchain",
        "tokenomics",
        "options",
        "macro",
    )
    READY_STATUSES = {"ready", "shared_ready"}
    LIMITED_STATUSES = {"limited"}
    ASSET_ALIAS_REGISTRY_PATH = (
        Path(__file__).resolve().parents[2]
        / "data_layer"
        / "news_data"
        / "registry"
        / "tracked_assets.json"
    )

    def __init__(
        self,
        db: DBManager | None = None,
        exchange_service: ExchangeDataService | None = None,
        news_service: NewsDataService | None = None,
        event_calendar_service: EventCalendarDataService | None = None,
        onchain_service: OnchainDataService | None = None,
        tokenomics_service: TokenomicsDataService | None = None,
        options_service: OptionsDataService | None = None,
        alternative_service: AlternativeDataService | None = None,
        audit_service: DataLayerAuditService | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.exchange_service = exchange_service or ExchangeDataService(db=self.db)
        self.news_service = news_service or NewsDataService(db=self.db)
        self.event_calendar_service = (
            event_calendar_service or EventCalendarDataService(db=self.db)
        )
        self.onchain_service = onchain_service or OnchainDataService(db=self.db)
        self.tokenomics_service = tokenomics_service or TokenomicsDataService(db=self.db)
        self.options_service = options_service or OptionsDataService(db=self.db)
        self.alternative_service = alternative_service or AlternativeDataService(db=self.db)
        self.audit_service = audit_service or DataLayerAuditService(db=self.db)
        self.asset_aliases, self.alias_to_asset = self._load_asset_alias_registry()

    def init_storage(self):
        self.db.init_analytics_tables()

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _load_asset_alias_registry(cls) -> tuple[dict[str, set[str]], dict[str, str]]:
        asset_aliases: dict[str, set[str]] = {}
        alias_to_asset: dict[str, str] = {}
        try:
            payload = json.loads(cls.ASSET_ALIAS_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return asset_aliases, alias_to_asset

        for raw_asset, raw_aliases in payload.items():
            asset = str(raw_asset or "").strip().upper()
            if not asset:
                continue
            aliases = {
                asset,
                asset.replace("-", " ").replace("_", " "),
            }
            if isinstance(raw_aliases, list):
                aliases.update(
                    str(item or "").strip().upper()
                    for item in raw_aliases
                    if str(item or "").strip()
                )
            asset_aliases[asset] = {
                alias
                for alias in aliases
                if alias
            }
            for alias in asset_aliases[asset]:
                alias_to_asset[alias] = asset
        return asset_aliases, alias_to_asset

    @staticmethod
    def _normalize_asset_from_symbol(symbol: str | None) -> str | None:
        raw_symbol = str(symbol or "").strip()
        if not raw_symbol:
            return None
        if ":" in raw_symbol:
            raw_symbol = raw_symbol.split(":", 1)[0]
        raw_symbol = raw_symbol.upper()
        if "/" in raw_symbol:
            base, _, quote = raw_symbol.partition("/")
            return base if quote else raw_symbol
        for quote_suffix in ("USDT", "USDC", "FDUSD", "BUSD", "USD"):
            if raw_symbol.endswith(quote_suffix) and len(raw_symbol) > len(quote_suffix):
                return raw_symbol[: -len(quote_suffix)]
        return raw_symbol

    def _resolve_asset_key(self, raw_value: object) -> str | None:
        normalized_symbol = self._normalize_asset_from_symbol(str(raw_value or ""))
        candidates = [
            str(raw_value or "").strip().upper(),
            str(raw_value or "").strip().upper().replace("_", " "),
            str(raw_value or "").strip().upper().replace("-", " "),
        ]
        if normalized_symbol:
            candidates.extend(
                [
                    normalized_symbol,
                    normalized_symbol.replace("_", " "),
                    normalized_symbol.replace("-", " "),
                ]
            )

        for candidate in candidates:
            if not candidate:
                continue
            asset = self.alias_to_asset.get(candidate)
            if asset:
                return asset

        if normalized_symbol:
            return normalized_symbol
        return None

    def _normalize_asset_keys(self, asset_keys: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in asset_keys or []:
            asset = self._resolve_asset_key(item)
            if not asset or asset in seen:
                continue
            seen.add(asset)
            normalized.append(asset)
        return normalized

    @staticmethod
    def _dedupe_texts(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

    @staticmethod
    def _status_ratio(status: str) -> float:
        if status in {"ready", "shared_ready"}:
            return 1.0
        if status == "limited":
            return 0.5
        return 0.0

    @classmethod
    def _status_rank(cls, status: str) -> int:
        if status in cls.READY_STATUSES:
            return 2
        if status in cls.LIMITED_STATUSES:
            return 1
        return 0

    @classmethod
    def _is_ready_status(cls, status: str) -> bool:
        return status in cls.READY_STATUSES

    def _band_detail(
        self,
        *,
        band_name: str,
        status: str,
        evidence_count: int = 0,
        score_ratio: float | None = None,
        details: dict | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, object]:
        ratio = score_ratio if score_ratio is not None else self._status_ratio(status)
        weight = float(self.BAND_WEIGHTS.get(band_name, 0.0))
        return {
            "band_name": band_name,
            "status": status,
            "weight": weight,
            "score_ratio": round(float(ratio), 4),
            "weighted_score": round(weight * float(ratio), 4),
            "evidence_count": int(evidence_count or 0),
            "details": details or {},
            "notes": self._dedupe_texts(list(notes or [])),
        }

    def _index_exchange(self, bundle: dict) -> tuple[dict[str, dict], set[str]]:
        index: dict[str, dict] = {}
        tracked_assets: set[str] = set()
        for symbol in bundle.get("configured_universe_summary", {}).get("tracked_symbols") or []:
            asset = self._resolve_asset_key(symbol)
            if asset:
                tracked_assets.add(asset)
        for entry in bundle.get("symbols") or []:
            asset = self._resolve_asset_key(entry.get("symbol"))
            if not asset or asset == "MARKET":
                continue
            index[asset] = dict(entry)
        return index, tracked_assets

    @staticmethod
    def _visible_exchange_sections(entry: dict) -> list[str]:
        visible_sections: list[str] = []
        for section_name in ("spot", "orderbook", "funding", "open_interest", "liquidations", "positioning", "basis"):
            if entry.get(section_name):
                visible_sections.append(section_name)
        if (
            entry.get("trade_flow")
            or entry.get("trade_flow_spot")
            or entry.get("trade_flow_derivatives")
        ):
            visible_sections.append("trade_flow")
        return visible_sections

    def _index_news(self, bundle: dict) -> tuple[dict[str, dict], set[str]]:
        article_counts: Counter = Counter()
        source_counts: defaultdict[str, set[str]] = defaultdict(set)
        tracked_assets = {
            self._resolve_asset_key(symbol)
            for symbol in (
                bundle.get("configured_universe_summary", {}).get("tracked_symbols") or []
            )
        }
        tracked_assets.discard(None)
        for article in bundle.get("latest_articles") or []:
            source_name = str(article.get("source") or "")
            relevance_symbols = article.get("relevance_symbols") or []
            for symbol in relevance_symbols:
                asset = self._resolve_asset_key(symbol)
                if not asset or asset == "MARKET":
                    continue
                article_counts[asset] += 1
                if source_name:
                    source_counts[asset].add(source_name)
        return {
            asset: {
                "article_count_72h": int(article_counts.get(asset) or 0),
                "source_count_72h": len(source_counts.get(asset) or set()),
            }
            for asset in sorted(set(article_counts) | set(source_counts))
        }, {
            asset for asset in tracked_assets if asset
        }

    def _index_event_calendar(self, bundle: dict) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for item in bundle.get("symbol_watchlist") or []:
            asset = self._resolve_asset_key(item.get("symbol"))
            if not asset or asset == "MARKET":
                continue
            index[asset] = dict(item)
        return index

    def _index_onchain(self, bundle: dict) -> tuple[dict[str, dict], set[str]]:
        index: dict[str, dict] = {}
        tracked_assets: set[str] = set()
        for entity_keys in (
            bundle.get("configured_universe_summary", {}).get("entity_keys_by_type") or {}
        ).values():
            for entity_key in entity_keys or []:
                asset = self._resolve_asset_key(entity_key)
                if asset:
                    tracked_assets.add(asset)

        for entity in bundle.get("entities") or []:
            asset = self._resolve_asset_key(entity.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            matched = index.setdefault(
                asset,
                {
                    "entities": [],
                    "entity_types": set(),
                    "quality_flags": set(),
                    "observed_factor_count": 0,
                    "max_quality_ready_ratio": 0.0,
                },
            )
            matched["entities"].append(dict(entity))
            entity_type = str(entity.get("entity_type") or "").strip()
            if entity_type:
                matched["entity_types"].add(entity_type)
            quality_flag = str(entity.get("quality_flag") or "").strip()
            if quality_flag:
                matched["quality_flags"].add(quality_flag)
            matched["observed_factor_count"] += int(entity.get("observed_factor_count") or 0)
            matched["max_quality_ready_ratio"] = max(
                float(matched["max_quality_ready_ratio"] or 0.0),
                float(entity.get("quality_ready_ratio") or 0.0),
            )

        for value in index.values():
            value["entity_types"] = sorted(value["entity_types"])
            value["quality_flags"] = sorted(value["quality_flags"])
        return index, tracked_assets

    def _index_tokenomics(self, bundle: dict) -> tuple[dict[str, dict], set[str]]:
        index: dict[str, dict] = {}
        tracked_assets: set[str] = set()
        for entity_key in (
            bundle.get("configured_universe_summary", {}).get("tracked_entity_keys") or []
        ):
            asset = self._resolve_asset_key(entity_key)
            if asset:
                tracked_assets.add(asset)
        for entity in bundle.get("entities") or []:
            asset = self._resolve_asset_key(entity.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            index[asset] = dict(entity)
        return index, tracked_assets

    def _index_options(self, bundle: dict) -> tuple[dict[str, dict], set[str]]:
        index: dict[str, dict] = {}
        tracked_assets: set[str] = set()
        for entity_key in (
            bundle.get("configured_universe_summary", {}).get("tracked_entity_keys") or []
        ):
            asset = self._resolve_asset_key(entity_key)
            if asset:
                tracked_assets.add(asset)
        for asset_entry in bundle.get("assets") or []:
            asset = self._resolve_asset_key(asset_entry.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            index[asset] = dict(asset_entry)
        return index, tracked_assets

    def _index_alternative(self, bundle: dict) -> dict[str, dict]:
        index: dict[str, dict] = {}
        sources = bundle.get("sources") or {}

        for entity in (sources.get("google_trends") or {}).get("entities") or []:
            asset = self._resolve_asset_key(entity.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            index.setdefault(asset, {})["google_trends"] = dict(entity)

        for entity in (sources.get("github") or {}).get("entities") or []:
            asset = self._resolve_asset_key(entity.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            index.setdefault(asset, {})["github"] = dict(entity)

        for asset_entry in (sources.get("stablecoin") or {}).get("assets") or []:
            asset = self._resolve_asset_key(asset_entry.get("entity_key"))
            if not asset or asset == "MARKET":
                continue
            index.setdefault(asset, {})["stablecoin"] = dict(asset_entry)

        return index

    def _band_from_exchange(self, asset: str, exchange_index: dict[str, dict]) -> dict[str, object]:
        entry = exchange_index.get(asset)
        if entry is None:
            return self._band_detail(
                band_name="exchange",
                status="missing",
                notes=["当前没有可直接给 AI 使用的交易所微观结构快照。"],
            )
        coverage_summary = entry.get("coverage_summary") or {}
        complete_sections = list(coverage_summary.get("complete_sections") or [])
        partial_sections = list(coverage_summary.get("partial_sections") or [])
        visible_sections = self._visible_exchange_sections(entry)
        evidence_count = int(entry.get("row_count") or 0)
        raw_row_count = int(entry.get("raw_row_count") or 0)
        notes = list(entry.get("quality_notes") or [])[:4]
        if evidence_count <= 0 or not visible_sections:
            if raw_row_count > 0 or complete_sections or partial_sections:
                notes.insert(
                    0,
                    "当前虽然存在真实 raw exchange 快照，但没有任何 AI-ready section 进入主视图。",
                )
            else:
                notes.insert(0, "当前没有可直接给 AI 使用的交易所微观结构快照。")
            return self._band_detail(
                band_name="exchange",
                status="missing",
                evidence_count=evidence_count,
                details={
                    "symbol": entry.get("symbol"),
                    "visible_sections": visible_sections,
                    "raw_row_count": raw_row_count,
                    "raw_complete_sections": complete_sections,
                    "raw_partial_sections": partial_sections,
                    "latest_price": entry.get("spot", [{}])[0].get("last_price")
                    if entry.get("spot")
                    else None,
                },
                notes=self._dedupe_texts(notes)[:6],
            )
        has_spot = "spot" in set(visible_sections)
        has_supporting_structure = bool(
            set(visible_sections) & {"orderbook", "trade_flow", "funding", "open_interest", "basis"}
        )
        status = "ready" if has_spot and has_supporting_structure else "limited"
        if status == "limited":
            notes.append("当前只看到局部 AI-ready exchange section，市场微观结构仍偏薄。")
        return self._band_detail(
            band_name="exchange",
            status=status,
            evidence_count=evidence_count,
            details={
                "symbol": entry.get("symbol"),
                "visible_sections": visible_sections,
                "raw_row_count": raw_row_count,
                "complete_sections": complete_sections,
                "partial_sections": partial_sections,
                "latest_price": entry.get("spot", [{}])[0].get("last_price")
                if entry.get("spot")
                else None,
            },
            notes=notes,
        )

    def _band_from_news(self, asset: str, news_index: dict[str, dict], tracked_assets: set[str]) -> dict[str, object]:
        if asset not in tracked_assets and asset not in news_index:
            return self._band_detail(
                band_name="news",
                status="untracked",
                notes=["当前新闻注册表没有把该资产纳入默认跟踪宇宙。"],
            )
        info = news_index.get(asset) or {}
        article_count = int(info.get("article_count_72h") or 0)
        source_count = int(info.get("source_count_72h") or 0)
        if article_count >= 2:
            status = "ready"
        elif article_count > 0:
            status = "limited"
        else:
            status = "missing"
        notes: list[str] = []
        if article_count <= 0:
            notes.append("最近 72 小时没有命中该资产的 AI-ready 新闻。")
        elif article_count == 1:
            notes.append("最近 72 小时只有 1 篇命中新闻，叙事证据仍偏薄。")
        return self._band_detail(
            band_name="news",
            status=status,
            evidence_count=article_count,
            details={
                "article_count_72h": article_count,
                "source_count_72h": source_count,
            },
            notes=notes,
        )

    def _band_from_event_calendar(
        self,
        asset: str,
        event_index: dict[str, dict],
        band_report: dict[str, object] | None,
    ) -> dict[str, object]:
        if not band_report or not band_report.get("is_band_ready_for_ai"):
            return self._band_detail(
                band_name="event_calendar",
                status="shared_missing",
                notes=["当前未来事件日历证据带整体尚未达到 AI-ready。"],
            )
        info = event_index.get(asset) or {}
        event_count = int(info.get("event_count") or 0)
        notes = []
        if event_count <= 0:
            notes.append("未来 30 天暂无该资产的 AI-ready 事件命中。")
        return self._band_detail(
            band_name="event_calendar",
            status="shared_ready",
            evidence_count=event_count,
            details={
                "event_count_30d": event_count,
                "high_importance_event_count_30d": int(
                    info.get("high_importance_event_count") or 0
                ),
                "next_event_at": info.get("next_event_at"),
                "event_types": list(info.get("event_types") or []),
            },
            notes=notes,
        )

    def _band_from_onchain(self, asset: str, index: dict[str, dict], tracked_assets: set[str]) -> dict[str, object]:
        info = index.get(asset)
        if info is None:
            status = "untracked" if asset not in tracked_assets else "missing"
            notes = [
                "当前链上默认跟踪宇宙没有覆盖该资产。"
                if status == "untracked"
                else "当前没有可直接给 AI 使用的链上实体快照。"
            ]
            return self._band_detail(
                band_name="onchain",
                status=status,
                notes=notes,
            )
        max_ready_ratio = float(info.get("max_quality_ready_ratio") or 0.0)
        observed_factor_count = int(info.get("observed_factor_count") or 0)
        status = "ready" if max_ready_ratio >= 0.6 or observed_factor_count >= 3 else "limited"
        notes: list[str] = []
        if status == "limited":
            notes.append("链上实体已存在，但覆盖字段或质量比例仍偏弱。")
        return self._band_detail(
            band_name="onchain",
            status=status,
            evidence_count=len(info.get("entities") or []),
            score_ratio=max(max_ready_ratio, self._status_ratio(status)),
            details={
                "matched_entity_types": list(info.get("entity_types") or []),
                "observed_factor_count": observed_factor_count,
                "max_quality_ready_ratio": round(max_ready_ratio, 4),
                "quality_flags": list(info.get("quality_flags") or []),
            },
            notes=notes,
        )

    def _band_from_tokenomics(
        self,
        asset: str,
        index: dict[str, dict],
        tracked_assets: set[str],
    ) -> dict[str, object]:
        info = index.get(asset)
        if info is None:
            status = "untracked" if asset not in tracked_assets else "missing"
            notes = [
                "当前 tokenomics 默认跟踪宇宙没有覆盖该资产。"
                if status == "untracked"
                else "当前没有可直接给 AI 使用的 tokenomics 快照。"
            ]
            return self._band_detail(
                band_name="tokenomics",
                status=status,
                notes=notes,
            )
        observed_factor_count = int(info.get("observed_factor_count") or 0)
        quality_flag = str(info.get("quality_flag") or "")
        ready_ratio = float(info.get("quality_ready_ratio") or 0.0)
        status = (
            "ready"
            if quality_flag == "ok" or ready_ratio >= 0.6 or observed_factor_count >= 4
            else "limited"
        )
        notes: list[str] = []
        if status == "limited":
            notes.append("供给侧实体已存在，但缺失关键因子或质量比例仍偏弱。")
        return self._band_detail(
            band_name="tokenomics",
            status=status,
            evidence_count=observed_factor_count,
            score_ratio=max(ready_ratio, self._status_ratio(status)),
            details={
                "observed_factor_count": observed_factor_count,
                "quality_flag": quality_flag,
                "quality_ready_ratio": round(ready_ratio, 4),
                "scheduled_unlock_usd_7d": info.get("scheduled_unlock_usd_7d"),
                "scheduled_unlock_usd_30d": info.get("scheduled_unlock_usd_30d"),
                "staking_ratio": info.get("staking_ratio"),
            },
            notes=notes,
        )

    def _band_from_options(
        self,
        asset: str,
        index: dict[str, dict],
        tracked_assets: set[str],
    ) -> dict[str, object]:
        info = index.get(asset)
        if info is None:
            status = "untracked" if asset not in tracked_assets else "missing"
            notes = [
                "当前 options 默认跟踪宇宙没有覆盖该资产。"
                if status == "untracked"
                else "当前没有可直接给 AI 使用的期权快照。"
            ]
            return self._band_detail(
                band_name="options",
                status=status,
                notes=notes,
            )
        observed_factor_count = int(info.get("observed_factor_count") or 0)
        quality_flag = str(info.get("quality_flag") or "")
        status = (
            "ready"
            if quality_flag == "ok" or observed_factor_count >= 4
            else "limited"
        )
        notes: list[str] = []
        if status == "limited":
            notes.append("期权实体已存在，但关键期限/墙位/波动率字段仍不完整。")
        return self._band_detail(
            band_name="options",
            status=status,
            evidence_count=observed_factor_count,
            details={
                "observed_factor_count": observed_factor_count,
                "quality_flag": quality_flag,
                "atm_iv_30d": info.get("atm_iv_30d"),
                "iv_rv_spread_30d": info.get("iv_rv_spread_30d"),
                "net_gamma_exposure_ratio": info.get("net_gamma_exposure_ratio"),
            },
            notes=notes,
        )

    def _band_from_alternative(self, asset: str, index: dict[str, dict]) -> dict[str, object]:
        info = index.get(asset)
        if info is None:
            return self._band_detail(
                band_name="alternative",
                status="missing",
                notes=["当前没有与该资产匹配的 AI-ready alternative 证据。"],
            )
        sections = sorted(info)
        notes: list[str] = []
        if len(sections) == 1:
            notes.append("当前只命中 1 类补充证据，attention/builder/stablecoin 视角仍偏窄。")
        return self._band_detail(
            band_name="alternative",
            status="ready" if sections else "missing",
            evidence_count=len(sections),
            details={
                "matched_sections": sections,
                "google_trends_key": (info.get("google_trends") or {}).get("entity_key"),
                "github_key": (info.get("github") or {}).get("entity_key"),
                "stablecoin_key": (info.get("stablecoin") or {}).get("entity_key"),
            },
            notes=notes,
        )

    def _band_from_macro(self, band_report: dict[str, object] | None) -> dict[str, object]:
        if band_report and band_report.get("is_band_ready_for_ai"):
            return self._band_detail(
                band_name="macro",
                status="shared_ready",
                evidence_count=int(band_report.get("ready_for_ai_source_count") or 0),
                details={
                    "band_status": band_report.get("band_status"),
                    "ready_for_ai_source_count": band_report.get("ready_for_ai_source_count"),
                },
            )
        return self._band_detail(
            band_name="macro",
            status="shared_missing",
            notes=["当前宏观证据带整体尚未达到 AI-ready。"],
            details={
                "band_status": band_report.get("band_status") if band_report else None,
                "blocking_reasons": list(band_report.get("blocking_reasons") or [])
                if band_report
                else [],
            },
        )

    def _asset_status_from_bands(
        self,
        *,
        readiness_score: float,
        band_details: dict[str, dict[str, object]],
    ) -> str:
        exchange_status = str((band_details.get("exchange") or {}).get("status") or "")
        ready_required_band_count = sum(
            1
            for band_name in self.REQUIRED_BANDS
            if self._is_ready_status(
                str((band_details.get(band_name) or {}).get("status") or "")
            )
        )
        if exchange_status != "ready":
            return "blocked"
        if readiness_score >= 0.8 and ready_required_band_count >= 5:
            return "ready"
        if readiness_score >= 0.45:
            return "partial"
        return "thin"

    def build_latest_context_bundle(
        self,
        asset_keys: list[str] | None = None,
        audit_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        now = self._utc_now_naive()
        normalized_asset_keys = self._normalize_asset_keys(asset_keys)

        resolved_audit_payload = audit_payload or self.audit_service.load_market_world_audit()
        audit_summary = dict(resolved_audit_payload.get("summary") or {})
        band_reports = {
            str(item.get("band_name")): dict(item)
            for item in (resolved_audit_payload.get("bands") or [])
        }

        exchange_bundle = self.exchange_service.load_latest_market_context_bundle()
        news_bundle = self.news_service.load_latest_context_bundle(hours=72, limit=1000)
        event_bundle = self.event_calendar_service.load_upcoming_context_bundle(
            horizon_days=30,
            limit=500,
        )
        onchain_bundle = self.onchain_service.load_latest_context_bundle()
        tokenomics_bundle = self.tokenomics_service.load_latest_context_bundle()
        options_bundle = self.options_service.load_latest_context_bundle()
        alternative_bundle = self.alternative_service.load_latest_context_bundle()

        exchange_index, exchange_tracked_assets = self._index_exchange(exchange_bundle)
        news_index, news_tracked_assets = self._index_news(news_bundle)
        event_index = self._index_event_calendar(event_bundle)
        onchain_index, onchain_tracked_assets = self._index_onchain(onchain_bundle)
        tokenomics_index, tokenomics_tracked_assets = self._index_tokenomics(tokenomics_bundle)
        options_index, options_tracked_assets = self._index_options(options_bundle)
        alternative_index = self._index_alternative(alternative_bundle)

        asset_universe = sorted(
            set(exchange_index)
            | set(exchange_tracked_assets)
            | set(news_index)
            | set(news_tracked_assets)
            | set(event_index)
            | set(onchain_index)
            | set(onchain_tracked_assets)
            | set(tokenomics_index)
            | set(tokenomics_tracked_assets)
            | set(options_index)
            | set(options_tracked_assets)
            | set(alternative_index)
        )
        if normalized_asset_keys:
            asset_universe = [
                asset
                for asset in normalized_asset_keys
                if asset in set(asset_universe) or asset
            ]

        assets: list[dict[str, object]] = []
        band_coverage_summary: dict[str, Counter] = {
            band_name: Counter()
            for band_name in self.BAND_WEIGHTS
        }

        for asset in asset_universe:
            band_details = {
                "exchange": self._band_from_exchange(asset, exchange_index),
                "news": self._band_from_news(asset, news_index, news_tracked_assets),
                "event_calendar": self._band_from_event_calendar(
                    asset,
                    event_index,
                    band_reports.get("event_calendar"),
                ),
                "onchain": self._band_from_onchain(asset, onchain_index, onchain_tracked_assets),
                "tokenomics": self._band_from_tokenomics(
                    asset,
                    tokenomics_index,
                    tokenomics_tracked_assets,
                ),
                "options": self._band_from_options(
                    asset,
                    options_index,
                    options_tracked_assets,
                ),
                "alternative": self._band_from_alternative(asset, alternative_index),
                "macro": self._band_from_macro(band_reports.get("macro")),
            }
            for band_name, detail in band_details.items():
                band_coverage_summary[band_name][str(detail.get("status") or "missing")] += 1

            readiness_score = round(
                sum(float(detail.get("weighted_score") or 0.0) for detail in band_details.values()),
                4,
            )
            asset_status = self._asset_status_from_bands(
                readiness_score=readiness_score,
                band_details=band_details,
            )
            ready_band_count = sum(
                1
                for detail in band_details.values()
                if self._is_ready_status(str(detail.get("status") or ""))
            )
            limited_band_count = sum(
                1
                for detail in band_details.values()
                if str(detail.get("status") or "") in self.LIMITED_STATUSES
            )
            missing_band_names = [
                band_name
                for band_name, detail in band_details.items()
                if self._status_rank(str(detail.get("status") or "")) <= 0
            ]
            limited_band_names = [
                band_name
                for band_name, detail in band_details.items()
                if str(detail.get("status") or "") in self.LIMITED_STATUSES
            ]
            quality_notes = self._dedupe_texts(
                [
                    note
                    for detail in band_details.values()
                    for note in (detail.get("notes") or [])
                ]
            )

            asset_row = {
                "asset": asset,
                "asset_status": asset_status,
                "readiness_score": readiness_score,
                "ready_band_count": ready_band_count,
                "limited_band_count": limited_band_count,
                "missing_band_count": len(missing_band_names),
                "missing_band_names": missing_band_names,
                "limited_band_names": limited_band_names,
                "global_world_status": audit_summary.get("world_model_status"),
                "bands": band_details,
                "quality_notes": quality_notes[:10],
            }
            assets.append(asset_row)

        assets.sort(
            key=lambda item: (
                {"ready": 0, "partial": 1, "thin": 2, "blocked": 3}.get(
                    str(item.get("asset_status") or ""),
                    9,
                ),
                -float(item.get("readiness_score") or 0.0),
                str(item.get("asset") or ""),
            )
        )

        asset_status_counts = Counter(str(item.get("asset_status") or "blocked") for item in assets)
        average_readiness_score = round(
            sum(float(item.get("readiness_score") or 0.0) for item in assets) / max(len(assets), 1),
            4,
        )
        data_quality_flags: list[str] = []
        quality_notes: list[str] = []
        world_status = str(audit_summary.get("world_model_status") or "blocked")
        if world_status == "blocked":
            data_quality_flags.append("market_world_model_blocked")
            quality_notes.append(
                "当前跨模块市场世界模型仍处于 blocked，说明至少一条 required 证据带还没有达到 AI-ready。"
            )
        if int(asset_status_counts.get("ready") or 0) <= 0:
            data_quality_flags.append("no_asset_fully_ready")
            quality_notes.append("当前没有任何资产达到全证据带 ready 状态。")
        if int(asset_status_counts.get("partial") or 0) > 0:
            quality_notes.append(
                f"当前仍有 {int(asset_status_counts.get('partial') or 0)} 个资产处于 partial，可做有限分析，但不代表全证据带完整。"
            )
        if average_readiness_score < 0.35:
            data_quality_flags.append("asset_readiness_score_thin")
            quality_notes.append("当前全资产平均 readiness score 偏低，数据世界对 AI 来说仍然偏薄。")

        return {
            "as_of": now.isoformat(),
            "generated_at": now.isoformat(),
            "scope_kind": "filtered" if normalized_asset_keys else "default",
            "market_world_status": world_status,
            "market_world_summary": {
                "required_band_count": int(audit_summary.get("required_band_count") or 0),
                "required_ready_band_count": int(
                    audit_summary.get("required_ready_band_count") or 0
                ),
                "critical_gap_count": int(audit_summary.get("critical_gap_count") or 0),
                "critical_gap_band_names": list(
                    audit_summary.get("critical_gap_band_names") or []
                ),
                "blocked_band_names": list(audit_summary.get("blocked_band_names") or []),
                "partial_band_names": list(audit_summary.get("partial_band_names") or []),
            },
            "global_band_statuses": {
                band_name: {
                    "band_status": report.get("band_status"),
                    "is_band_ready_for_ai": bool(report.get("is_band_ready_for_ai")),
                    "ready_for_ai_source_count": int(
                        report.get("ready_for_ai_source_count") or 0
                    ),
                    "blocking_reasons": list(report.get("blocking_reasons") or []),
                }
                for band_name, report in band_reports.items()
            },
            "asset_count": len(assets),
            "ready_asset_count": int(asset_status_counts.get("ready") or 0),
            "partial_asset_count": int(asset_status_counts.get("partial") or 0),
            "thin_asset_count": int(asset_status_counts.get("thin") or 0),
            "blocked_asset_count": int(asset_status_counts.get("blocked") or 0),
            "average_readiness_score": average_readiness_score,
            "band_coverage_summary": {
                band_name: dict(counter)
                for band_name, counter in band_coverage_summary.items()
            },
            "top_analysis_candidate_assets": [
                {
                    "asset": item["asset"],
                    "asset_status": item["asset_status"],
                    "readiness_score": item["readiness_score"],
                    "missing_band_names": item["missing_band_names"],
                }
                for item in assets
                if str(item.get("asset_status") or "") in {"ready", "partial"}
            ][:10],
            "data_quality_flag": (
                "ok"
                if world_status == "ready" and int(asset_status_counts.get("ready") or 0) > 0
                else "partial"
                if int(asset_status_counts.get("partial") or 0) > 0
                else "blocked"
            ),
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
            "assets": assets,
        }

    def save_snapshot(self, bundle: dict | None = None) -> dict[str, object]:
        payload = dict(bundle or self.build_latest_context_bundle())
        snapshot_time = str(payload.get("generated_at") or self._utc_now_naive().isoformat())
        self.db.execute(
            """
            INSERT INTO asset_readiness_snapshots (
                snapshot_time, scope_kind, market_world_status, asset_count,
                ready_asset_count, partial_asset_count, thin_asset_count,
                blocked_asset_count, average_readiness_score, data_quality_flag,
                bundle_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_time,
                str(payload.get("scope_kind") or "default"),
                str(payload.get("market_world_status") or "blocked"),
                int(payload.get("asset_count") or 0),
                int(payload.get("ready_asset_count") or 0),
                int(payload.get("partial_asset_count") or 0),
                int(payload.get("thin_asset_count") or 0),
                int(payload.get("blocked_asset_count") or 0),
                self._safe_float(payload.get("average_readiness_score")),
                str(payload.get("data_quality_flag") or "blocked"),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.db.commit()
        row = self.db.fetch_one(
            """
            SELECT id, snapshot_time, scope_kind, market_world_status,
                   asset_count, ready_asset_count, partial_asset_count,
                   blocked_asset_count, data_quality_flag
            FROM asset_readiness_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else {}

    def close(self):
        self.db.close()
