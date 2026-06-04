from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Optional

from loguru import logger

from database.db_manager import DBManager
from logic_layer.macro_context.models import MacroContextConfig, MacroContextSnapshot
from logic_layer.macro_context.repository import MacroContextRepository


class MacroContextService:
    """将宏观原始时序聚合成 AI 可直接消费的上下文快照。"""

    def __init__(
        self,
        db: DBManager | None = None,
        repository: MacroContextRepository | None = None,
        config: MacroContextConfig | None = None,
    ):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter

            self.db = DatabaseRouter().get_analytics_db()
        self.repository = repository or MacroContextRepository(self.db)
        self.config = config or MacroContextConfig()

    def init_storage(self):
        self.db.init_analytics_tables()

    @staticmethod
    def _utc_now_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_db_timestamp(value) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _pct_change(latest: float, reference: float | None) -> float | None:
        if reference in (None, 0):
            return None
        return (latest - reference) / reference * 100

    @staticmethod
    def _bps_change(latest: float, reference: float | None) -> float | None:
        if reference is None:
            return None
        return (latest - reference) * 100

    @staticmethod
    def _completeness_score(snapshot: MacroContextSnapshot) -> float:
        checks = [
            snapshot.reference_1d_value is not None,
            snapshot.reference_5d_value is not None,
            snapshot.freshness_seconds is not None,
            snapshot.staleness_ttl_seconds is not None,
        ]
        return sum(1 for item in checks if item) / len(checks)

    @staticmethod
    def _normalize_quality_flag(value: str | None) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return "ok"
        if text in {"ok", "partial", "fallback", "stale"}:
            return text
        return "unknown"

    @classmethod
    def _factor_context_status(cls, snapshot: MacroContextSnapshot) -> str:
        quality_flag = cls._normalize_quality_flag(snapshot.quality_flag)
        if snapshot.is_stale or quality_flag == "stale":
            return "stale_only"
        if quality_flag == "unknown":
            return "raw_only"
        if (
            quality_flag == "ok"
            and snapshot.reference_1d_value is not None
            and snapshot.reference_5d_value is not None
        ):
            return "ready"
        return "partial"

    @staticmethod
    def _factor_is_ai_visible(context_status: str) -> bool:
        return context_status in {"ready", "partial"}

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

    @classmethod
    def _factor_context_quality_flags(
        cls,
        snapshot: MacroContextSnapshot,
        *,
        normalized_quality_flag: str,
    ) -> list[str]:
        flags: list[str] = []
        if snapshot.is_stale or normalized_quality_flag == "stale":
            flags.append("stale_factor")
        elif normalized_quality_flag == "partial":
            flags.append("partial_latest_point")
        elif normalized_quality_flag == "fallback":
            flags.append("fallback_latest_point")
        elif normalized_quality_flag == "unknown":
            flags.append("unknown_quality_flag")

        if snapshot.reference_1d_value is None:
            flags.append("missing_reference_1d")
        if snapshot.reference_5d_value is None:
            flags.append("missing_reference_5d")
        if snapshot.freshness_seconds is None:
            flags.append("missing_freshness")
        if snapshot.staleness_ttl_seconds is None:
            flags.append("missing_staleness_ttl")
        return flags

    @classmethod
    def _build_factor_payload(
        cls,
        snapshot: MacroContextSnapshot,
    ) -> dict:
        normalized_quality_flag = cls._normalize_quality_flag(snapshot.quality_flag)
        context_status = cls._factor_context_status(snapshot)
        context_quality_flags = cls._factor_context_quality_flags(
            snapshot,
            normalized_quality_flag=normalized_quality_flag,
        )
        return {
            "factor_id": snapshot.factor_id,
            "name": snapshot.name,
            "category": snapshot.category,
            "factor_type": snapshot.factor_type,
            "interval": snapshot.interval,
            "snapshot_time": snapshot.snapshot_time.isoformat(),
            "observation_time": snapshot.observation_time.isoformat(),
            "latest_value": snapshot.latest_value,
            "unit": snapshot.unit,
            "currency": snapshot.currency,
            "quality_flag": snapshot.quality_flag,
            "source_name": snapshot.source_name,
            "source_symbol": snapshot.source_symbol,
            "source_priority": snapshot.source_priority,
            "freshness_seconds": snapshot.freshness_seconds,
            "staleness_ttl_seconds": snapshot.staleness_ttl_seconds,
            "is_stale": snapshot.is_stale,
            "reference_1d_time": (
                snapshot.reference_1d_time.isoformat()
                if snapshot.reference_1d_time is not None
                else None
            ),
            "reference_1d_value": snapshot.reference_1d_value,
            "reference_1d_available": snapshot.reference_1d_value is not None,
            "change_1d_abs": snapshot.change_1d_abs,
            "change_1d_pct": snapshot.change_1d_pct,
            "change_1d_bps": snapshot.change_1d_bps,
            "reference_5d_time": (
                snapshot.reference_5d_time.isoformat()
                if snapshot.reference_5d_time is not None
                else None
            ),
            "reference_5d_value": snapshot.reference_5d_value,
            "reference_5d_available": snapshot.reference_5d_value is not None,
            "change_5d_abs": snapshot.change_5d_abs,
            "change_5d_pct": snapshot.change_5d_pct,
            "change_5d_bps": snapshot.change_5d_bps,
            "context_completeness_score": snapshot.context_completeness_score,
            "context_status": context_status,
            "context_quality_flags": context_quality_flags,
            "is_ai_visible": cls._factor_is_ai_visible(context_status),
        }

    @staticmethod
    def _max_iso_timestamp(rows: list[dict], field_name: str) -> str | None:
        values = [
            str(row.get(field_name))
            for row in rows
            if row.get(field_name)
        ]
        return max(values) if values else None

    @staticmethod
    def _yield_curve_bps(by_factor: dict[str, dict]) -> float | None:
        ust_2y = by_factor.get("ust_2y_yield::1d")
        ust_10y = by_factor.get("ust_10y_yield::1d")
        if not ust_2y or not ust_10y:
            return None
        return (ust_10y["latest_value"] - ust_2y["latest_value"]) * 100

    @staticmethod
    def _yield_curve_status(
        curve_bps: float | None,
        *,
        available_leg_count: int,
    ) -> str:
        if curve_bps is not None:
            return "ready"
        if available_leg_count > 0:
            return "partial"
        return "missing"

    @classmethod
    def _build_bundle_quality(
        cls,
        *,
        factor_count: int,
        raw_factor_count: int,
        ready_factor_count: int,
        partial_factor_count: int,
        stale_factor_count: int,
        raw_only_factor_count: int,
        missing_reference_1d_factor_count: int,
        missing_reference_5d_factor_count: int,
        coverage_score: float,
        raw_coverage_score: float,
        visible_yield_curve_bps: float | None,
        raw_yield_curve_bps: float | None,
    ) -> tuple[str, list[str], list[str], str]:
        flags: list[str] = []
        notes: list[str] = []

        if raw_factor_count <= 0:
            flags.append("macro_context_empty")
            notes.append("当前没有任何已生成的宏观上下文快照，AI 不能把宏观背景视为已覆盖。")
            return "blocked", flags, notes, "missing"

        visibility_status = "ready"
        if factor_count == 0:
            visibility_status = "raw_only"
            flags.append("macro_context_raw_only")
            notes.append(
                "当前 macro_context 只有 raw 因子，没有任何达到 AI 可见门槛的宏观因子；"
                "这通常意味着最新因子已全部 stale 或质量语义未标准化。"
            )
        elif factor_count < raw_factor_count:
            visibility_status = "partial"
            flags.append("macro_context_partially_visible")
            notes.append(
                "当前 macro_context 同时存在 AI-visible 因子和仅 raw 可见因子；"
                "被剥离的真实因子需要通过 raw_factors 单独诊断。"
            )

        if stale_factor_count:
            flags.append("macro_stale_factor_present")
            notes.append(
                f"当前有 {stale_factor_count} 个宏观因子已 stale，"
                "这些真实快照不会继续混入 AI 主视图。"
            )
        if raw_only_factor_count:
            flags.append("macro_unknown_quality_flag_present")
            notes.append(
                f"当前有 {raw_only_factor_count} 个宏观因子因 quality_flag 未标准化而只能保留在 raw 诊断里。"
            )
        if partial_factor_count:
            flags.append("macro_partial_factor_present")
            notes.append(
                f"当前有 {partial_factor_count} 个 AI-visible 宏观因子仍属于 partial，"
                "通常意味着变化参考窗口不完整或最新点来自降级路径。"
            )
        if missing_reference_1d_factor_count:
            flags.append("macro_missing_reference_1d_present")
            notes.append(
                f"当前有 {missing_reference_1d_factor_count} 个宏观因子缺少 1d 参考点，"
                "AI 不能对这些因子稳定读取短周期变化。"
            )
        if missing_reference_5d_factor_count:
            flags.append("macro_missing_reference_5d_present")
            notes.append(
                f"当前有 {missing_reference_5d_factor_count} 个宏观因子缺少 5d 参考点，"
                "AI 不能对这些因子稳定读取中周期变化。"
            )
        if raw_yield_curve_bps is not None and visible_yield_curve_bps is None:
            flags.append("yield_curve_raw_only")
            notes.append(
                "当前收益率曲线 2s10s 只能在 raw 宏观因子中计算，AI 主视图里这条 cross-asset 线索暂不可直接使用。"
            )
        if ready_factor_count == 0 and factor_count > 0:
            flags.append("macro_no_fully_ready_factor")
            notes.append(
                "当前虽仍有 AI-visible 宏观因子，但没有任何因子同时具备 clean 最新点和完整 1d/5d 参考窗口。"
            )

        quality_flag = "ok"
        if factor_count <= 0:
            quality_flag = "blocked"
        else:
            visible_ratio = factor_count / raw_factor_count if raw_factor_count else 0.0
            minimum_visible_count = min(raw_factor_count, max(1, ceil(raw_factor_count * 0.5)))
            if (
                factor_count < minimum_visible_count
                or visible_ratio < 0.5
                or coverage_score < 0.5
            ):
                quality_flag = "thin"
            elif flags:
                quality_flag = "partial"

        if raw_factor_count > 0 and raw_coverage_score < coverage_score:
            notes.append("raw 宏观因子的平均 completeness 低于 AI-visible 子集，说明被剥离的因子主要集中在低质量区域。")
        return quality_flag, flags, cls._dedupe_texts(notes)[:12], visibility_status

    def _build_snapshot_from_row(
        self,
        row: dict,
        snapshot_time: datetime,
        config: MacroContextConfig,
    ) -> MacroContextSnapshot:
        observation_time = self._parse_db_timestamp(row["observation_time"])
        if observation_time is None:
            raise ValueError(f"latest macro row 缺少 observation_time: {row}")

        latest_value = float(row["value"])
        freshness_seconds = max(
            0.0,
            (snapshot_time - observation_time).total_seconds(),
        )
        staleness_ttl_seconds = row.get("staleness_ttl_seconds")
        is_stale = (
            row.get("quality_flag") == "stale"
            or (
                staleness_ttl_seconds is not None
                and freshness_seconds > float(staleness_ttl_seconds)
            )
        )

        ref_1d = self.repository.fetch_reference_point(
            factor_id=row["factor_id"],
            interval=row["interval"],
            target_time=observation_time - timedelta(days=config.short_lookback_days),
        )
        ref_5d = self.repository.fetch_reference_point(
            factor_id=row["factor_id"],
            interval=row["interval"],
            target_time=observation_time - timedelta(days=config.medium_lookback_days),
        )

        reference_1d_time = self._parse_db_timestamp(
            ref_1d["observation_time"] if ref_1d else None
        )
        reference_1d_value = float(ref_1d["value"]) if ref_1d else None
        reference_5d_time = self._parse_db_timestamp(
            ref_5d["observation_time"] if ref_5d else None
        )
        reference_5d_value = float(ref_5d["value"]) if ref_5d else None

        change_1d_abs = (
            latest_value - reference_1d_value
            if reference_1d_value is not None
            else None
        )
        change_5d_abs = (
            latest_value - reference_5d_value
            if reference_5d_value is not None
            else None
        )
        change_1d_pct = self._pct_change(latest_value, reference_1d_value)
        change_5d_pct = self._pct_change(latest_value, reference_5d_value)
        change_1d_bps = (
            self._bps_change(latest_value, reference_1d_value)
            if row["factor_type"] == "macro_level"
            else None
        )
        change_5d_bps = (
            self._bps_change(latest_value, reference_5d_value)
            if row["factor_type"] == "macro_level"
            else None
        )

        snapshot = MacroContextSnapshot(
            factor_id=row["factor_id"],
            name=row["name"],
            category=row["category"],
            factor_type=row["factor_type"],
            interval=row["interval"],
            snapshot_time=snapshot_time,
            observation_time=observation_time,
            latest_value=latest_value,
            unit=row.get("unit"),
            currency=row.get("currency"),
            quality_flag=row.get("quality_flag") or "ok",
            source_name=row["source_name"],
            source_symbol=row["source_symbol"],
            source_priority=row.get("source_priority") or "primary",
            freshness_seconds=freshness_seconds,
            staleness_ttl_seconds=staleness_ttl_seconds,
            is_stale=is_stale,
            reference_1d_time=reference_1d_time,
            reference_1d_value=reference_1d_value,
            change_1d_abs=change_1d_abs,
            change_1d_pct=change_1d_pct,
            change_1d_bps=change_1d_bps,
            reference_5d_time=reference_5d_time,
            reference_5d_value=reference_5d_value,
            change_5d_abs=change_5d_abs,
            change_5d_pct=change_5d_pct,
            change_5d_bps=change_5d_bps,
        )
        snapshot.context_completeness_score = self._completeness_score(snapshot)
        snapshot.raw_context_json = json.dumps(
            {
                "reference_1d_time": (
                    reference_1d_time.isoformat() if reference_1d_time else None
                ),
                "reference_1d_value": reference_1d_value,
                "reference_5d_time": (
                    reference_5d_time.isoformat() if reference_5d_time else None
                ),
                "reference_5d_value": reference_5d_value,
                "enabled": row.get("enabled", 1),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return snapshot

    def build_latest_snapshots(
        self,
        factor_ids: list[str] | None = None,
        persist: bool = True,
        config: MacroContextConfig | None = None,
    ) -> list[MacroContextSnapshot]:
        active_config = config or self.config
        latest_rows = self.repository.fetch_latest_macro_points(
            factor_ids=factor_ids,
            interval=active_config.interval_filter,
            include_disabled_factors=active_config.include_disabled_factors,
        )
        if not latest_rows:
            logger.warning("没有 latest_macro_timeseries 数据，无法构建宏观上下文快照")
            return []

        snapshot_time = self._utc_now_naive()
        snapshots = [
            self._build_snapshot_from_row(row, snapshot_time, active_config)
            for row in latest_rows
        ]
        if persist:
            self.repository.save_context_snapshots(snapshots)
        logger.info(f"已生成 {len(snapshots)} 条 macro_context_snapshots")
        return snapshots

    def build_context_bundle_from_snapshots(
        self,
        snapshots: list[MacroContextSnapshot],
        factor_ids: list[str] | None = None,
        interval: str | None = None,
    ) -> dict:
        raw_factors = [
            self._build_factor_payload(snapshot)
            for snapshot in snapshots
        ]
        raw_factors.sort(
            key=lambda item: (
                str(item["factor_id"]),
                str(item["interval"]),
            )
        )
        factors = [
            factor
            for factor in raw_factors
            if factor["is_ai_visible"]
        ]

        visible_by_factor = {
            f"{factor['factor_id']}::{factor['interval']}": factor
            for factor in factors
        }
        raw_by_factor = {
            f"{factor['factor_id']}::{factor['interval']}": factor
            for factor in raw_factors
        }
        visible_yield_curve_bps = self._yield_curve_bps(visible_by_factor)
        raw_yield_curve_bps = self._yield_curve_bps(raw_by_factor)

        ready_factor_count = sum(
            1
            for factor in raw_factors
            if factor["context_status"] == "ready"
        )
        partial_factor_count = sum(
            1
            for factor in raw_factors
            if factor["context_status"] == "partial"
        )
        stale_factor_count = sum(
            1
            for factor in raw_factors
            if factor["context_status"] == "stale_only"
        )
        raw_only_factor_count = sum(
            1
            for factor in raw_factors
            if factor["context_status"] == "raw_only"
        )
        missing_reference_1d_factor_count = sum(
            1
            for factor in raw_factors
            if not factor["reference_1d_available"]
        )
        missing_reference_5d_factor_count = sum(
            1
            for factor in raw_factors
            if not factor["reference_5d_available"]
        )
        coverage_score = (
            sum(float(factor["context_completeness_score"]) for factor in factors) / len(factors)
            if factors
            else 0.0
        )
        raw_coverage_score = (
            sum(float(factor["context_completeness_score"]) for factor in raw_factors) / len(raw_factors)
            if raw_factors
            else 0.0
        )
        (
            data_quality_flag,
            data_quality_flags,
            quality_notes,
            visibility_status,
        ) = self._build_bundle_quality(
            factor_count=len(factors),
            raw_factor_count=len(raw_factors),
            ready_factor_count=ready_factor_count,
            partial_factor_count=partial_factor_count,
            stale_factor_count=stale_factor_count,
            raw_only_factor_count=raw_only_factor_count,
            missing_reference_1d_factor_count=missing_reference_1d_factor_count,
            missing_reference_5d_factor_count=missing_reference_5d_factor_count,
            coverage_score=coverage_score,
            raw_coverage_score=raw_coverage_score,
            visible_yield_curve_bps=visible_yield_curve_bps,
            raw_yield_curve_bps=raw_yield_curve_bps,
        )
        visible_factor_ids = sorted(
            {
                str(factor["factor_id"])
                for factor in factors
            }
        )
        raw_factor_ids = sorted(
            {
                str(factor["factor_id"])
                for factor in raw_factors
            }
        )
        visible_categories = sorted(
            {
                str(factor["category"])
                for factor in factors
                if str(factor.get("category") or "").strip()
            }
        )
        raw_categories = sorted(
            {
                str(factor["category"])
                for factor in raw_factors
                if str(factor.get("category") or "").strip()
            }
        )

        return {
            "as_of": self._max_iso_timestamp(factors, "observation_time"),
            "raw_as_of": self._max_iso_timestamp(raw_factors, "observation_time"),
            "generated_at": self._max_iso_timestamp(raw_factors, "snapshot_time") or self._utc_now_naive().isoformat(),
            "factor_count": len(factors),
            "raw_factor_count": len(raw_factors),
            "excluded_factor_count": len(raw_factors) - len(factors),
            "ready_factor_count": ready_factor_count,
            "partial_factor_count": partial_factor_count,
            "stale_factor_count": stale_factor_count,
            "raw_only_factor_count": raw_only_factor_count,
            "missing_reference_1d_factor_count": missing_reference_1d_factor_count,
            "missing_reference_5d_factor_count": missing_reference_5d_factor_count,
            "coverage_score": coverage_score,
            "raw_coverage_score": raw_coverage_score,
            "visibility_status": visibility_status,
            "coverage_summary": {
                "requested_factor_ids": sorted({str(item) for item in factor_ids or []}),
                "requested_interval": interval,
                "observed_factor_count": len(visible_factor_ids),
                "raw_observed_factor_count": len(raw_factor_ids),
                "observed_category_count": len(visible_categories),
                "raw_observed_category_count": len(raw_categories),
                "visible_factor_ids": visible_factor_ids,
                "raw_factor_ids": raw_factor_ids,
                "excluded_factor_ids": sorted(set(raw_factor_ids) - set(visible_factor_ids)),
                "missing_reference_1d_factor_ids": sorted(
                    {
                        str(factor["factor_id"])
                        for factor in raw_factors
                        if not factor["reference_1d_available"]
                    }
                ),
                "missing_reference_5d_factor_ids": sorted(
                    {
                        str(factor["factor_id"])
                        for factor in raw_factors
                        if not factor["reference_5d_available"]
                    }
                ),
            },
            "data_quality_flag": data_quality_flag,
            "data_quality_flags": data_quality_flags,
            "quality_notes": quality_notes,
            "cross_asset_context": {
                "yield_curve_2s10s_bps": visible_yield_curve_bps,
                "yield_curve_2s10s_status": self._yield_curve_status(
                    visible_yield_curve_bps,
                    available_leg_count=sum(
                        1
                        for key in ("ust_2y_yield::1d", "ust_10y_yield::1d")
                        if key in visible_by_factor
                    ),
                ),
            },
            "raw_cross_asset_context": {
                "yield_curve_2s10s_bps": raw_yield_curve_bps,
                "yield_curve_2s10s_status": self._yield_curve_status(
                    raw_yield_curve_bps,
                    available_leg_count=sum(
                        1
                        for key in ("ust_2y_yield::1d", "ust_10y_yield::1d")
                        if key in raw_by_factor
                    ),
                ),
            },
            "factors": factors,
            "raw_factors": raw_factors,
        }

    def load_latest_context_bundle(
        self,
        factor_ids: list[str] | None = None,
        interval: str | None = None,
    ) -> dict:
        rows = self.repository.fetch_latest_context_snapshots(
            factor_ids=factor_ids,
            interval=interval,
        )
        snapshots = [
            MacroContextSnapshot(
                factor_id=row["factor_id"],
                name=row["name"],
                category=row["category"],
                factor_type=row["factor_type"],
                interval=row["interval"],
                snapshot_time=self._parse_db_timestamp(row["snapshot_time"]) or self._utc_now_naive(),
                observation_time=self._parse_db_timestamp(row["observation_time"]) or self._utc_now_naive(),
                latest_value=row["latest_value"],
                unit=row["unit"],
                currency=row["currency"],
                quality_flag=row["quality_flag"],
                source_name=row["source_name"],
                source_symbol=row["source_symbol"],
                source_priority=row["source_priority"],
                freshness_seconds=row["freshness_seconds"],
                staleness_ttl_seconds=row["staleness_ttl_seconds"],
                is_stale=bool(row["is_stale"]),
                reference_1d_time=self._parse_db_timestamp(row["reference_1d_time"]),
                reference_1d_value=row["reference_1d_value"],
                change_1d_abs=row["change_1d_abs"],
                change_1d_pct=row["change_1d_pct"],
                change_1d_bps=row["change_1d_bps"],
                reference_5d_time=self._parse_db_timestamp(row["reference_5d_time"]),
                reference_5d_value=row["reference_5d_value"],
                change_5d_abs=row["change_5d_abs"],
                change_5d_pct=row["change_5d_pct"],
                change_5d_bps=row["change_5d_bps"],
                context_completeness_score=row["context_completeness_score"] or 0.0,
                raw_context_json=row["raw_context_json"],
            )
            for row in rows
        ]
        return self.build_context_bundle_from_snapshots(
            snapshots,
            factor_ids=factor_ids,
            interval=interval,
        )

    def close(self):
        self.db.close()
