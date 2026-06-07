import time
from datetime import datetime, timedelta, timezone

from loguru import logger

from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES, KLINE_TIMEFRAMES, KLINE_BACKFILL_DAYS
from database.db_manager import DBManager
from data_layer.exchange_data.batch_utils import parallel_fetch
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import Kline


class KlineCollector:
    """K线数据采集器（支持历史回填与增量更新）"""

    # ccxt 单次请求最大K线数量（大部分交易所限制500-1000）
    BATCH_LIMIT = 500
    INITIAL_FETCH_LIMIT = 50
    INCREMENTAL_OVERLAP_BARS = 2
    TIMEFRAME_TO_DELTA = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }
    TIMEFRAME_INTERVAL_SECONDS = {
        timeframe: int(delta.total_seconds())
        for timeframe, delta in TIMEFRAME_TO_DELTA.items()
    }

    def __init__(self, client_manager: ExchangeClientManager, db: DBManager):
        self.client_manager = client_manager
        self.db = db

    @classmethod
    def _timeframe_delta(cls, timeframe: str) -> timedelta:
        if timeframe not in cls.TIMEFRAME_TO_DELTA:
            raise ValueError(f"不支持的K线周期: {timeframe}")
        return cls.TIMEFRAME_TO_DELTA[timeframe]

    @staticmethod
    def _to_timestamp_ms(value: datetime | None) -> int | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)

    @staticmethod
    def _parse_db_datetime(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            dt = value
        else:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def _safe_float(value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_latest_open_time(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str,
    ) -> datetime | None:
        row = self.db.fetch_one(
            """
            SELECT MAX(open_time) AS latest_open_time
            FROM klines
            WHERE exchange = ? AND symbol = ? AND timeframe = ?
            """,
            (exchange_name, symbol, timeframe),
        )
        if row is None or row["latest_open_time"] is None:
            return None
        return self._parse_db_datetime(row["latest_open_time"])

    @retry_on_failure
    def _fetch_ohlcv(
        self, exchange_name: str, symbol: str, timeframe: str,
        since: int = None, limit: int = None
    ) -> list:
        """调用 ccxt 获取K线原始数据"""
        client = self.client_manager.get_client(exchange_name)
        return client.fetch_ohlcv(
            symbol, timeframe=timeframe, since=since, limit=limit or self.BATCH_LIMIT
        )

    def _parse_ohlcv(
        self, raw_data: list, symbol: str, exchange: str, timeframe: str
    ) -> list[Kline]:
        """将 ccxt 原始数据转换为 Kline 模型"""
        results = []
        for row in raw_data:
            if not isinstance(row, list | tuple) or len(row) < 6:
                logger.warning(
                    f"K线原始行结构损坏，跳过 [{exchange}] {symbol} {timeframe}: {row}"
                )
                continue
            timestamp_ms = self._safe_float(row[0])
            open_price = self._safe_float(row[1])
            high_price = self._safe_float(row[2])
            low_price = self._safe_float(row[3])
            close_price = self._safe_float(row[4])
            volume = self._safe_float(row[5])
            if (
                timestamp_ms is None
                or open_price is None
                or high_price is None
                or low_price is None
                or close_price is None
                or volume is None
            ):
                logger.warning(
                    "K线存在缺失核心 OHLCV 字段，跳过 "
                    f"[{exchange}] {symbol} {timeframe}: {row}"
                )
                continue
            # ccxt ohlcv: [timestamp_ms, open, high, low, close, volume]
            kline = Kline(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                open_time=datetime.fromtimestamp(
                    timestamp_ms / 1000,
                    tz=timezone.utc,
                ).replace(tzinfo=None),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
            results.append(kline)
        return results

    def fetch_klines(
        self, exchange_name: str, symbol: str, timeframe: str,
        since: datetime = None, limit: int = None
    ) -> list[Kline]:
        """获取K线数据"""
        since_ms = self._to_timestamp_ms(since)
        try:
            raw = self._fetch_ohlcv(exchange_name, symbol, timeframe, since_ms, limit)
            klines = self._parse_ohlcv(raw, symbol, exchange_name, timeframe)
            logger.debug(
                f"获取K线: [{exchange_name}] {symbol} {timeframe} "
                f"共{len(klines)}条"
            )
            return klines
        except Exception as e:
            logger.error(
                f"获取K线失败 [{exchange_name}] {symbol} {timeframe}: {e}"
            )
            return []

    def fetch_incremental_klines(
        self,
        exchange_name: str,
        symbol: str,
        timeframe: str,
    ) -> list[Kline]:
        """基于数据库最新游标增量拉取K线，并回补少量重叠区间。"""
        latest_open_time = self._get_latest_open_time(exchange_name, symbol, timeframe)
        if latest_open_time is None:
            return self.fetch_klines(
                exchange_name,
                symbol,
                timeframe,
                limit=self.INITIAL_FETCH_LIMIT,
            )

        since = latest_open_time - (
            self._timeframe_delta(timeframe) * self.INCREMENTAL_OVERLAP_BARS
        )
        since_ms = self._to_timestamp_ms(since)
        all_klines: list[Kline] = []

        while True:
            try:
                raw = self._fetch_ohlcv(
                    exchange_name,
                    symbol,
                    timeframe,
                    since_ms,
                    self.BATCH_LIMIT,
                )
            except Exception as e:
                logger.error(
                    f"增量获取K线失败 [{exchange_name}] {symbol} {timeframe}: {e}"
                )
                break

            if not raw:
                break

            all_klines.extend(
                self._parse_ohlcv(raw, symbol, exchange_name, timeframe)
            )
            last_ts = raw[-1][0]
            since_ms = last_ts + 1

            if len(raw) < self.BATCH_LIMIT:
                break

            time.sleep(0.2)

        logger.debug(
            f"增量获取K线: [{exchange_name}] {symbol} {timeframe} 共{len(all_klines)}条"
        )
        return all_klines

    def backfill(
        self, exchange_name: str, symbol: str, timeframe: str,
        days: int = None
    ):
        """历史K线数据批量回填"""
        days = days or KLINE_BACKFILL_DAYS
        start_time = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        )
        since_ms = self._to_timestamp_ms(start_time)
        all_klines = []

        logger.info(
            f"开始回填K线: [{exchange_name}] {symbol} {timeframe} "
            f"最近{days}天"
        )

        while True:
            try:
                raw = self._fetch_ohlcv(
                    exchange_name, symbol, timeframe, since_ms, self.BATCH_LIMIT
                )
            except Exception as e:
                logger.error(f"回填请求失败: {e}")
                break

            if not raw:
                break

            klines = self._parse_ohlcv(raw, symbol, exchange_name, timeframe)
            all_klines.extend(klines)

            # 下一批从最后一条之后开始
            last_ts = raw[-1][0]
            since_ms = last_ts + 1

            # 如果返回数量不足，说明已到达最新数据
            if len(raw) < self.BATCH_LIMIT:
                break

            # 避免触发频率限制
            time.sleep(0.5)

        if all_klines:
            self.save_to_db(all_klines)
            logger.info(
                f"回填完成: [{exchange_name}] {symbol} {timeframe} "
                f"共{len(all_klines)}条"
            )
        return all_klines

    def incremental_update(self, timeframe: str | None = None):
        """增量更新：并行获取所有目标币种的最新K线。"""
        target_timeframes = [timeframe] if timeframe else KLINE_TIMEFRAMES
        all_klines: list[Kline] = []
        for exchange_name in TARGET_EXCHANGES:
            tasks = [
                (exchange_name, symbol, tf)
                for symbol in TARGET_SYMBOLS
                for tf in target_timeframes
            ]
            results = parallel_fetch(
                self.fetch_incremental_klines,
                tasks,
                task_label=f"kline_{exchange_name}",
            )
            all_klines.extend(results)
        if all_klines:
            self.save_to_db(all_klines)
            logger.info(f"K线增量批次已写入，共 {len(all_klines)} 条")
        return all_klines

    def collect_timeframe(self, timeframe: str):
        """只采集指定周期的增量 K 线。"""
        logger.info(f"开始增量更新K线数据: {timeframe}")
        all_klines = self.incremental_update(timeframe=timeframe)
        logger.info(f"K线增量更新完成: {timeframe}")
        return all_klines

    def backfill_all(self):
        """回填所有目标币种的历史K线"""
        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                for timeframe in KLINE_TIMEFRAMES:
                    self.backfill(exchange_name, symbol, timeframe)

    def save_to_db(self, klines: list[Kline]):
        """K线数据写入数据库（UPSERT）"""
        sql = """
            INSERT INTO klines (
                symbol, exchange, timeframe, open_time,
                open, high, low, close, volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timeframe, open_time) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume
        """
        params_list = [
            (
                k.symbol, k.exchange, k.timeframe,
                k.open_time.isoformat(),
                k.open, k.high, k.low, k.close, k.volume,
            )
            for k in klines
        ]
        self.db.execute_many(sql, params_list)
        self.db.commit()

    def collect(self):
        """执行一次增量采集"""
        logger.info("开始增量更新K线数据...")
        all_klines = self.incremental_update()
        logger.info("K线增量更新完成")
        return all_klines
