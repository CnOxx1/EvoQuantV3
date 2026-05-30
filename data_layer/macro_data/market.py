import json
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger

from config.settings import MACRO_CONFIG
from database.db_manager import DBManager
from data_layer.macro_data.client import MacroDataClient
from data_layer.macro_data.models import MacroFactorDefinition, MacroTimeSeriesPoint, utc_now_naive
from data_layer.macro_data.sources import load_macro_factors


class MacroMarketCollector:
    """采集美元指数、纳指、黄金等 market_price 型宏观因子。"""

    INTERVAL_REQUEST_MAP = {
        "1h": "60m",
        "1d": "1d",
    }

    def __init__(self, client: MacroDataClient, db: DBManager):
        self.client = client
        self.db = db

    @staticmethod
    def _bool_to_int(value: bool | None) -> int | None:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _point_rank(point: MacroTimeSeriesPoint) -> tuple:
        return (
            1 if point.source_priority == "primary" else 0,
            1 if point.quality_flag == "ok" else 0,
            point.collected_at,
        )

    def _select_factors(self, factor_ids: list[str] | None = None) -> list[MacroFactorDefinition]:
        return load_macro_factors(
            factor_type="market_price",
            factor_ids=factor_ids,
        )

    @staticmethod
    def _intervals_for_factor(
        factor: MacroFactorDefinition,
        intervals: list[str] | None = None,
    ) -> list[str]:
        if intervals is None:
            return list(factor.supported_intervals)
        requested = {interval.strip() for interval in intervals if interval.strip()}
        return [
            interval
            for interval in factor.supported_intervals
            if interval in requested
        ]

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

    def _normalize_chart_result(
        self,
        factor: MacroFactorDefinition,
        interval: str,
        payload: dict,
        ingest_run_id: str,
    ) -> list[MacroTimeSeriesPoint]:
        result = ((payload.get("chart") or {}).get("result") or [])
        if not result:
            error_payload = (payload.get("chart") or {}).get("error")
            if error_payload:
                logger.warning(
                    f"宏观行情返回空结果 [{factor.factor_id}] error={error_payload}"
                )
            return []

        first = result[0]
        timestamps = first.get("timestamp") or []
        quotes = ((first.get("indicators") or {}).get("quote") or [])
        if not timestamps or not quotes:
            logger.warning(f"宏观行情缺少有效 bar [{factor.factor_id}] [{interval}]")
            return []

        quote = quotes[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        points: list[MacroTimeSeriesPoint] = []
        for index, timestamp in enumerate(timestamps):
            close = self._safe_float(closes[index] if index < len(closes) else None)
            if close is None:
                continue

            point = MacroTimeSeriesPoint(
                factor_id=factor.factor_id,
                category=factor.category,
                factor_type=factor.factor_type,
                interval=interval,
                observation_time=datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).replace(tzinfo=None),
                value=close,
                open=self._safe_float(opens[index] if index < len(opens) else None),
                high=self._safe_float(highs[index] if index < len(highs) else None),
                low=self._safe_float(lows[index] if index < len(lows) else None),
                close=close,
                volume=self._safe_float(volumes[index] if index < len(volumes) else None),
                unit=factor.unit,
                currency=factor.currency,
                source_name=factor.source_name,
                source_symbol=factor.source_symbol,
                source_priority=factor.source_priority,
                available_at=datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).replace(tzinfo=None),
                quality_flag="ok",
                is_market_open=None,
                ingest_run_id=ingest_run_id,
                raw_payload_json=json.dumps(
                    {
                        "timestamp": timestamp,
                        "open": opens[index] if index < len(opens) else None,
                        "high": highs[index] if index < len(highs) else None,
                        "low": lows[index] if index < len(lows) else None,
                        "close": closes[index] if index < len(closes) else None,
                        "volume": volumes[index] if index < len(volumes) else None,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            points.append(point)

        return self._mark_latest_quality(points, factor)

    def fetch_factor_history(
        self,
        factor: MacroFactorDefinition,
        interval: str,
        lookback_days: int,
        ingest_run_id: str,
    ) -> list[MacroTimeSeriesPoint]:
        request_interval = self.INTERVAL_REQUEST_MAP.get(interval)
        if request_interval is None:
            logger.warning(f"不支持的宏观行情频率 [{factor.factor_id}] {interval}")
            return []

        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(days=max(lookback_days, 1))
        payload = self.client.fetch_yahoo_chart(
            symbol=factor.source_symbol,
            interval=request_interval,
            start_at=start_at,
            end_at=end_at,
        )
        points = self._normalize_chart_result(
            factor=factor,
            interval=interval,
            payload=payload,
            ingest_run_id=ingest_run_id,
        )
        logger.info(
            f"宏观行情获取完成 [{factor.factor_id}] [{interval}] {len(points)} 条"
        )
        return points

    def fetch_recent_points(
        self,
        factor_ids: list[str] | None = None,
        intervals: list[str] | None = None,
    ) -> list[MacroTimeSeriesPoint]:
        factors = self._select_factors(factor_ids)
        ingest_run_id = str(uuid.uuid4())
        results: list[MacroTimeSeriesPoint] = []
        for factor in factors:
            for interval in self._intervals_for_factor(factor, intervals):
                lookback_days = (
                    MACRO_CONFIG["recent_market_lookback_days"]
                    if interval == "1h"
                    else 30
                )
                results.extend(
                    self.fetch_factor_history(
                        factor=factor,
                        interval=interval,
                        lookback_days=lookback_days,
                        ingest_run_id=ingest_run_id,
                    )
                )
        return results

    def bootstrap_history(
        self,
        factor_ids: list[str] | None = None,
        market_history_days: int | None = None,
        daily_history_years: int | None = None,
        continue_on_error: bool = False,
    ) -> list[MacroTimeSeriesPoint]:
        factors = self._select_factors(factor_ids)
        ingest_run_id = str(uuid.uuid4())
        intraday_days = market_history_days or MACRO_CONFIG["bootstrap_market_history_days"]
        daily_days = (daily_history_years or MACRO_CONFIG["bootstrap_daily_history_years"]) * 365
        results: list[MacroTimeSeriesPoint] = []

        for factor in factors:
            for interval in factor.supported_intervals:
                if interval == "1h" and not factor.is_intraday_enabled:
                    continue
                lookback_days = intraday_days if interval == "1h" else daily_days
                try:
                    results.extend(
                        self.fetch_factor_history(
                            factor=factor,
                            interval=interval,
                            lookback_days=lookback_days,
                            ingest_run_id=ingest_run_id,
                        )
                    )
                except Exception as exc:
                    if not continue_on_error:
                        raise
                    logger.error(
                        "宏观行情历史回填失败 "
                        f"[{factor.factor_id}] [{interval}] "
                        f"{type(exc).__name__}: {exc}"
                    )
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
            logger.warning("没有可保存的宏观行情数据")
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
        logger.info(f"已保存 {len(points)} 条宏观行情数据")

    def collect(self, factor_ids: list[str] | None = None):
        logger.info("开始采集宏观行情因子...")
        points = self.fetch_recent_points(factor_ids=factor_ids)
        if points:
            self.save_to_db(points)
        logger.info("宏观行情因子采集完成")
        return points
