import time
from datetime import datetime, timedelta, timezone

import ccxt
from loguru import logger

from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES
from database.db_manager import DBManager
from data_layer.exchange_data.batch_utils import parallel_fetch
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import FundingRate


class FundingRateCollector:
    """资金费率采集器（合约交易必需）"""

    HISTORY_BATCH_LIMIT = 100

    def __init__(self, client_manager: ExchangeClientManager, db: DBManager):
        self.client_manager = client_manager
        self.db = db

    @staticmethod
    def _to_swap_symbol(symbol: str) -> str:
        """将现货交易对转换为永续合约格式 (BTC/USDT -> BTC/USDT:USDT)"""
        if ":" not in symbol:
            quote = symbol.split("/")[1] if "/" in symbol else "USDT"
            return f"{symbol}:{quote}"
        return symbol

    @staticmethod
    def _to_timestamp_ms(value: datetime) -> int:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)

    @staticmethod
    def _timestamp_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None or timestamp_ms == "":
            return None
        try:
            numeric_timestamp = float(timestamp_ms)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(
            numeric_timestamp / 1000,
            tz=timezone.utc,
        ).replace(tzinfo=None)

    @staticmethod
    def _timestamp_to_milliseconds(value) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ensure_naive_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @retry_on_failure
    def _fetch_funding_rate(self, exchange_name: str, symbol: str) -> dict | None:
        """调用 ccxt 获取资金费率"""
        client = self.client_manager.get_client(exchange_name, market_type="swap")

        # 需要加载合约市场
        if not client.markets:
            client.load_markets()

        swap_symbol = self._to_swap_symbol(symbol)
        return client.fetch_funding_rate(swap_symbol)

    def fetch_funding_rate(
        self, exchange_name: str, symbol: str
    ) -> FundingRate | None:
        """获取单个交易对的当前资金费率"""
        try:
            raw = self._fetch_funding_rate(exchange_name, symbol)
            if raw is None:
                return None

            next_time = None
            if raw.get("fundingDatetime"):
                try:
                    next_time = self._ensure_naive_utc(
                        datetime.fromisoformat(
                            raw["fundingDatetime"].replace("Z", "+00:00")
                        )
                    )
                except (ValueError, TypeError):
                    pass
            elif raw.get("fundingTimestamp"):
                next_time = self._ensure_naive_utc(
                    datetime.fromtimestamp(
                        raw["fundingTimestamp"] / 1000,
                        tz=timezone.utc,
                    )
                )

            event_time = self._timestamp_to_datetime(raw.get("timestamp"))
            if event_time is None and raw.get("fundingDatetime"):
                try:
                    event_time = self._ensure_naive_utc(
                        datetime.fromisoformat(
                            raw["fundingDatetime"].replace("Z", "+00:00")
                        )
                    )
                except (ValueError, TypeError):
                    pass
            if event_time is None:
                event_time = datetime.now(timezone.utc).replace(tzinfo=None)

            funding = FundingRate(
                symbol=symbol,
                exchange=exchange_name,
                funding_rate=raw.get("fundingRate"),
                mark_price=raw.get("markPrice"),
                index_price=raw.get("indexPrice"),
                next_funding_time=next_time,
                timestamp=event_time,
            )
            logger.debug(
                f"获取资金费率: [{exchange_name}] {symbol} "
                f"rate={funding.funding_rate}"
            )
            return funding
        except (ccxt.BadSymbol, ccxt.NotSupported, ccxt.ExchangeError) as e:
            logger.warning(f"资金费率接口不可用 [{exchange_name}] {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"获取资金费率失败 [{exchange_name}] {symbol}: {e}")
            return None

    @retry_on_failure
    def _fetch_funding_history(
        self, exchange_name: str, symbol: str, since: int = None, limit: int | None = None
    ) -> list:
        """调用 ccxt 获取历史资金费率"""
        client = self.client_manager.get_client(exchange_name, market_type="swap")
        swap_symbol = self._to_swap_symbol(symbol)
        return client.fetch_funding_rate_history(
            swap_symbol, since=since, limit=limit or self.HISTORY_BATCH_LIMIT
        )

    def fetch_funding_history(
        self, exchange_name: str, symbol: str, days: int = 30
    ) -> list[FundingRate]:
        """获取历史资金费率"""
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        since_ms = self._to_timestamp_ms(since)
        results = []

        try:
            while True:
                raw_list = self._fetch_funding_history(
                    exchange_name,
                    symbol,
                    since_ms,
                    self.HISTORY_BATCH_LIMIT,
                )
                if not raw_list:
                    break

                valid_timestamps: list[int] = []
                for raw in raw_list:
                    timestamp_ms = self._timestamp_to_milliseconds(raw.get("timestamp"))
                    timestamp = self._timestamp_to_datetime(timestamp_ms)
                    if timestamp is None:
                        logger.warning(
                            f"历史资金费率缺少或损坏 timestamp，跳过 [{exchange_name}] {symbol}"
                        )
                        continue
                    funding = FundingRate(
                        symbol=symbol,
                        exchange=exchange_name,
                        funding_rate=raw.get("fundingRate"),
                        mark_price=raw.get("markPrice"),
                        index_price=raw.get("indexPrice"),
                        next_funding_time=None,
                        timestamp=timestamp,
                    )
                    results.append(funding)
                    valid_timestamps.append(timestamp_ms)

                if len(raw_list) < self.HISTORY_BATCH_LIMIT or not valid_timestamps:
                    break

                last_ts = max(valid_timestamps)
                if last_ts < since_ms:
                    break
                since_ms = last_ts + 1
                time.sleep(0.2)

            logger.info(
                f"获取历史资金费率: [{exchange_name}] {symbol} 共{len(results)}条"
            )
        except (ccxt.BadSymbol, ccxt.NotSupported, ccxt.ExchangeError) as e:
            logger.warning(
                f"历史资金费率接口不可用 [{exchange_name}] {symbol}: {e}"
            )
        except Exception as e:
            logger.error(
                f"获取历史资金费率失败 [{exchange_name}] {symbol}: {e}"
            )

        return results

    def fetch_all_funding_rates(self) -> list[FundingRate]:
        """批量获取所有目标交易对的当前资金费率（优先批量 API，回退并行获取）。

        Per-venue isolation: a geo-blocked or failing exchange must not abort
        funding collection for the remaining venues.
        """
        results = []
        for exchange_name in TARGET_EXCHANGES:
            before = len(results)
            try:
                client = self.client_manager.get_client(
                    exchange_name, market_type="swap"
                )
                if not client.markets:
                    client.load_markets()
                supports_batch = bool(
                    getattr(client, "has", {}).get("fetchFundingRates")
                )

                if supports_batch and len(TARGET_SYMBOLS) > 1:
                    try:
                        swap_symbols = [
                            self._to_swap_symbol(s) for s in TARGET_SYMBOLS
                        ]
                        raw_map = client.fetch_funding_rates(swap_symbols)
                        for symbol in TARGET_SYMBOLS:
                            swap = self._to_swap_symbol(symbol)
                            raw = raw_map.get(swap)
                            if raw:
                                rate = self._parse_funding_raw(
                                    exchange_name, symbol, raw
                                )
                                if rate:
                                    results.append(rate)
                        logger.debug(
                            f"批量获取资金费率成功: [{exchange_name}] "
                            f"{len(results) - before} 条"
                        )
                        continue
                    except Exception as e:
                        logger.warning(
                            f"批量资金费率失败，回退并行获取 [{exchange_name}]: {e}"
                        )

                # 回退：并行获取
                tasks = [(exchange_name, symbol) for symbol in TARGET_SYMBOLS]
                batch_results = parallel_fetch(
                    self.fetch_funding_rate,
                    tasks,
                    task_label=f"funding_{exchange_name}",
                )
                results.extend(batch_results)
            except Exception as e:
                logger.error(
                    f"资金费率采集跳过交易所 [{exchange_name}]: "
                    f"{type(e).__name__}: {e}"
                )
                continue

        logger.info(f"共获取 {len(results)} 条资金费率")
        return results

    def _parse_funding_raw(
        self, exchange_name: str, symbol: str, raw: dict
    ) -> FundingRate | None:
        """从 ccxt raw dict 解析 FundingRate 对象。"""
        try:
            next_time = None
            if raw.get("fundingDatetime"):
                try:
                    next_time = self._ensure_naive_utc(
                        datetime.fromisoformat(
                            raw["fundingDatetime"].replace("Z", "+00:00")
                        )
                    )
                except (ValueError, TypeError):
                    pass
            elif raw.get("fundingTimestamp"):
                next_time = self._ensure_naive_utc(
                    datetime.fromtimestamp(
                        raw["fundingTimestamp"] / 1000, tz=timezone.utc
                    )
                )
            event_time = self._timestamp_to_datetime(raw.get("timestamp"))
            if event_time is None:
                event_time = datetime.now(timezone.utc).replace(tzinfo=None)
            return FundingRate(
                symbol=symbol,
                exchange=exchange_name,
                funding_rate=raw.get("fundingRate"),
                mark_price=raw.get("markPrice"),
                index_price=raw.get("indexPrice"),
                next_funding_time=next_time,
                timestamp=event_time,
            )
        except Exception as e:
            logger.debug(f"解析资金费率失败 [{exchange_name}] {symbol}: {e}")
            return None

    def backfill_all_history(self, days: int = 30) -> list[FundingRate]:
        """批量回填所有目标币种的历史资金费率。"""
        results: list[FundingRate] = []
        for exchange_name in TARGET_EXCHANGES:
            for symbol in TARGET_SYMBOLS:
                history = self.fetch_funding_history(exchange_name, symbol, days=days)
                if history:
                    results.extend(history)
                time.sleep(0.2)
        if results:
            self.save_to_db(results)
        logger.info(f"历史资金费率回填完成，共 {len(results)} 条")
        return results

    def save_to_db(self, funding_list: list[FundingRate]):
        """资金费率写入数据库"""
        history_sql = """
            INSERT INTO funding_rates (
                symbol, exchange, funding_rate, mark_price,
                index_price, next_funding_time, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange, timestamp) DO UPDATE SET
                funding_rate=excluded.funding_rate,
                mark_price=excluded.mark_price,
                index_price=excluded.index_price,
                next_funding_time=excluded.next_funding_time
        """
        latest_sql = """
            INSERT INTO latest_funding_rates (
                symbol, exchange, funding_rate, mark_price,
                index_price, next_funding_time, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange) DO UPDATE SET
                funding_rate=excluded.funding_rate,
                mark_price=excluded.mark_price,
                index_price=excluded.index_price,
                next_funding_time=excluded.next_funding_time,
                timestamp=excluded.timestamp,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_funding_rates.timestamp
        """
        params_list = [
            (
                f.symbol, f.exchange, f.funding_rate,
                f.mark_price, f.index_price,
                f.next_funding_time.isoformat() if f.next_funding_time else None,
                f.timestamp.isoformat(),
            )
            for f in funding_list
        ]
        self.db.execute_many(history_sql, params_list)
        self.db.execute_many(latest_sql, params_list)
        self.db.commit()
        logger.debug(f"已保存 {len(funding_list)} 条资金费率到数据库")

    def collect(self):
        """执行一次完整采集"""
        logger.info("开始采集资金费率...")
        rates = self.fetch_all_funding_rates()
        if rates:
            self.save_to_db(rates)
        logger.info("资金费率采集完成")
        return rates
