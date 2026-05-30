from datetime import datetime, timezone

from loguru import logger

from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES
from database.db_manager import DBManager
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import Ticker


class TickerCollector:
    """实时行情采集器"""

    def __init__(self, client_manager: ExchangeClientManager, db: DBManager):
        self.client_manager = client_manager
        self.db = db

    @retry_on_failure
    def _fetch_ticker(self, exchange_name: str, symbol: str) -> dict:
        """调用 ccxt 获取单个交易对行情"""
        client = self.client_manager.get_client(exchange_name)
        return client.fetch_ticker(symbol)

    @retry_on_failure
    def _fetch_tickers(self, exchange_name: str, symbols: list[str]) -> dict:
        """调用 ccxt 批量获取多个交易对行情。"""
        client = self.client_manager.get_client(exchange_name)
        return client.fetch_tickers(symbols)

    @staticmethod
    def _to_event_time(value) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            try:
                dt = datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                text = str(value).strip()
                if not text:
                    return None
                if text.endswith("Z"):
                    text = f"{text[:-1]}+00:00"
                try:
                    dt = datetime.fromisoformat(text)
                except (TypeError, ValueError):
                    return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @classmethod
    def _extract_event_time(cls, raw: dict) -> datetime | None:
        return cls._to_event_time(raw.get("timestamp")) or cls._to_event_time(
            raw.get("datetime")
        )

    @classmethod
    def _build_ticker(
        cls,
        exchange_name: str,
        symbol: str,
        raw: dict,
    ) -> Ticker | None:
        try:
            event_time = cls._extract_event_time(raw)
            if event_time is None:
                # 部分交易所（如 bybit）不返回 ticker 时间戳，用采集时刻代替
                event_time = datetime.now(timezone.utc).replace(tzinfo=None)
                logger.debug(
                    f"行情无事件时间，使用采集时刻 [{exchange_name}] {symbol}"
                )

            bid = raw.get("bid")
            ask = raw.get("ask")
            mid_price = None
            spread = None
            spread_bps = None
            if bid is not None and ask is not None:
                mid_price = (bid + ask) / 2
                spread = ask - bid
                if mid_price:
                    spread_bps = spread / mid_price * 10000

            ticker = Ticker(
                symbol=symbol,
                exchange=exchange_name,
                last_price=raw.get("last"),
                open_24h=raw.get("open"),
                bid=bid,
                bid_volume=raw.get("bidVolume"),
                ask=ask,
                ask_volume=raw.get("askVolume"),
                previous_close=raw.get("previousClose"),
                high_24h=raw.get("high"),
                low_24h=raw.get("low"),
                vwap_24h=raw.get("vwap"),
                volume_24h=raw.get("baseVolume"),
                quote_volume_24h=raw.get("quoteVolume"),
                change_abs_24h=raw.get("change"),
                change_24h=raw.get("percentage"),
                mid_price=mid_price,
                spread=spread,
                spread_bps=spread_bps,
                timestamp=event_time,
            )
            logger.debug(
                f"获取行情: [{exchange_name}] {symbol} "
                f"last={ticker.last_price}"
            )
            return ticker
        except Exception as e:
            raise ValueError(
                f"构造行情对象失败 [{exchange_name}] {symbol}: {e}"
            ) from e

    @staticmethod
    def _find_batch_ticker(raw_map: dict, symbol: str) -> dict | None:
        if symbol in raw_map:
            return raw_map[symbol]
        for raw in raw_map.values():
            if isinstance(raw, dict) and raw.get("symbol") == symbol:
                return raw
        return None

    def fetch_ticker(self, exchange_name: str, symbol: str) -> Ticker | None:
        """获取单个交易对的行情数据"""
        try:
            raw = self._fetch_ticker(exchange_name, symbol)
            return self._build_ticker(exchange_name, symbol, raw)
        except Exception as e:
            logger.error(f"获取行情失败 [{exchange_name}] {symbol}: {e}")
            return None

    def fetch_exchange_tickers(self, exchange_name: str) -> list[Ticker]:
        """优先使用批量接口获取单个交易所的全部目标行情。"""
        client = self.client_manager.get_client(exchange_name)
        supports_batch = bool(getattr(client, "has", {}).get("fetchTickers"))

        if supports_batch and len(TARGET_SYMBOLS) > 1:
            try:
                raw_map = self._fetch_tickers(exchange_name, TARGET_SYMBOLS)
                results = []
                for symbol in TARGET_SYMBOLS:
                    raw = self._find_batch_ticker(raw_map, symbol)
                    if raw is None:
                        logger.warning(f"批量行情结果缺少交易对 [{exchange_name}] {symbol}")
                        continue
                    ticker = self._build_ticker(exchange_name, symbol, raw)
                    if ticker is None:
                        continue
                    results.append(ticker)
                logger.debug(
                    f"批量获取行情成功: [{exchange_name}] {len(results)} 条"
                )
                return results
            except Exception as e:
                logger.warning(
                    f"批量获取行情失败，回退单symbol接口 [{exchange_name}]: {e}"
                )

        results = []
        for symbol in TARGET_SYMBOLS:
            ticker = self.fetch_ticker(exchange_name, symbol)
            if ticker:
                results.append(ticker)
        return results

    def fetch_all_tickers(self) -> list[Ticker]:
        """批量获取所有目标交易对的行情"""
        results = []
        for exchange_name in TARGET_EXCHANGES:
            results.extend(self.fetch_exchange_tickers(exchange_name))
        logger.info(f"共获取 {len(results)} 条行情数据")
        return results

    def save_to_db(self, tickers: list[Ticker]):
        """行情数据写入数据库"""
        history_sql = """
            INSERT INTO tickers (
                symbol, exchange, last_price, open_24h, bid, bid_volume,
                ask, ask_volume, previous_close, high_24h, low_24h,
                vwap_24h, volume_24h, quote_volume_24h,
                change_abs_24h, change_24h, mid_price, spread, spread_bps, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        latest_sql = """
            INSERT INTO latest_tickers (
                symbol, exchange, last_price, open_24h, bid, bid_volume,
                ask, ask_volume, previous_close, high_24h, low_24h,
                vwap_24h, volume_24h, quote_volume_24h,
                change_abs_24h, change_24h, mid_price, spread, spread_bps, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange) DO UPDATE SET
                last_price=excluded.last_price,
                open_24h=excluded.open_24h,
                bid=excluded.bid,
                bid_volume=excluded.bid_volume,
                ask=excluded.ask,
                ask_volume=excluded.ask_volume,
                previous_close=excluded.previous_close,
                high_24h=excluded.high_24h,
                low_24h=excluded.low_24h,
                vwap_24h=excluded.vwap_24h,
                volume_24h=excluded.volume_24h,
                quote_volume_24h=excluded.quote_volume_24h,
                change_abs_24h=excluded.change_abs_24h,
                change_24h=excluded.change_24h,
                mid_price=excluded.mid_price,
                spread=excluded.spread,
                spread_bps=excluded.spread_bps,
                timestamp=excluded.timestamp,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_tickers.timestamp
        """
        params_list = [
            (
                t.symbol, t.exchange, t.last_price, t.open_24h,
                t.bid, t.bid_volume, t.ask, t.ask_volume,
                t.previous_close, t.high_24h, t.low_24h, t.vwap_24h,
                t.volume_24h, t.quote_volume_24h,
                t.change_abs_24h, t.change_24h,
                t.mid_price, t.spread, t.spread_bps,
                t.timestamp.isoformat(),
            )
            for t in tickers
        ]
        self.db.execute_many(history_sql, params_list)
        self.db.execute_many(latest_sql, params_list)
        self.db.commit()
        logger.debug(f"已保存 {len(tickers)} 条行情到数据库")

    def collect(self):
        """执行一次完整采集"""
        logger.info("开始采集实时行情...")
        tickers = self.fetch_all_tickers()
        if tickers:
            self.save_to_db(tickers)
        logger.info("实时行情采集完成")
        return tickers
