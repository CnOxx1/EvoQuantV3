import json
from datetime import datetime, timezone

from loguru import logger

from config.symbols import TARGET_SYMBOLS, TARGET_EXCHANGES, ORDERBOOK_DEPTH
from database.db_manager import DBManager
from data_layer.exchange_data.client import ExchangeClientManager, retry_on_failure
from data_layer.exchange_data.models import OrderBook, OrderBookLevel


class OrderBookCollector:
    """深度数据采集器"""

    def __init__(self, client_manager: ExchangeClientManager, db: DBManager):
        self.client_manager = client_manager
        self.db = db
        self._missing_event_time_warned_exchanges: set[str] = set()

    @retry_on_failure
    def _fetch_orderbook(
        self, exchange_name: str, symbol: str, limit: int
    ) -> dict:
        """调用 ccxt 获取深度数据"""
        client = self.client_manager.get_client(exchange_name)
        return client.fetch_order_book(symbol, limit=limit)

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

    def _log_missing_event_time(self, exchange_name: str, symbol: str):
        message = (
            f"深度快照缺少或损坏事件时间，跳过 [{exchange_name}] {symbol}；"
            "当前不会回退到本地采集时间伪装成事件时间。"
        )
        if exchange_name in self._missing_event_time_warned_exchanges:
            logger.debug(message)
            return
        self._missing_event_time_warned_exchanges.add(exchange_name)
        logger.warning(
            message
            + " 若该交易所 REST orderbook 默认不返回 timestamp/datetime，"
            "后续同类情况将仅记录 debug。"
        )

    def fetch_orderbook(
        self, exchange_name: str, symbol: str, limit: int = None
    ) -> OrderBook | None:
        """获取单个交易对的深度数据"""
        limit = limit or ORDERBOOK_DEPTH
        try:
            raw = self._fetch_orderbook(exchange_name, symbol, limit)
            event_time = self._extract_event_time(raw)
            if event_time is None:
                event_time = datetime.now(timezone.utc).replace(tzinfo=None)
            bids = [
                OrderBookLevel(price=bid[0], amount=bid[1])
                for bid in raw.get("bids", [])[:limit]
            ]
            asks = [
                OrderBookLevel(price=ask[0], amount=ask[1])
                for ask in raw.get("asks", [])[:limit]
            ]
            best_bid = bids[0].price if bids else None
            best_ask = asks[0].price if asks else None
            mid_price = None
            spread = None
            spread_bps = None
            if best_bid is not None and best_ask is not None:
                mid_price = (best_bid + best_ask) / 2
                spread = best_ask - best_bid
                if mid_price:
                    spread_bps = spread / mid_price * 10000

            bid_depth_notional = sum(level.price * level.amount for level in bids)
            ask_depth_notional = sum(level.price * level.amount for level in asks)
            total_notional = bid_depth_notional + ask_depth_notional
            depth_imbalance = None
            if total_notional:
                depth_imbalance = (
                    bid_depth_notional - ask_depth_notional
                ) / total_notional

            orderbook = OrderBook(
                symbol=symbol,
                exchange=exchange_name,
                snapshot_depth=limit,
                bids=bids,
                asks=asks,
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid_price,
                spread=spread,
                spread_bps=spread_bps,
                bid_depth_notional=bid_depth_notional,
                ask_depth_notional=ask_depth_notional,
                depth_imbalance=depth_imbalance,
                timestamp=event_time,
            )
            logger.debug(
                f"获取深度: [{exchange_name}] {symbol} "
                f"bids={len(orderbook.bids)} asks={len(orderbook.asks)}"
            )
            return orderbook
        except Exception as e:
            logger.error(f"获取深度失败 [{exchange_name}] {symbol}: {e}")
            return None

    def fetch_all_orderbooks(self, symbols: list[str] | None = None) -> list[OrderBook]:
        """批量获取目标交易对的深度。

        Parameters
        ----------
        symbols : list[str] | None
            要采集的符号列表，为 None 时使用全部 TARGET_SYMBOLS。
            支持分层调度：调度器按层级传入不同子集。
        """
        target_symbols = symbols if symbols is not None else TARGET_SYMBOLS
        results = []
        for exchange_name in TARGET_EXCHANGES:
            for symbol in target_symbols:
                ob = self.fetch_orderbook(exchange_name, symbol)
                if ob:
                    results.append(ob)
        logger.info(f"共获取 {len(results)} 条深度数据")
        return results

    def save_to_db(self, orderbooks: list[OrderBook]):
        """深度快照写入数据库（JSON序列化存储）"""
        history_sql = """
            INSERT INTO orderbook_snapshots (
                symbol, exchange, snapshot_depth, best_bid, best_ask,
                mid_price, spread, spread_bps, bid_depth_notional,
                ask_depth_notional, depth_imbalance, bids_json, asks_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        latest_sql = """
            INSERT INTO latest_orderbook_snapshots (
                symbol, exchange, snapshot_depth, best_bid, best_ask,
                mid_price, spread, spread_bps, bid_depth_notional,
                ask_depth_notional, depth_imbalance, bids_json, asks_json, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, exchange) DO UPDATE SET
                snapshot_depth=excluded.snapshot_depth,
                best_bid=excluded.best_bid,
                best_ask=excluded.best_ask,
                mid_price=excluded.mid_price,
                spread=excluded.spread,
                spread_bps=excluded.spread_bps,
                bid_depth_notional=excluded.bid_depth_notional,
                ask_depth_notional=excluded.ask_depth_notional,
                depth_imbalance=excluded.depth_imbalance,
                bids_json=excluded.bids_json,
                asks_json=excluded.asks_json,
                timestamp=excluded.timestamp,
                updated_at=CURRENT_TIMESTAMP
            WHERE excluded.timestamp >= latest_orderbook_snapshots.timestamp
        """
        params_list = [
            (
                ob.symbol,
                ob.exchange,
                ob.snapshot_depth,
                ob.best_bid,
                ob.best_ask,
                ob.mid_price,
                ob.spread,
                ob.spread_bps,
                ob.bid_depth_notional,
                ob.ask_depth_notional,
                ob.depth_imbalance,
                json.dumps(
                    [{"price": l.price, "amount": l.amount} for l in ob.bids],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [{"price": l.price, "amount": l.amount} for l in ob.asks],
                    ensure_ascii=False,
                ),
                ob.timestamp.isoformat(),
            )
            for ob in orderbooks
        ]
        self.db.execute_many(history_sql, params_list)
        self.db.execute_many(latest_sql, params_list)
        self.db.commit()
        logger.debug(f"已保存 {len(orderbooks)} 条深度快照到数据库")

    def collect(self):
        """执行一次完整采集"""
        logger.info("开始采集深度数据...")
        orderbooks = self.fetch_all_orderbooks()
        if orderbooks:
            self.save_to_db(orderbooks)
        logger.info("深度数据采集完成")
        return orderbooks
