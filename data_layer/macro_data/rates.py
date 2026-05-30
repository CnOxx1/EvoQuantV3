import json
import uuid
from datetime import datetime, timedelta

from loguru import logger

from config.settings import MACRO_CONFIG
from database.db_manager import DBManager
from data_layer.macro_data.client import MacroDataClient
from data_layer.macro_data.models import MacroFactorDefinition, MacroTimeSeriesPoint, utc_now_naive
from data_layer.macro_data.sources import load_macro_factors


class MacroRateCollector:
    """采集利率与政策利率等 macro_level 型因子。"""

    BOOTSTRAP_WINDOW_DAYS = 365

    def __init__(self, client: MacroDataClient, db: DBManager):
        self.client = client
        self.db = db

    @staticmethod
    def _point_rank(point: MacroTimeSeriesPoint) -> tuple:
        return (
            1 if point.source_priority == "primary" else 0,
            1 if point.quality_flag == "ok" else 0,
            point.collected_at,
        )

    def _select_factors(self, factor_ids: list[str] | None = None) -> list[MacroFactorDefinition]:
        return load_macro_factors(
            factor_type="macro_level",
            factor_ids=factor_ids,
        )

    @staticmethod
    def _mark_latest_quality(
        points: list[MacroTimeSeriesPoint],
        factor: MacroFactorDefinition,
    ) -> list[MacroTimeSeriesPoint]:
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
            if age_seconds > factor.staleness_ttl_seconds
            else latest.quality_flag
        )
        return points

    def fetch_factor_history(
        self,
        factor: MacroFactorDefinition,
        lookback_days: int,
        ingest_run_id: str,
    ) -> list[MacroTimeSeriesPoint]:
        start_at = utc_now_naive() - timedelta(days=max(lookback_days, 1))
        results = self._fetch_factor_window(
            factor=factor,
            start_at=start_at,
            end_at=utc_now_naive(),
            ingest_run_id=ingest_run_id,
        )
        results = self._mark_latest_quality(results, factor)
        logger.info(f"宏观利率获取完成 [{factor.factor_id}] {len(results)} 条")
        return results

    def _fetch_factor_window(
        self,
        factor: MacroFactorDefinition,
        start_at: datetime,
        end_at: datetime,
        ingest_run_id: str,
    ) -> list[MacroTimeSeriesPoint]:
        rows = self.client.fetch_fred_series(
            series_id=factor.source_symbol,
            start_date=start_at,
            end_date=end_at,
        )
        results: list[MacroTimeSeriesPoint] = []
        for row in rows:
            date_text = (
                row.get("observation_date")
                or row.get("DATE")
                or row.get("date")
                or ""
            ).strip()
            value_text = (row.get(factor.source_symbol) or "").strip()
            if not date_text or not value_text or value_text == ".":
                continue
            try:
                observation_time = datetime.fromisoformat(f"{date_text}T00:00:00")
                value = float(value_text)
            except ValueError:
                logger.debug(
                    f"跳过无法解析的宏观利率行 [{factor.factor_id}] {row}"
                )
                continue

            results.append(
                MacroTimeSeriesPoint(
                    factor_id=factor.factor_id,
                    category=factor.category,
                    factor_type=factor.factor_type,
                    interval="1d",
                    observation_time=observation_time,
                    value=value,
                    unit=factor.unit,
                    currency=factor.currency,
                    source_name=factor.source_name,
                    source_symbol=factor.source_symbol,
                    source_priority=factor.source_priority,
                    available_at=observation_time,
                    quality_flag="ok",
                    is_market_open=None,
                    ingest_run_id=ingest_run_id,
                    raw_payload_json=json.dumps(
                        row,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            )

        return results

    @classmethod
    def _iter_bootstrap_windows(
        cls,
        *,
        start_at: datetime,
        end_at: datetime,
    ):
        current_start = start_at
        while current_start <= end_at:
            current_end = min(
                current_start + timedelta(days=cls.BOOTSTRAP_WINDOW_DAYS - 1),
                end_at,
            )
            yield current_start, current_end
            current_start = current_end + timedelta(days=1)

    def fetch_recent_points(
        self,
        factor_ids: list[str] | None = None,
        continue_on_error: bool = False,
    ) -> list[MacroTimeSeriesPoint]:
        factors = self._select_factors(factor_ids)
        ingest_run_id = str(uuid.uuid4())
        results: list[MacroTimeSeriesPoint] = []
        for factor in factors:
            try:
                results.extend(
                    self.fetch_factor_history(
                        factor=factor,
                        lookback_days=MACRO_CONFIG["recent_rate_lookback_days"],
                        ingest_run_id=ingest_run_id,
                    )
                )
            except Exception as exc:
                if not continue_on_error:
                    raise
                logger.error(
                    "宏观利率最新采集失败 "
                    f"[{factor.factor_id}] "
                    f"{type(exc).__name__}: {exc}"
                )
        return results

    def bootstrap_history(
        self,
        factor_ids: list[str] | None = None,
        daily_history_years: int | None = None,
        continue_on_error: bool = False,
    ) -> list[MacroTimeSeriesPoint]:
        factors = self._select_factors(factor_ids)
        ingest_run_id = str(uuid.uuid4())
        lookback_days = (daily_history_years or MACRO_CONFIG["bootstrap_daily_history_years"]) * 365
        results: list[MacroTimeSeriesPoint] = []
        end_at = utc_now_naive()
        start_at = end_at - timedelta(days=max(lookback_days, 1))
        for factor in factors:
            factor_points: list[MacroTimeSeriesPoint] = []
            for window_start, window_end in self._iter_bootstrap_windows(
                start_at=start_at,
                end_at=end_at,
            ):
                try:
                    factor_points.extend(
                        self._fetch_factor_window(
                            factor=factor,
                            start_at=window_start,
                            end_at=window_end,
                            ingest_run_id=ingest_run_id,
                        )
                    )
                except Exception as exc:
                    if not continue_on_error:
                        raise
                    logger.error(
                        "宏观利率历史回填失败 "
                        f"[{factor.factor_id}] [{window_start.date()} -> {window_end.date()}] "
                        f"{type(exc).__name__}: {exc}"
                    )
            factor_points = self._mark_latest_quality(factor_points, factor)
            logger.info(
                f"宏观利率历史回填完成 [{factor.factor_id}] {len(factor_points)} 条"
            )
            results.extend(factor_points)
        return results

    def _deduplicate_points(
        self,
        points: list[MacroTimeSeriesPoint],
    ) -> list[MacroTimeSeriesPoint]:
        deduped: dict[tuple[str, str, datetime], MacroTimeSeriesPoint] = {}
        for point in points:
            key = (point.factor_id, point.interval, point.observation_time)
            previous = deduped.get(key)
            if previous is None or self._point_rank(point) >= self._point_rank(previous):
                deduped[key] = point
        return list(deduped.values())

    def save_to_db(self, points: list[MacroTimeSeriesPoint]):
        points = self._deduplicate_points(points)
        if not points:
            logger.warning("没有可保存的宏观利率数据")
            return

        history_sql = """
            INSERT INTO macro_timeseries (
                factor_id, category, factor_type, interval, observation_time,
                session_date, value, open, high, low, close, volume, unit,
                currency, source_name, source_symbol, source_priority,
                available_at, is_revision, revision_seq, quality_flag,
                is_market_open, ingest_run_id, collected_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_id, interval, observation_time) DO UPDATE SET
                category=excluded.category,
                factor_type=excluded.factor_type,
                session_date=excluded.session_date,
                value=excluded.value,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                unit=excluded.unit,
                currency=excluded.currency,
                source_name=excluded.source_name,
                source_symbol=excluded.source_symbol,
                source_priority=excluded.source_priority,
                available_at=excluded.available_at,
                is_revision=excluded.is_revision,
                revision_seq=excluded.revision_seq,
                quality_flag=excluded.quality_flag,
                is_market_open=excluded.is_market_open,
                ingest_run_id=excluded.ingest_run_id,
                collected_at=excluded.collected_at,
                raw_payload_json=excluded.raw_payload_json
        """
        latest_sql = """
            INSERT INTO latest_macro_timeseries (
                factor_id, factor_type, interval, observation_time, value,
                open, high, low, close, unit, currency, source_name,
                source_symbol, source_priority, quality_flag, is_market_open,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_id, interval) DO UPDATE SET
                factor_type=excluded.factor_type,
                observation_time=excluded.observation_time,
                value=excluded.value,
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                unit=excluded.unit,
                currency=excluded.currency,
                source_name=excluded.source_name,
                source_symbol=excluded.source_symbol,
                source_priority=excluded.source_priority,
                quality_flag=excluded.quality_flag,
                is_market_open=excluded.is_market_open,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.observation_time >= latest_macro_timeseries.observation_time
        """
        history_params = [point.history_db_tuple() for point in points]
        latest_points = self._deduplicate_points(
            sorted(points, key=lambda item: item.observation_time)
        )
        latest_params = [point.latest_db_tuple() for point in latest_points]

        self.db.execute_many(history_sql, history_params)
        self.db.execute_many(latest_sql, latest_params)
        self.db.commit()
        logger.info(f"已保存 {len(points)} 条宏观利率数据")

    def collect(
        self,
        factor_ids: list[str] | None = None,
        continue_on_error: bool = False,
    ):
        logger.info("开始采集宏观利率因子...")
        points = self.fetch_recent_points(
            factor_ids=factor_ids,
            continue_on_error=continue_on_error,
        )
        if points:
            self.save_to_db(points)
        logger.info("宏观利率因子采集完成")
        return points
