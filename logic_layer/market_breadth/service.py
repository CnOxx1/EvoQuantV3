from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from database.db_manager import DBManager
from data_layer.exchange_data.service import ExchangeDataService
from data_layer.news_data.service import NewsDataService
from data_layer.tokenomics_data.service import TokenomicsDataService


class MarketBreadthService:
    """基于真实已落库数据构建跨资产市场广度快照。"""

    MINIMUM_AI_READY_ASSET_COUNT = 8
    MINIMUM_ARTICLE_ASSET_COUNT = 6
    MINIMUM_UNLOCK_ASSET_COUNT = 4

    def __init__(self, db: DBManager | None = None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.exchange_service = ExchangeDataService(db=self.db)
        self.news_service = NewsDataService(db=self.db)
        self.tokenomics_service = TokenomicsDataService(db=self.db)

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
    def _normalize_asset_keys(cls, asset_keys: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in asset_keys or []:
            asset = cls._normalize_asset_from_symbol(item)
            if not asset or asset in seen:
                continue
            seen.add(asset)
            normalized.append(asset)
        return normalized

    @staticmethod
    def _normalize_asset_from_symbol(symbol: str | None) -> str | None:
        raw_symbol = str(symbol or "").strip().upper()
        if not raw_symbol:
            return None
        if "/" in raw_symbol:
            base, _, quote = raw_symbol.partition("/")
            return base if quote else raw_symbol
        if raw_symbol.endswith("USDT"):
            return raw_symbol[:-4] or raw_symbol
        return raw_symbol

    @staticmethod
    def _article_effective_time(row: dict) -> datetime | None:
        for field_name in ("published_at", "collected_at"):
            value = row.get(field_name)
            if not value:
                continue
            try:
                return datetime.fromisoformat(str(value))
            except ValueError:
                continue
        return None

    @staticmethod
    def _sorted_counter(counter: Counter, field_name: str) -> list[dict]:
        total = sum(counter.values()) or 1
        return [
            {
                field_name: key,
                "count": count,
                "share": round(count / total, 4),
            }
            for key, count in sorted(
                counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

    def _load_exchange_snapshot(self) -> dict:
        return self.exchange_service.load_latest_market_context_bundle()

    @staticmethod
    def _visible_exchange_sections(symbol_entry: dict) -> list[str]:
        visible_sections: list[str] = []
        for section_name in (
            "spot",
            "orderbook",
            "funding",
            "open_interest",
            "liquidations",
            "positioning",
            "basis",
        ):
            if symbol_entry.get(section_name):
                visible_sections.append(section_name)
        if (
            symbol_entry.get("trade_flow")
            or symbol_entry.get("trade_flow_spot")
            or symbol_entry.get("trade_flow_derivatives")
        ):
            visible_sections.append("trade_flow")
        return visible_sections

    def build_latest_context_bundle(
        self,
        asset_keys: list[str] | None = None,
    ) -> dict:
        now = self._utc_now_naive()
        normalized_asset_keys = self._normalize_asset_keys(asset_keys)
        exchange_symbols = (
            [f"{asset}/USDT" for asset in normalized_asset_keys]
            if normalized_asset_keys
            else None
        )
        exchange_bundle = self.exchange_service.load_latest_market_context_bundle(
            symbols=exchange_symbols
        )
        news_bundle = self.news_service.load_latest_context_bundle(hours=72, limit=1000)
        tokenomics_bundle = self.tokenomics_service.load_latest_context_bundle(
            entity_keys=normalized_asset_keys or None,
        )
        news_articles = list(news_bundle.get("latest_articles") or [])
        unlock_events = list(tokenomics_bundle.get("upcoming_unlock_events") or [])

        ai_ready_assets: set[str] = set()
        asset_rows: dict[str, dict[str, object]] = {}
        article_counts: Counter = Counter()
        article_source_counts: defaultdict[str, set[str]] = defaultdict(set)
        unlock_value_30d: defaultdict[str, float] = defaultdict(float)
        unlock_event_counts: Counter = Counter()
        funding_bias_counter: Counter = Counter()
        breadth_flags: list[str] = []
        breadth_notes: list[str] = []

        for symbol_entry in exchange_bundle.get("symbols") or []:
            asset = self._normalize_asset_from_symbol(symbol_entry.get("symbol"))
            if not asset:
                continue
            if normalized_asset_keys and asset not in normalized_asset_keys:
                continue
            visible_sections = self._visible_exchange_sections(symbol_entry)
            if int(symbol_entry.get("row_count") or 0) > 0 and visible_sections:
                ai_ready_assets.add(asset)
            coverage_summary = symbol_entry.get("coverage_summary") or {}
            trade_flow_spot = symbol_entry.get("trade_flow_spot") or []
            trade_flow_derivatives = symbol_entry.get("trade_flow_derivatives") or []
            funding_rows = symbol_entry.get("funding") or []
            basis_rows = symbol_entry.get("basis") or []
            latest_price = None
            spot_rows = symbol_entry.get("spot") or []
            if spot_rows:
                latest_price = self._safe_float(spot_rows[0].get("last_price"))
            funding_mean = None
            funding_values = [
                self._safe_float(row.get("funding_rate"))
                for row in funding_rows
                if self._safe_float(row.get("funding_rate")) is not None
            ]
            if funding_values:
                funding_mean = sum(funding_values) / len(funding_values)
                funding_bias_counter["positive" if funding_mean > 0 else "negative"] += 1
            basis_values = [
                self._safe_float(row.get("basis_bps"))
                for row in basis_rows
                if self._safe_float(row.get("basis_bps")) is not None
            ]
            basis_mean = sum(basis_values) / len(basis_values) if basis_values else None
            asset_rows[asset] = {
                "asset": asset,
                "symbol": symbol_entry.get("symbol"),
                "latest_price": latest_price,
                "exchange_visible_section_count": len(visible_sections),
                "exchange_visible_sections": visible_sections,
                "exchange_section_count": int(
                    coverage_summary.get("configured_section_count") or 0
                ),
                "exchange_complete_sections": list(
                    coverage_summary.get("complete_sections") or []
                ),
                "exchange_partial_sections": list(
                    coverage_summary.get("partial_sections") or []
                ),
                "exchange_row_count": int(symbol_entry.get("row_count") or 0),
                "exchange_raw_row_count": int(symbol_entry.get("raw_row_count") or 0),
                "trade_flow_row_count": len(trade_flow_spot) + len(trade_flow_derivatives),
                "funding_row_count": len(funding_rows),
                "basis_row_count": len(basis_rows),
                "funding_mean": funding_mean,
                "basis_mean_bps": basis_mean,
                "data_quality_flags": list(symbol_entry.get("data_quality_flags") or []),
                "quality_notes": list(symbol_entry.get("quality_notes") or []),
            }

        for article in news_articles:
            source_name = str(article.get("source") or "")
            symbols = article.get("relevance_symbols") or article.get("relevance_symbols_list") or []
            for symbol in symbols:
                asset = self._normalize_asset_from_symbol(symbol)
                if not asset:
                    continue
                if normalized_asset_keys and asset not in normalized_asset_keys:
                    continue
                article_counts[asset] += 1
                article_source_counts[asset].add(source_name)

        for event in unlock_events:
            asset = self._normalize_asset_from_symbol(
                event.get("asset") or event.get("entity_key")
            )
            if not asset:
                continue
            if normalized_asset_keys and asset not in normalized_asset_keys:
                continue
            unlock_event_counts[asset] += 1
            unlock_value_30d[asset] += float(event.get("unlock_value_usd") or 0.0)

        for entity in tokenomics_bundle.get("entities") or []:
            asset = self._normalize_asset_from_symbol(entity.get("entity_key"))
            if not asset:
                continue
            if normalized_asset_keys and asset not in normalized_asset_keys:
                continue
            asset_rows.setdefault(asset, {"asset": asset})
            asset_rows[asset]["scheduled_unlock_usd_7d"] = self._safe_float(
                entity.get("scheduled_unlock_usd_7d")
            )
            asset_rows[asset]["staking_ratio"] = self._safe_float(entity.get("staking_ratio"))
            asset_rows[asset]["tokenomics_quality_flag"] = entity.get("quality_flag")

        all_assets = sorted(
            set(asset_rows)
            | set(article_counts)
            | set(unlock_event_counts)
            | set(normalized_asset_keys)
        )
        breadth_rows: list[dict] = []
        for asset in all_assets:
            row = dict(asset_rows.get(asset) or {"asset": asset})
            row["recent_article_count_72h"] = int(article_counts.get(asset) or 0)
            row["recent_article_source_count_72h"] = len(article_source_counts.get(asset) or set())
            row["unlock_event_count_30d"] = int(unlock_event_counts.get(asset) or 0)
            row["unlock_value_usd_30d"] = round(float(unlock_value_30d.get(asset) or 0.0), 4)
            row["is_ai_ready_market_asset"] = asset in ai_ready_assets
            breadth_rows.append(row)

        breadth_rows.sort(
            key=lambda item: (
                0 if item.get("is_ai_ready_market_asset") else 1,
                -int(item.get("recent_article_count_72h") or 0),
                -float(item.get("unlock_value_usd_30d") or 0.0),
                str(item.get("asset") or ""),
            )
        )

        ai_ready_asset_count = len(ai_ready_assets)
        article_asset_count = len(article_counts)
        unlock_asset_count = len(unlock_event_counts)
        breadth_score = (
            min(ai_ready_asset_count / max(self.MINIMUM_AI_READY_ASSET_COUNT, 1), 1.0) * 0.5
            + min(article_asset_count / max(self.MINIMUM_ARTICLE_ASSET_COUNT, 1), 1.0) * 0.3
            + min(unlock_asset_count / max(self.MINIMUM_UNLOCK_ASSET_COUNT, 1), 1.0) * 0.2
        )
        breadth_score = round(breadth_score, 4)

        if ai_ready_asset_count >= self.MINIMUM_AI_READY_ASSET_COUNT:
            breadth_status = "sufficient"
        elif ai_ready_asset_count >= max(2, self.MINIMUM_AI_READY_ASSET_COUNT // 2):
            breadth_status = "narrow"
            breadth_flags.append("configured_market_breadth_limited")
            breadth_notes.append(
                "当前 AI-ready 市场资产覆盖仍偏窄，更像核心执行资产视角，而不是更广的加密市场 breadth。"
            )
        else:
            breadth_status = "thin"
            breadth_flags.append("configured_market_breadth_thin")
            breadth_notes.append(
                "当前 AI-ready 市场资产覆盖很薄，AI 看到的仍主要是极少数核心资产，不足以代表更广市场。"
            )

        if article_asset_count == 0:
            breadth_flags.append("news_asset_breadth_missing")
            breadth_notes.append("最近 AI-ready 新闻流里没有可映射资产，跨资产叙事广度目前为空。")
        elif article_asset_count < self.MINIMUM_ARTICLE_ASSET_COUNT:
            breadth_flags.append("news_asset_breadth_limited")
            breadth_notes.append("最近 AI-ready 新闻流可映射资产数量偏少，叙事 breadth 仍受限。")

        if unlock_asset_count == 0:
            breadth_flags.append("unlock_breadth_missing")
            breadth_notes.append("未来 30d AI-ready 解锁事件覆盖为空，供给事件广度当前不可用。")

        exchange_raw_row_count = int(exchange_bundle.get("raw_row_count") or 0)
        if ai_ready_asset_count == 0 and exchange_raw_row_count > 0:
            breadth_flags.append("exchange_raw_only_no_ai_ready_assets")
            breadth_notes.append(
                "交易所层虽然还有真实 raw 快照，但当前没有任何资产保留 AI-ready 市场结构 section。"
            )

        raw_news_article_count = int(news_bundle.get("raw_article_count") or 0)
        if article_asset_count == 0 and raw_news_article_count > 0:
            breadth_flags.append("news_raw_only_no_ai_ready_articles")
            breadth_notes.append(
                "新闻层虽然还有真实 raw 文章，但它们当前都没有进入 AI-ready 新闻主视图。"
            )

        raw_unlock_event_count = int(tokenomics_bundle.get("raw_upcoming_unlock_event_count") or 0)
        if unlock_asset_count == 0 and raw_unlock_event_count > 0:
            breadth_flags.append("unlock_raw_only_no_ai_ready_events")
            breadth_notes.append(
                "tokenomics 层虽然还有真实 raw 解锁事件，但它们当前都没有进入 AI-ready 解锁主视图。"
            )

        bundle = {
            "as_of": exchange_bundle.get("as_of") or now.isoformat(),
            "generated_at": now.isoformat(),
            "scope_kind": "filtered" if normalized_asset_keys else "default",
            "breadth_status": breadth_status,
            "breadth_score": breadth_score,
            "asset_count": len(all_assets),
            "ai_ready_asset_count": ai_ready_asset_count,
            "article_asset_count_72h": article_asset_count,
            "unlock_asset_count_30d": unlock_asset_count,
            "ai_ready_market_assets": sorted(ai_ready_assets),
            "top_assets_by_article_count_72h": self._sorted_counter(
                article_counts,
                "asset",
            )[:10],
            "top_assets_by_unlock_value_30d": [
                {
                    "asset": asset,
                    "unlock_value_usd_30d": round(value, 4),
                    "unlock_event_count_30d": int(unlock_event_counts.get(asset) or 0),
                }
                for asset, value in sorted(
                    unlock_value_30d.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ][:10],
            "funding_bias_summary": {
                "positive_asset_count": int(funding_bias_counter.get("positive") or 0),
                "negative_asset_count": int(funding_bias_counter.get("negative") or 0),
            },
            "coverage_summary": {
                "exchange_symbol_count": len(exchange_bundle.get("symbols") or []),
                "exchange_visible_symbol_count": len(ai_ready_assets),
                "exchange_raw_row_count": exchange_raw_row_count,
                "exchange_ai_ready_source_names": list(
                    exchange_bundle.get("ai_ready_source_names") or []
                ),
                "exchange_ai_excluded_source_names": list(
                    exchange_bundle.get("ai_excluded_source_names") or []
                ),
                "news_article_count_72h": len(news_articles),
                "news_raw_article_count_72h": raw_news_article_count,
                "news_ai_ready_source_names": list(news_bundle.get("ai_ready_source_names") or []),
                "news_ai_excluded_source_names": list(
                    news_bundle.get("ai_excluded_source_names") or []
                ),
                "unlock_event_count_30d": len(unlock_events),
                "unlock_raw_event_count_30d": raw_unlock_event_count,
                "tokenomics_ai_ready_source_names": list(
                    tokenomics_bundle.get("ai_ready_source_names") or []
                ),
                "tokenomics_ai_excluded_source_names": list(
                    tokenomics_bundle.get("ai_excluded_source_names") or []
                ),
            },
            "data_quality_flag": (
                "ok"
                if breadth_status == "sufficient"
                else "partial" if breadth_status == "narrow" else "thin"
            ),
            "data_quality_flags": breadth_flags,
            "quality_notes": breadth_notes,
            "assets": breadth_rows,
        }
        return bundle

    def save_snapshot(self, bundle: dict | None = None) -> dict[str, object]:
        payload = dict(bundle or self.build_latest_context_bundle())
        snapshot_time = str(payload.get("generated_at") or self._utc_now_naive().isoformat())
        self.db.execute(
            """
            INSERT INTO market_breadth_snapshots (
                snapshot_time, scope_kind, breadth_status, asset_count, ai_ready_asset_count,
                article_asset_count, unlock_asset_count, breadth_score, data_quality_flag,
                bundle_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_time,
                str(payload.get("scope_kind") or "default"),
                str(payload.get("breadth_status") or "limited"),
                int(payload.get("asset_count") or 0),
                int(payload.get("ai_ready_asset_count") or 0),
                int(payload.get("article_asset_count_72h") or 0),
                int(payload.get("unlock_asset_count_30d") or 0),
                self._safe_float(payload.get("breadth_score")),
                str(payload.get("data_quality_flag") or "partial"),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self.db.commit()
        row = self.db.fetch_one(
            """
            SELECT id, snapshot_time, scope_kind, breadth_status, asset_count,
                   ai_ready_asset_count, data_quality_flag
            FROM market_breadth_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else {}

    def close(self):
        self.db.close()
