from datetime import timedelta
from math import log, log1p, sqrt
from statistics import median

from loguru import logger

from config.settings import ALTERNATIVE_CONFIG
from data_layer.alternative_data.base import AlternativeCollectorBase
from data_layer.alternative_data.client import AlternativeDataClient
from data_layer.alternative_data.models import AlternativeTimeSeriesPoint, dump_json, utc_now_naive
from data_layer.alternative_data.sources import load_alternative_factors, load_google_trends_query_groups


class GoogleTrendsCollector(AlternativeCollectorBase):
    """采集 Google Trends query group 搜索热度与相关注意力信号。"""

    ATTENTION_SHOCK_BASELINE_DAYS = 7
    ATTENTION_SHOCK_MIN_BASELINE_OBSERVATIONS = 2
    CROSS_QUERY_MIN_PEERS = 2
    NARRATIVE_BUCKETS = ("speculation", "builder", "institutional", "risk", "other")
    NARRATIVE_PRIORITY = ("risk", "institutional", "builder", "speculation", "other")
    NARRATIVE_KEYWORDS = {
        "speculation": (
            "price",
            "breakout",
            "outlook",
            "prediction",
            "forecast",
            "target",
            "chart",
            "buy",
            "sell",
            "trade",
            "trading",
            "pump",
            "dump",
            "rally",
            "moon",
            "mania",
        ),
        "builder": (
            "network",
            "ecosystem",
            "protocol",
            "developer",
            "development",
            "dev",
            "upgrade",
            "mainnet",
            "testnet",
            "roadmap",
            "staking",
            "validator",
            "rollup",
            "layer 2",
            "l2",
            "bridge",
            "scaling",
        ),
        "institutional": (
            "etf",
            "sec",
            "approval",
            "filing",
            "blackrock",
            "fidelity",
            "regulation",
            "regulatory",
            "policy",
            "bank",
            "banking",
            "treasury",
            "reserve",
            "institution",
        ),
        "risk": (
            "hack",
            "exploit",
            "scam",
            "fraud",
            "lawsuit",
            "ban",
            "crash",
            "collapse",
            "liquidation",
            "insolvency",
            "breach",
            "attack",
            "security",
            "outage",
            "risk",
        ),
    }

    def __init__(self, client: AlternativeDataClient, db):
        super().__init__(db)
        self.client = client

    @staticmethod
    def _build_timeframe(window_days: int) -> str:
        end_date = utc_now_naive().date()
        start_date = end_date - timedelta(days=max(window_days - 1, 0))
        return f"{start_date.isoformat()} {end_date.isoformat()}"

    @staticmethod
    def _build_timeframe_from_dates(start_date, end_date) -> str:
        return f"{start_date.isoformat()} {end_date.isoformat()}"

    @staticmethod
    def _date_key(timestamp) -> str:
        return timestamp.date().isoformat()

    @staticmethod
    def _infer_interval(rows: list[dict]) -> str:
        if len(rows) < 2:
            return "1d"

        timestamps = [
            row["timestamp"]
            for row in rows
            if row.get("timestamp") is not None
        ]
        if len(timestamps) < 2:
            return "1d"

        deltas = [
            int((current - previous).total_seconds())
            for previous, current in zip(timestamps, timestamps[1:])
            if current > previous
        ]
        if not deltas:
            return "1d"

        min_delta = min(deltas)
        if min_delta <= 5400:
            return "1h"
        if min_delta <= 172800:
            return "1d"
        return "1w"

    @staticmethod
    def _mark_latest_quality(
        points: list[AlternativeTimeSeriesPoint],
        staleness_ttl_seconds: int,
    ) -> list[AlternativeTimeSeriesPoint]:
        if not points:
            return points
        points.sort(key=lambda item: item.observation_time)
        latest = points[-1]
        age_seconds = max(
            0.0,
            (utc_now_naive() - latest.observation_time).total_seconds(),
        )
        latest.quality_flag = (
            "stale"
            if age_seconds > staleness_ttl_seconds
            else latest.quality_flag
        )
        return points

    @staticmethod
    def _build_point(
        factor,
        entity_key: str,
        interval: str,
        observation_time,
        value: float,
        quality_flag: str,
        dimensions_json: dict[str, object],
        source_symbol: str,
        raw_payload: dict[str, object],
    ) -> AlternativeTimeSeriesPoint:
        return AlternativeTimeSeriesPoint(
            factor_id=factor.factor_id,
            category=factor.category,
            factor_type=factor.factor_type,
            entity_type=factor.entity_type,
            entity_key=entity_key,
            interval=interval,
            observation_time=observation_time,
            value=float(value),
            unit=factor.unit,
            quality_flag=quality_flag,
            dimensions_json=dimensions_json,
            config_version=factor.config_version,
            source_name=factor.source_name,
            source_symbol=source_symbol,
            raw_payload_json=dump_json(raw_payload),
        )

    @staticmethod
    def _normalize_rows(rows: list[dict]) -> list[dict]:
        normalized_rows: list[dict] = []
        for row in rows:
            timestamp = row.get("timestamp")
            value = row.get("value")
            if timestamp is None or value is None:
                continue
            normalized_rows.append(
                {
                    **row,
                    "timestamp": timestamp,
                    "value": float(value),
                }
            )
        normalized_rows.sort(key=lambda item: item["timestamp"])
        return normalized_rows

    @staticmethod
    def _build_dimensions_json(
        query_group: dict[str, object],
        window_days: int,
    ) -> dict[str, object]:
        return {
            "query": str(query_group["query"]),
            "geo": ALTERNATIVE_CONFIG["google_trends_geo"] or "WORLD",
            "gprop": ALTERNATIVE_CONFIG["google_trends_property"] or "web",
            "category": ALTERNATIVE_CONFIG["google_trends_category"],
            "window_days": window_days,
            "query_group_type": str(query_group["group_type"]),
            "query_version": ALTERNATIVE_CONFIG["google_trends_query_version"],
        }

    @staticmethod
    def _truncate_ranked_entries(entries: list[dict], limit: int) -> list[dict]:
        return [dict(item) for item in entries[:limit]]

    @staticmethod
    def _safe_share(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return float(numerator) / float(denominator)

    @staticmethod
    def _build_day_start(observation_time):
        return observation_time.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    @classmethod
    def _entry_signal_weight(cls, entry: dict[str, object]) -> float:
        value = max(float(entry.get("value") or 0.0), 0.0)
        return log1p(value)

    @classmethod
    def _classify_narrative(cls, entry: dict[str, object]) -> str:
        title = str(entry.get("title") or "").lower()
        topic_type = str(entry.get("topic_type") or "").lower()
        text = f"{title} {topic_type}".strip()
        if not text:
            return "other"

        best_bucket = "other"
        best_score = 0
        best_priority = len(cls.NARRATIVE_PRIORITY)
        for priority, bucket in enumerate(cls.NARRATIVE_PRIORITY):
            keywords = cls.NARRATIVE_KEYWORDS.get(bucket, ())
            score = sum(1 for keyword in keywords if keyword in text)
            if score <= 0:
                continue
            if score > best_score or (score == best_score and priority < best_priority):
                best_bucket = bucket
                best_score = score
                best_priority = priority
        return best_bucket

    @classmethod
    def _combine_related_entries(
        cls,
        query_top: list[dict],
        query_rising: list[dict],
        topic_top: list[dict],
        topic_rising: list[dict],
    ) -> list[dict[str, object]]:
        combined: list[dict[str, object]] = []
        for ranking_type, entries in (
            ("top", query_top),
            ("rising", query_rising),
            ("top", topic_top),
            ("rising", topic_rising),
        ):
            for entry in entries:
                combined.append(
                    {
                        **dict(entry),
                        "ranking_type": ranking_type,
                    }
                )
        return combined

    @classmethod
    def _aggregate_related_narratives(
        cls,
        entries: list[dict[str, object]],
    ) -> dict[str, object]:
        bucket_stats = {
            bucket: {
                "weight": 0.0,
                "item_count": 0,
                "breakout_count": 0,
                "sample_titles": [],
            }
            for bucket in cls.NARRATIVE_BUCKETS
        }
        classified_entries: list[dict[str, object]] = []
        total_weight = 0.0
        for entry in entries:
            narrative = cls._classify_narrative(entry)
            signal_weight = cls._entry_signal_weight(entry)
            bucket_stats[narrative]["weight"] += signal_weight
            bucket_stats[narrative]["item_count"] += 1
            if entry.get("is_breakout"):
                bucket_stats[narrative]["breakout_count"] += 1
            if len(bucket_stats[narrative]["sample_titles"]) < 5:
                bucket_stats[narrative]["sample_titles"].append(str(entry.get("title") or ""))
            total_weight += signal_weight
            classified_entries.append(
                {
                    **dict(entry),
                    "narrative": narrative,
                    "signal_weight": signal_weight,
                }
            )

        shares = {
            bucket: cls._safe_share(stats["weight"], total_weight)
            for bucket, stats in bucket_stats.items()
        }
        dominant_narrative = max(
            cls.NARRATIVE_BUCKETS,
            key=lambda bucket: shares.get(bucket, 0.0),
            default="other",
        )
        active_shares = [
            share
            for share in shares.values()
            if share > 0
        ]
        normalized_entropy = 0.0
        if len(active_shares) > 1:
            entropy = -sum(share * log(share) for share in active_shares)
            normalized_entropy = cls._safe_share(entropy, log(len(active_shares)))
        return {
            "total_weight": total_weight,
            "bucket_stats": bucket_stats,
            "shares": shares,
            "dominant_narrative": dominant_narrative,
            "dominant_share": shares.get(dominant_narrative, 0.0),
            "active_narrative_count": sum(1 for share in active_shares if share > 0),
            "normalized_entropy": normalized_entropy,
            "classified_entries": classified_entries,
        }

    @staticmethod
    def _build_history_segments(
        total_days: int,
        segment_days: int,
        overlap_days: int,
    ) -> list[dict[str, object]]:
        segment_days = max(2, int(segment_days))
        overlap_days = max(0, min(int(overlap_days), segment_days - 1))
        total_days = max(1, int(total_days))

        end_date = utc_now_naive().date()
        start_date = end_date - timedelta(days=max(total_days - 1, 0))
        segments: list[dict[str, object]] = []
        current_end = end_date

        while True:
            current_start = max(
                start_date,
                current_end - timedelta(days=segment_days - 1),
            )
            segments.append(
                {
                    "start_date": current_start,
                    "end_date": current_end,
                    "timeframe": GoogleTrendsCollector._build_timeframe_from_dates(
                        current_start,
                        current_end,
                    ),
                }
            )
            if current_start <= start_date:
                break
            current_end = current_start + timedelta(days=overlap_days - 1)

        return segments

    @classmethod
    def _rescale_history_segment(
        cls,
        anchor_rows: list[dict],
        candidate_rows: list[dict],
    ) -> tuple[list[dict], float, int]:
        anchor_by_date = {
            cls._date_key(row["timestamp"]): row
            for row in anchor_rows
        }
        candidate_by_date = {
            cls._date_key(row["timestamp"]): row
            for row in candidate_rows
        }
        overlap_keys = sorted(set(anchor_by_date).intersection(candidate_by_date))

        ratios = [
            float(anchor_by_date[key]["value"]) / float(candidate_by_date[key]["value"])
            for key in overlap_keys
            if float(anchor_by_date[key]["value"]) > 0 and float(candidate_by_date[key]["value"]) > 0
        ]
        if ratios:
            scale = float(median(ratios))
        else:
            anchor_max = max(
                (float(anchor_by_date[key]["value"]) for key in overlap_keys),
                default=0.0,
            )
            candidate_max = max(
                (float(candidate_by_date[key]["value"]) for key in overlap_keys),
                default=0.0,
            )
            scale = anchor_max / candidate_max if anchor_max > 0 and candidate_max > 0 else 1.0

        scaled_rows = [
            {
                **row,
                "value": float(row["value"]) * scale,
                "rescale_factor": scale,
                "overlap_observation_count": len(overlap_keys),
                "history_mode": "stitched_long_history",
            }
            for row in candidate_rows
        ]
        return scaled_rows, scale, len(overlap_keys)

    def _fetch_interest_rows(
        self,
        query_group: dict[str, object],
        timeframe: str,
    ) -> list[dict]:
        return self.client.fetch_google_trends_interest(
            query=str(query_group["query"]),
            timeframe=timeframe,
            geo=ALTERNATIVE_CONFIG["google_trends_geo"],
            category=ALTERNATIVE_CONFIG["google_trends_category"],
            gprop=ALTERNATIVE_CONFIG["google_trends_property"],
            hl=ALTERNATIVE_CONFIG["google_trends_hl"],
            tz=ALTERNATIVE_CONFIG["google_trends_tz"],
        )

    def _fetch_bootstrap_history_rows(
        self,
        query_group: dict[str, object],
    ) -> list[dict]:
        total_days = max(
            ALTERNATIVE_CONFIG["google_trends_window_days"],
            ALTERNATIVE_CONFIG["google_trends_bootstrap_history_days"],
        )
        segment_days = max(2, ALTERNATIVE_CONFIG["google_trends_history_segment_days"])
        overlap_days = max(0, ALTERNATIVE_CONFIG["google_trends_history_overlap_days"])
        segments = self._build_history_segments(
            total_days=total_days,
            segment_days=segment_days,
            overlap_days=overlap_days,
        )
        stitched_rows: list[dict] = []

        for segment_index, segment in enumerate(segments):
            rows = self._normalize_rows(
                self._fetch_interest_rows(
                    query_group=query_group,
                    timeframe=str(segment["timeframe"]),
                )
            )
            if not rows:
                continue

            rows_with_meta = [
                {
                    **row,
                    "history_mode": "stitched_long_history",
                    "history_depth_days": total_days,
                    "segment_index": segment_index,
                    "segment_start": segment["start_date"].isoformat(),
                    "segment_end": segment["end_date"].isoformat(),
                    "timeframe": str(segment["timeframe"]),
                    "rescale_factor": 1.0,
                    "overlap_observation_count": 0,
                }
                for row in rows
            ]

            if not stitched_rows:
                stitched_rows = rows_with_meta
                continue

            scaled_rows, scale, overlap_count = self._rescale_history_segment(
                anchor_rows=stitched_rows,
                candidate_rows=rows_with_meta,
            )
            logger.info(
                f"Google Trends 长历史分段拼接 "
                f"[{query_group['entity_key']}] "
                f"segment={segment['start_date']}~{segment['end_date']} "
                f"scale={scale:.6f} overlap={overlap_count}"
            )
            stitched_by_date = {
                self._date_key(row["timestamp"]): row
                for row in stitched_rows
            }
            for row in scaled_rows:
                row_date = self._date_key(row["timestamp"])
                if row_date in stitched_by_date:
                    continue
                stitched_by_date[row_date] = row
            stitched_rows = sorted(
                stitched_by_date.values(),
                key=lambda item: item["timestamp"],
            )

        return stitched_rows

    @classmethod
    def _build_attention_shock_points(
        cls,
        factor,
        query_group: dict[str, object],
        rows: list[dict],
        interval: str,
        dimensions_json: dict[str, object],
        source_symbol: str,
        timeframe: str,
    ) -> list[AlternativeTimeSeriesPoint]:
        points: list[AlternativeTimeSeriesPoint] = []
        shock_dimensions = {
            **dimensions_json,
            "baseline_days": cls.ATTENTION_SHOCK_BASELINE_DAYS,
            "shock_formula": "relative_delta_from_trailing_mean",
        }
        baseline_window = timedelta(days=cls.ATTENTION_SHOCK_BASELINE_DAYS)

        for index, row in enumerate(rows):
            observation_time = row["timestamp"]
            baseline_rows = [
                candidate
                for candidate in rows[:index]
                if observation_time - candidate["timestamp"] <= baseline_window
            ]
            if len(baseline_rows) < cls.ATTENTION_SHOCK_MIN_BASELINE_OBSERVATIONS:
                continue

            baseline_values = [
                float(candidate["value"])
                for candidate in baseline_rows
            ]
            baseline_mean = sum(baseline_values) / len(baseline_values)
            shock_value = (
                (float(row["value"]) - baseline_mean)
                / max(abs(baseline_mean), 1.0)
            )
            points.append(
                cls._build_point(
                    factor=factor,
                    entity_key=str(query_group["entity_key"]),
                    interval=interval,
                    observation_time=observation_time,
                    value=shock_value,
                    quality_flag="partial" if row.get("is_partial") else "ok",
                    dimensions_json=shock_dimensions,
                    source_symbol=source_symbol,
                    raw_payload={
                        "metric": factor.factor_id,
                        "query_group": query_group["name"],
                        "query_group_type": query_group["group_type"],
                        "query": query_group["query"],
                        "timeframe": timeframe,
                        "formatted_time": row.get("formatted_time"),
                        "has_data": row.get("has_data"),
                        "is_partial": row.get("is_partial"),
                        "window_days": dimensions_json["window_days"],
                        "baseline_days": cls.ATTENTION_SHOCK_BASELINE_DAYS,
                        "baseline_observation_count": len(baseline_values),
                        "baseline_mean": baseline_mean,
                        "current_value": float(row["value"]),
                        "shock_formula": "relative_delta_from_trailing_mean",
                        "history_mode": row.get("history_mode"),
                        "history_depth_days": row.get("history_depth_days"),
                        "rescale_factor": row.get("rescale_factor"),
                        "segment_start": row.get("segment_start"),
                        "segment_end": row.get("segment_end"),
                        "value": shock_value,
                    },
                )
            )

        return cls._mark_latest_quality(points, factor.staleness_ttl_seconds)

    def _build_series_points_for_group(
        self,
        factor_map: dict[str, object],
        query_group: dict[str, object],
        rows: list[dict],
        window_days: int,
        timeframe: str,
    ) -> list[AlternativeTimeSeriesPoint]:
        normalized_rows = self._normalize_rows(rows)
        if not normalized_rows:
            return []

        interval = self._infer_interval(normalized_rows)
        dimensions_json = self._build_dimensions_json(
            query_group=query_group,
            window_days=window_days,
        )
        source_symbol = str(query_group["query"])
        search_interest_points: list[AlternativeTimeSeriesPoint] = []

        for row in normalized_rows:
            search_interest_points.append(
                self._build_point(
                    factor=factor_map["google_trends_search_interest"],
                    entity_key=str(query_group["entity_key"]),
                    interval=interval,
                    observation_time=row["timestamp"],
                    value=float(row["value"]),
                    quality_flag="partial" if row.get("is_partial") else "ok",
                    dimensions_json=dimensions_json,
                    source_symbol=source_symbol,
                    raw_payload={
                        "metric": "google_trends_search_interest",
                        "query_group": query_group["name"],
                        "query_group_type": query_group["group_type"],
                        "query": query_group["query"],
                        "timeframe": timeframe,
                        "formatted_time": row.get("formatted_time"),
                        "has_data": row.get("has_data"),
                        "is_partial": row.get("is_partial"),
                        "window_days": window_days,
                        "history_mode": row.get("history_mode"),
                        "history_depth_days": row.get("history_depth_days"),
                        "rescale_factor": row.get("rescale_factor"),
                        "segment_start": row.get("segment_start"),
                        "segment_end": row.get("segment_end"),
                        "overlap_observation_count": row.get("overlap_observation_count"),
                        "value": row["value"],
                    },
                )
            )

        attention_shock_points = self._build_attention_shock_points(
            factor=factor_map["google_trends_attention_shock_7d"],
            query_group=query_group,
            rows=normalized_rows,
            interval=interval,
            dimensions_json=dimensions_json,
            source_symbol=source_symbol,
            timeframe=timeframe,
        )
        return [
            *self._mark_latest_quality(
                search_interest_points,
                factor_map["google_trends_search_interest"].staleness_ttl_seconds,
            ),
            *attention_shock_points,
        ]

    def _build_related_points_for_group(
        self,
        factor_map: dict[str, object],
        query_group: dict[str, object],
        observation_time,
        window_days: int,
        timeframe: str,
    ) -> list[AlternativeTimeSeriesPoint]:
        dimensions_json = {
            **self._build_dimensions_json(
                query_group=query_group,
                window_days=window_days,
            ),
            "related_limit": ALTERNATIVE_CONFIG["google_trends_related_limit"],
        }
        source_symbol = str(query_group["query"])
        limit = max(1, ALTERNATIVE_CONFIG["google_trends_related_limit"])
        query_related = self.client.fetch_google_trends_related_queries(
            query=str(query_group["query"]),
            timeframe=timeframe,
            geo=ALTERNATIVE_CONFIG["google_trends_geo"],
            category=ALTERNATIVE_CONFIG["google_trends_category"],
            gprop=ALTERNATIVE_CONFIG["google_trends_property"],
            hl=ALTERNATIVE_CONFIG["google_trends_hl"],
            tz=ALTERNATIVE_CONFIG["google_trends_tz"],
        )
        topic_related = self.client.fetch_google_trends_related_topics(
            query=str(query_group["query"]),
            timeframe=timeframe,
            geo=ALTERNATIVE_CONFIG["google_trends_geo"],
            category=ALTERNATIVE_CONFIG["google_trends_category"],
            gprop=ALTERNATIVE_CONFIG["google_trends_property"],
            hl=ALTERNATIVE_CONFIG["google_trends_hl"],
            tz=ALTERNATIVE_CONFIG["google_trends_tz"],
        )

        query_top = self._truncate_ranked_entries(query_related.get("top", []), limit)
        query_rising = self._truncate_ranked_entries(query_related.get("rising", []), limit)
        topic_top = self._truncate_ranked_entries(topic_related.get("top", []), limit)
        topic_rising = self._truncate_ranked_entries(topic_related.get("rising", []), limit)
        combined_entries = self._combine_related_entries(
            query_top=query_top,
            query_rising=query_rising,
            topic_top=topic_top,
            topic_rising=topic_rising,
        )
        narrative_summary = self._aggregate_related_narratives(combined_entries)

        query_breakout_count = float(sum(1 for item in query_rising if item.get("is_breakout")))
        query_rising_max_score = max(
            (float(item.get("value") or 0.0) for item in query_rising),
            default=0.0,
        )
        topic_breakout_count = float(sum(1 for item in topic_rising if item.get("is_breakout")))
        topic_rising_max_score = max(
            (float(item.get("value") or 0.0) for item in topic_rising),
            default=0.0,
        )

        common_payload = {
            "query_group": query_group["name"],
            "query_group_type": query_group["group_type"],
            "query": query_group["query"],
            "timeframe": timeframe,
            "window_days": window_days,
            "related_limit": limit,
            "narrative_summary": {
                "dominant_narrative": narrative_summary["dominant_narrative"],
                "dominant_share": narrative_summary["dominant_share"],
                "active_narrative_count": narrative_summary["active_narrative_count"],
                "normalized_entropy": narrative_summary["normalized_entropy"],
                "shares": narrative_summary["shares"],
                "bucket_stats": narrative_summary["bucket_stats"],
            },
            "classified_entries": narrative_summary["classified_entries"],
        }
        return [
            self._build_point(
                factor=factor_map["google_trends_related_query_breakout_count"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=query_breakout_count,
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_related_query_breakout_count",
                    "top_entries": query_top,
                    "rising_entries": query_rising,
                    "value": query_breakout_count,
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_related_query_rising_max_score"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=query_rising_max_score,
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_related_query_rising_max_score",
                    "top_entries": query_top,
                    "rising_entries": query_rising,
                    "value": query_rising_max_score,
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_related_topic_breakout_count"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=topic_breakout_count,
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_related_topic_breakout_count",
                    "top_entries": topic_top,
                    "rising_entries": topic_rising,
                    "value": topic_breakout_count,
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_related_topic_rising_max_score"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=topic_rising_max_score,
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_related_topic_rising_max_score",
                    "top_entries": topic_top,
                    "rising_entries": topic_rising,
                    "value": topic_rising_max_score,
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_narrative_concentration"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=float(narrative_summary["dominant_share"]),
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_narrative_concentration",
                    "top_entries": query_top + topic_top,
                    "rising_entries": query_rising + topic_rising,
                    "value": float(narrative_summary["dominant_share"]),
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_narrative_speculation_share"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=float(narrative_summary["shares"].get("speculation", 0.0)),
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_narrative_speculation_share",
                    "top_entries": query_top + topic_top,
                    "rising_entries": query_rising + topic_rising,
                    "value": float(narrative_summary["shares"].get("speculation", 0.0)),
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_narrative_builder_share"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=float(narrative_summary["shares"].get("builder", 0.0)),
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_narrative_builder_share",
                    "top_entries": query_top + topic_top,
                    "rising_entries": query_rising + topic_rising,
                    "value": float(narrative_summary["shares"].get("builder", 0.0)),
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_narrative_institutional_share"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=float(narrative_summary["shares"].get("institutional", 0.0)),
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_narrative_institutional_share",
                    "top_entries": query_top + topic_top,
                    "rising_entries": query_rising + topic_rising,
                    "value": float(narrative_summary["shares"].get("institutional", 0.0)),
                },
            ),
            self._build_point(
                factor=factor_map["google_trends_narrative_risk_share"],
                entity_key=str(query_group["entity_key"]),
                interval="1d",
                observation_time=observation_time,
                value=float(narrative_summary["shares"].get("risk", 0.0)),
                quality_flag="ok",
                dimensions_json=dimensions_json,
                source_symbol=source_symbol,
                raw_payload={
                    **common_payload,
                    "metric": "google_trends_narrative_risk_share",
                    "top_entries": query_top + topic_top,
                    "rising_entries": query_rising + topic_rising,
                    "value": float(narrative_summary["shares"].get("risk", 0.0)),
                },
            ),
        ]

    def _build_cross_query_points(
        self,
        factor_map: dict[str, object],
        query_group_rows: list[dict[str, object]],
        window_days: int,
        timeframe: str,
    ) -> list[AlternativeTimeSeriesPoint]:
        if len(query_group_rows) < self.CROSS_QUERY_MIN_PEERS:
            return []

        peer_set = sorted(
            str(item["query_group"]["entity_key"])
            for item in query_group_rows
        )
        observations_by_date: dict[str, list[dict[str, object]]] = {}
        for item in query_group_rows:
            query_group = item["query_group"]
            source_symbol = str(query_group["query"])
            interval = str(item["interval"])
            dimensions_json = {
                **self._build_dimensions_json(
                    query_group=query_group,
                    window_days=window_days,
                ),
                "cross_query_peer_count": len(peer_set),
                "cross_query_peer_set": ",".join(peer_set),
            }
            for row in item["rows"]:
                observation_date = self._date_key(row["timestamp"])
                observations_by_date.setdefault(observation_date, []).append(
                    {
                        "entity_key": str(query_group["entity_key"]),
                        "query_group": query_group,
                        "row": row,
                        "interval": interval,
                        "source_symbol": source_symbol,
                        "dimensions_json": dimensions_json,
                    }
                )

        points: list[AlternativeTimeSeriesPoint] = []
        for observation_date, peer_rows in observations_by_date.items():
            if len(peer_rows) < self.CROSS_QUERY_MIN_PEERS:
                continue
            values = [
                float(item["row"]["value"])
                for item in peer_rows
            ]
            mean_value = sum(values) / len(values)
            variance = sum((value - mean_value) ** 2 for value in values) / len(values)
            std_value = sqrt(variance)
            peer_values = {
                item["entity_key"]: float(item["row"]["value"])
                for item in sorted(peer_rows, key=lambda row: row["entity_key"])
            }
            peer_count = len(peer_rows)
            for item in peer_rows:
                current_value = float(item["row"]["value"])
                smaller_count = sum(1 for value in values if value < current_value)
                equal_count = sum(1 for value in values if value == current_value)
                average_rank = smaller_count + ((equal_count + 1) / 2)
                percentile = self._safe_share(average_rank - 1, peer_count - 1)
                zscore = 0.0 if std_value <= 0 else (current_value - mean_value) / std_value
                rank_desc = 1 + sum(1 for value in values if value > current_value)
                common_payload = {
                    "query_group": item["query_group"]["name"],
                    "query_group_type": item["query_group"]["group_type"],
                    "query": item["query_group"]["query"],
                    "timeframe": timeframe,
                    "window_days": window_days,
                    "observation_date": observation_date,
                    "peer_count": peer_count,
                    "peer_set": peer_set,
                    "peer_values": peer_values,
                    "mean_value": mean_value,
                    "std_value": std_value,
                    "rank_desc": rank_desc,
                    "percentile": percentile,
                    "value": current_value,
                    "formatted_time": item["row"].get("formatted_time"),
                    "history_mode": item["row"].get("history_mode"),
                    "history_depth_days": item["row"].get("history_depth_days"),
                }
                points.append(
                    self._build_point(
                        factor=factor_map["google_trends_cross_query_zscore"],
                        entity_key=item["entity_key"],
                        interval=item["interval"],
                        observation_time=item["row"]["timestamp"],
                        value=zscore,
                        quality_flag="partial" if item["row"].get("is_partial") else "ok",
                        dimensions_json=item["dimensions_json"],
                        source_symbol=item["source_symbol"],
                        raw_payload={
                            **common_payload,
                            "metric": "google_trends_cross_query_zscore",
                            "value": zscore,
                        },
                    )
                )
                points.append(
                    self._build_point(
                        factor=factor_map["google_trends_cross_query_percentile"],
                        entity_key=item["entity_key"],
                        interval=item["interval"],
                        observation_time=item["row"]["timestamp"],
                        value=percentile,
                        quality_flag="partial" if item["row"].get("is_partial") else "ok",
                        dimensions_json=item["dimensions_json"],
                        source_symbol=item["source_symbol"],
                        raw_payload={
                            **common_payload,
                            "metric": "google_trends_cross_query_percentile",
                            "value": percentile,
                        },
                    )
                )

        return points

    def fetch_recent_points(
        self,
        entity_keys: list[str] | None = None,
        window_days: int | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        factor_map = {
            factor.factor_id: factor
            for factor in load_alternative_factors(source_names=["google_trends"])
        }
        query_groups = load_google_trends_query_groups(entity_keys=entity_keys)
        if not query_groups:
            return []

        window_days = max(
            1,
            int(window_days or ALTERNATIVE_CONFIG["google_trends_window_days"]),
        )
        timeframe = self._build_timeframe(window_days)
        results: list[AlternativeTimeSeriesPoint] = []
        query_group_rows: list[dict[str, object]] = []

        for query_group in query_groups:
            try:
                rows = self._fetch_interest_rows(
                    query_group=query_group,
                    timeframe=timeframe,
                )
            except Exception as exc:
                logger.warning(
                    f"Google Trends query group 采集失败 "
                    f"[{query_group['entity_key']}] [{query_group['query']}]: {exc}"
                )
                continue

            normalized_rows = self._normalize_rows(rows)
            if not normalized_rows:
                logger.warning(
                    f"Google Trends query group 返回空结果 "
                    f"[{query_group['entity_key']}] [{query_group['query']}]"
                )
                continue
            query_group_rows.append(
                {
                    "query_group": query_group,
                    "rows": normalized_rows,
                    "interval": self._infer_interval(normalized_rows),
                }
            )

            results.extend(
                self._build_series_points_for_group(
                    factor_map=factor_map,
                    query_group=query_group,
                    rows=normalized_rows,
                    window_days=window_days,
                    timeframe=timeframe,
                )
            )
            try:
                results.extend(
                    self._build_related_points_for_group(
                        factor_map=factor_map,
                        query_group=query_group,
                        observation_time=normalized_rows[-1]["timestamp"],
                        window_days=window_days,
                        timeframe=timeframe,
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"Google Trends related signals 采集失败 "
                    f"[{query_group['entity_key']}] [{query_group['query']}]: {exc}"
                )

        results.extend(
            self._build_cross_query_points(
                factor_map=factor_map,
                query_group_rows=query_group_rows,
                window_days=window_days,
                timeframe=timeframe,
            )
        )
        return results

    def bootstrap_history(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        factor_map = {
            factor.factor_id: factor
            for factor in load_alternative_factors(source_names=["google_trends"])
        }
        query_groups = load_google_trends_query_groups(entity_keys=entity_keys)
        if not query_groups:
            return []

        recent_window_days = max(1, ALTERNATIVE_CONFIG["google_trends_window_days"])
        recent_timeframe = self._build_timeframe(recent_window_days)
        results: list[AlternativeTimeSeriesPoint] = []
        query_group_rows: list[dict[str, object]] = []

        for query_group in query_groups:
            try:
                stitched_rows = self._fetch_bootstrap_history_rows(query_group=query_group)
            except Exception as exc:
                logger.warning(
                    f"Google Trends 长历史 bootstrap 失败 "
                    f"[{query_group['entity_key']}] [{query_group['query']}]: {exc}"
                )
                continue

            normalized_rows = self._normalize_rows(stitched_rows)
            if not normalized_rows:
                continue
            query_group_rows.append(
                {
                    "query_group": query_group,
                    "rows": normalized_rows,
                    "interval": self._infer_interval(normalized_rows),
                }
            )

            results.extend(
                self._build_series_points_for_group(
                    factor_map=factor_map,
                    query_group=query_group,
                    rows=normalized_rows,
                    window_days=recent_window_days,
                    timeframe=recent_timeframe,
                )
            )
            try:
                results.extend(
                    self._build_related_points_for_group(
                        factor_map=factor_map,
                        query_group=query_group,
                        observation_time=normalized_rows[-1]["timestamp"],
                        window_days=recent_window_days,
                        timeframe=recent_timeframe,
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"Google Trends related signals bootstrap 失败 "
                    f"[{query_group['entity_key']}] [{query_group['query']}]: {exc}"
                )

        results.extend(
            self._build_cross_query_points(
                factor_map=factor_map,
                query_group_rows=query_group_rows,
                window_days=recent_window_days,
                timeframe=recent_timeframe,
            )
        )
        return results

    def collect(
        self,
        entity_keys: list[str] | None = None,
    ) -> list[AlternativeTimeSeriesPoint]:
        logger.info("开始采集 Google Trends 搜索热度与相关注意力信号...")
        points = self.fetch_recent_points(entity_keys=entity_keys)
        if points:
            self.save_to_db(points)
        logger.info(f"Google Trends 搜索热度与相关注意力信号采集完成，共 {len(points)} 条")
        return points
