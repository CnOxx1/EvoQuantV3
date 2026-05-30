from database.db_manager import DBManager
from data_layer.tokenomics_data.models import TokenomicsTimeSeriesPoint


class TokenomicsCollectorBase:
    """Tokenomics 时序点公共落库逻辑。"""

    def __init__(self, db: DBManager):
        self.db = db

    @staticmethod
    def _quality_rank(point: TokenomicsTimeSeriesPoint) -> tuple:
        quality_rank = {
            "ok": 3,
            "partial": 2,
            "fallback": 1,
            "stale": 0,
        }
        return (
            point.observation_time,
            quality_rank.get(point.quality_flag, -1),
            point.collected_at,
        )

    @staticmethod
    def _history_identity(point: TokenomicsTimeSeriesPoint) -> tuple:
        return (
            point.factor_id,
            point.entity_type,
            point.entity_key,
            point.interval,
            point.observation_time,
            point.dimensions_key,
            point.source_name,
            point.config_version,
        )

    @staticmethod
    def _latest_identity(point: TokenomicsTimeSeriesPoint) -> tuple:
        return (
            point.factor_id,
            point.entity_type,
            point.entity_key,
            point.interval,
            point.dimensions_key,
            point.source_name,
            point.config_version,
        )

    def _deduplicate_history_points(
        self,
        points: list[TokenomicsTimeSeriesPoint],
    ) -> list[TokenomicsTimeSeriesPoint]:
        deduped: dict[tuple, TokenomicsTimeSeriesPoint] = {}
        for point in points:
            key = self._history_identity(point)
            previous = deduped.get(key)
            if previous is None or self._quality_rank(point) >= self._quality_rank(previous):
                deduped[key] = point
        return list(deduped.values())

    def _deduplicate_latest_points(
        self,
        points: list[TokenomicsTimeSeriesPoint],
    ) -> list[TokenomicsTimeSeriesPoint]:
        deduped: dict[tuple, TokenomicsTimeSeriesPoint] = {}
        for point in points:
            key = self._latest_identity(point)
            previous = deduped.get(key)
            if previous is None or self._quality_rank(point) >= self._quality_rank(previous):
                deduped[key] = point
        return list(deduped.values())

    def save_to_db(self, points: list[TokenomicsTimeSeriesPoint]):
        points = self._deduplicate_history_points(points)
        if not points:
            return

        history_sql = """
            INSERT INTO tokenomics_timeseries (
                factor_id, category, factor_type, entity_type, entity_key,
                interval, observation_time, value, unit, quality_flag,
                dimensions_key, dimensions_json, config_version, source_name,
                source_symbol, raw_payload_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                factor_id, entity_type, entity_key, interval, observation_time,
                dimensions_key, source_name, config_version
            ) DO UPDATE SET
                category=excluded.category,
                factor_type=excluded.factor_type,
                value=excluded.value,
                unit=excluded.unit,
                quality_flag=excluded.quality_flag,
                dimensions_json=excluded.dimensions_json,
                source_symbol=excluded.source_symbol,
                raw_payload_json=excluded.raw_payload_json,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
        """
        latest_sql = """
            INSERT INTO latest_tokenomics_timeseries (
                factor_id, category, factor_type, entity_type, entity_key,
                interval, observation_time, value, unit, quality_flag,
                dimensions_key, dimensions_json, config_version, source_name,
                source_symbol, raw_payload_json, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                factor_id, entity_type, entity_key, interval, dimensions_key,
                source_name, config_version
            ) DO UPDATE SET
                category=excluded.category,
                factor_type=excluded.factor_type,
                observation_time=excluded.observation_time,
                value=excluded.value,
                unit=excluded.unit,
                quality_flag=excluded.quality_flag,
                dimensions_json=excluded.dimensions_json,
                source_symbol=excluded.source_symbol,
                raw_payload_json=excluded.raw_payload_json,
                collected_at=excluded.collected_at,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.observation_time >= latest_tokenomics_timeseries.observation_time
        """
        history_params = [point.history_db_tuple() for point in points]
        latest_points = self._deduplicate_latest_points(points)
        latest_params = [point.latest_db_tuple() for point in latest_points]

        self.db.execute_many(history_sql, history_params)
        self.db.execute_many(latest_sql, latest_params)
        self.db.commit()
