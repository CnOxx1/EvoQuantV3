"""orderflow_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from config.symbols import TARGET_ASSET_CODES
from data_layer.orderflow_data.client import OrderflowClient


# symbol 映射
SYMBOL_MAP = {
    "BTC": {"binance": "BTCUSDT", "bybit": "BTCUSDT", "okx": "BTC-USDT-SWAP"},
    "ETH": {"binance": "ETHUSDT", "bybit": "ETHUSDT", "okx": "ETH-USDT-SWAP"},
    "SOL": {"binance": "SOLUSDT", "bybit": "SOLUSDT", "okx": "SOL-USDT-SWAP"},
    "BNB": {"binance": "BNBUSDT", "bybit": "BNBUSDT", "okx": "BNB-USDT-SWAP"},
    "XRP": {"binance": "XRPUSDT", "bybit": "XRPUSDT", "okx": "XRP-USDT-SWAP"},
    "DOGE": {"binance": "DOGEUSDT", "bybit": "DOGEUSDT", "okx": "DOGE-USDT-SWAP"},
    "ADA": {"binance": "ADAUSDT", "bybit": "ADAUSDT", "okx": "ADA-USDT-SWAP"},
    "AVAX": {"binance": "AVAXUSDT", "bybit": "AVAXUSDT", "okx": "AVAX-USDT-SWAP"},
    "DOT": {"binance": "DOTUSDT", "bybit": "DOTUSDT", "okx": "DOT-USDT-SWAP"},
    "LINK": {"binance": "LINKUSDT", "bybit": "LINKUSDT", "okx": "LINK-USDT-SWAP"},
    "ARB": {"binance": "ARBUSDT", "bybit": "ARBUSDT", "okx": "ARB-USDT-SWAP"},
    "OP": {"binance": "OPUSDT", "bybit": "OPUSDT", "okx": "OP-USDT-SWAP"},
}

TARGET_SYMBOLS = TARGET_ASSET_CODES
LARGE_TRADE_USD = 100_000


class OrderflowDataService:
    """订单流数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or OrderflowClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS orderflow_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                trade_time TEXT NOT NULL,
                price REAL NOT NULL,
                quantity REAL NOT NULL,
                side TEXT NOT NULL,
                is_maker INTEGER DEFAULT 0,
                trade_id TEXT,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, trade_id)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS orderflow_agg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                exchange TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                buy_volume REAL DEFAULT 0,
                sell_volume REAL DEFAULT 0,
                cvd REAL DEFAULT 0,
                large_buy_count INTEGER DEFAULT 0,
                large_sell_count INTEGER DEFAULT 0,
                large_buy_volume REAL DEFAULT 0,
                large_sell_volume REAL DEFAULT 0,
                vwap REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                aggression_ratio REAL DEFAULT 1.0,
                collected_at TEXT NOT NULL,
                UNIQUE(entity_key, exchange, interval, window_start)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orderflow_trades_entity
            ON orderflow_trades(entity_key, trade_time DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orderflow_agg_entity
            ON orderflow_agg(entity_key, window_start DESC)
        """)
        self.db.conn.commit()
        logger.info("orderflow_data 存储初始化完成")

    def bootstrap(self, symbols: list[str] | None = None):
        """首次回填。"""
        symbols = symbols or TARGET_SYMBOLS
        logger.info(f"开始 bootstrap，目标: {symbols}")
        self._collect_all_exchanges(symbols)
        self._compute_aggregations(symbols)
        logger.info("bootstrap 完成")

    def collect_once(self, symbols: list[str] | None = None):
        """执行一次采集周期。"""
        symbols = symbols or TARGET_SYMBOLS
        self._collect_all_exchanges(symbols)
        self._compute_aggregations(symbols)
        logger.info(f"collect_once 完成，处理 {len(symbols)} 个标的")

    def _collect_all_exchanges(self, symbols: list[str]):
        """从所有交易所采集逐笔成交。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for entity_key in symbols:
            mapping = SYMBOL_MAP.get(entity_key, {})

            # Binance
            if "binance" in mapping:
                trades = self.client.fetch_recent_trades_binance(mapping["binance"])
                self._store_trades(trades, "binance", mapping["binance"], entity_key, now_iso)

            # Bybit
            if "bybit" in mapping:
                trades = self.client.fetch_recent_trades_bybit(mapping["bybit"])
                self._store_trades(trades, "bybit", mapping["bybit"], entity_key, now_iso)

            # OKX
            if "okx" in mapping:
                trades = self.client.fetch_recent_trades_okx(mapping["okx"])
                self._store_trades(trades, "okx", mapping["okx"], entity_key, now_iso)

    def _store_trades(self, trades: list[dict], exchange: str, symbol: str, entity_key: str, now_iso: str):
        """存储逐笔成交到数据库。"""
        for t in trades:
            side = "sell" if t.get("is_buyer_maker") else "buy"
            self.db.conn.execute("""
                INSERT OR IGNORE INTO orderflow_trades
                (exchange, symbol, entity_key, trade_time, price, quantity,
                 side, is_maker, trade_id, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exchange, symbol, entity_key,
                t["time"], t["price"], t["quantity"],
                side, int(t.get("is_buyer_maker", False)),
                t.get("trade_id", ""), now_iso,
            ))
        self.db.conn.commit()

    def _compute_aggregations(self, symbols: list[str]):
        """计算订单流聚合指标。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        window_start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        for entity_key in symbols:
            for exchange in ["binance", "bybit", "okx"]:
                cursor = self.db.conn.execute("""
                    SELECT price, quantity, side FROM orderflow_trades
                    WHERE entity_key = ? AND exchange = ? AND trade_time >= ?
                """, (entity_key, exchange, window_start))
                rows = cursor.fetchall()
                if not rows:
                    continue

                buy_vol = sum(r[0] * r[1] for r in rows if r[2] == "buy")
                sell_vol = sum(r[0] * r[1] for r in rows if r[2] == "sell")
                cvd = buy_vol - sell_vol
                total_notional = sum(r[0] * r[1] for r in rows)
                total_qty = sum(r[1] for r in rows)
                vwap = total_notional / total_qty if total_qty > 0 else 0

                large_buys = [(r[0] * r[1]) for r in rows if r[2] == "buy" and r[0] * r[1] >= LARGE_TRADE_USD]
                large_sells = [(r[0] * r[1]) for r in rows if r[2] == "sell" and r[0] * r[1] >= LARGE_TRADE_USD]

                aggression = buy_vol / sell_vol if sell_vol > 0 else 2.0

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO orderflow_agg
                    (entity_key, exchange, interval, window_start, window_end,
                     buy_volume, sell_volume, cvd, large_buy_count, large_sell_count,
                     large_buy_volume, large_sell_volume, vwap, trade_count,
                     aggression_ratio, collected_at)
                    VALUES (?, ?, '1h', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entity_key, exchange, window_start, now_iso,
                    buy_vol, sell_vol, cvd,
                    len(large_buys), len(large_sells),
                    sum(large_buys), sum(large_sells),
                    vwap, len(rows), round(aggression, 4), now_iso,
                ))
        self.db.conn.commit()

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的订单流上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        placeholders = ",".join("?" * len(symbols))
        cursor = self.db.conn.execute(f"""
            SELECT entity_key, exchange, interval, window_start,
                   buy_volume, sell_volume, cvd,
                   large_buy_count, large_sell_count,
                   large_buy_volume, large_sell_volume,
                   vwap, trade_count, aggression_ratio
            FROM orderflow_agg
            WHERE entity_key IN ({placeholders})
            ORDER BY entity_key, window_start DESC
        """, tuple(symbols))
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        # 按 entity 聚合（跨交易所合并）
        entity_data = {}
        for row in rows:
            key = row[0]
            if key not in entity_data:
                entity_data[key] = {
                    "total_buy_volume": 0, "total_sell_volume": 0,
                    "total_cvd": 0, "large_buy_count": 0, "large_sell_count": 0,
                    "exchanges": [],
                }
            d = entity_data[key]
            d["total_buy_volume"] += row[4]
            d["total_sell_volume"] += row[5]
            d["total_cvd"] += row[6]
            d["large_buy_count"] += row[7]
            d["large_sell_count"] += row[8]
            d["exchanges"].append(row[1])

        summaries = {}
        for entity, d in entity_data.items():
            total = d["total_buy_volume"] + d["total_sell_volume"]
            if d["total_cvd"] > total * 0.1:
                bias = "buy_dominant"
            elif d["total_cvd"] < -total * 0.1:
                bias = "sell_dominant"
            else:
                bias = "balanced"

            summaries[entity] = {
                "buy_volume_usd": round(d["total_buy_volume"], 2),
                "sell_volume_usd": round(d["total_sell_volume"], 2),
                "cvd_usd": round(d["total_cvd"], 2),
                "large_buy_count": d["large_buy_count"],
                "large_sell_count": d["large_sell_count"],
                "bias": bias,
                "exchanges_covered": list(set(d["exchanges"])),
            }

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "1h",
            "coverage": {
                "symbols_with_data": len(entity_data),
                "symbols_requested": len(symbols),
            },
            "summaries": summaries,
            "raw_row_count": len(rows),
        }

    def build_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            kwargs={"symbols": symbols}, id="orderflow_collect",
        )
        return scheduler

    def build_async_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            kwargs={"symbols": symbols}, id="orderflow_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
