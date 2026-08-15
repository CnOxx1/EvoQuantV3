"""cex_orderbook_depth 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.cex_orderbook_depth.client import CexOrderbookDepthClient


from config.symbols import TARGET_ASSET_CODES

DEFAULT_SYMBOLS = [f"{asset}USDT" for asset in TARGET_ASSET_CODES]
DEFAULT_EXCHANGES = ["binance", "okx", "bybit"]


class CexOrderbookDepthService:
    """CEX 深度盘口数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or CexOrderbookDepthClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS depth_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                bid_volume_total REAL DEFAULT 0,
                ask_volume_total REAL DEFAULT 0,
                depth_imbalance_1pct REAL DEFAULT 0,
                depth_imbalance_5pct REAL DEFAULT 0,
                buy_wall_price REAL DEFAULT 0,
                buy_wall_size REAL DEFAULT 0,
                sell_wall_price REAL DEFAULT 0,
                sell_wall_size REAL DEFAULT 0,
                mid_price REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(symbol, exchange, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS depth_levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                side TEXT NOT NULL,
                price_level REAL DEFAULT 0,
                volume REAL DEFAULT 0,
                cumulative_volume REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(symbol, exchange, timestamp, side, price_level)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_depth_snapshots_symbol
            ON depth_snapshots(symbol, exchange, timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_depth_levels_symbol
            ON depth_levels(symbol, exchange, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("cex_orderbook_depth 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 cex_orderbook_depth bootstrap")
        self._collect_depth()
        logger.info("cex_orderbook_depth bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_depth()
        logger.info("cex_orderbook_depth collect_once 完成")

    def _collect_depth(self):
        """采集所有交易所的深度盘口数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        collected_count = 0

        for symbol in DEFAULT_SYMBOLS:
            for exchange in DEFAULT_EXCHANGES:
                data = self.client.fetch_full_depth(symbol, exchange)
                if not data:
                    continue

                bids = data.get("bids", [])
                asks = data.get("asks", [])
                if not bids and not asks:
                    continue

                snapshot = self._compute_snapshot(symbol, exchange, now_iso, bids, asks)
                self._store_snapshot(snapshot)
                self._store_aggregated_levels(symbol, exchange, now_iso, bids, asks)
                collected_count += 1

        self.db.conn.commit()
        logger.info(f"深度盘口采集完成，处理 {collected_count} 个交易对")

    def _compute_snapshot(self, symbol, exchange, timestamp, bids, asks) -> dict:
        """从原始深度数据计算聚合快照。"""
        bid_prices = [(float(b[0]), float(b[1])) for b in bids if len(b) >= 2]
        ask_prices = [(float(a[0]), float(a[1])) for a in asks if len(a) >= 2]

        bid_volume_total = sum(v for _, v in bid_prices)
        ask_volume_total = sum(v for _, v in ask_prices)

        mid_price = 0.0
        if bid_prices and ask_prices:
            mid_price = (bid_prices[0][0] + ask_prices[0][0]) / 2

        # 计算 1% 和 5% 范围内的不平衡度
        imbalance_1pct = self._calc_imbalance(bid_prices, ask_prices, mid_price, 0.01)
        imbalance_5pct = self._calc_imbalance(bid_prices, ask_prices, mid_price, 0.05)

        # 找买墙和卖墙（最大单档）
        buy_wall_price, buy_wall_size = 0.0, 0.0
        if bid_prices:
            max_bid = max(bid_prices, key=lambda x: x[1])
            buy_wall_price, buy_wall_size = max_bid

        sell_wall_price, sell_wall_size = 0.0, 0.0
        if ask_prices:
            max_ask = max(ask_prices, key=lambda x: x[1])
            sell_wall_price, sell_wall_size = max_ask

        return {
            "symbol": symbol, "exchange": exchange, "timestamp": timestamp,
            "bid_volume_total": bid_volume_total,
            "ask_volume_total": ask_volume_total,
            "depth_imbalance_1pct": imbalance_1pct,
            "depth_imbalance_5pct": imbalance_5pct,
            "buy_wall_price": buy_wall_price, "buy_wall_size": buy_wall_size,
            "sell_wall_price": sell_wall_price, "sell_wall_size": sell_wall_size,
            "mid_price": mid_price,
        }

    def _calc_imbalance(self, bids, asks, mid_price, pct_range) -> float:
        """计算指定价格范围内的买卖不平衡度。"""
        if mid_price <= 0:
            return 0.0
        lower = mid_price * (1 - pct_range)
        upper = mid_price * (1 + pct_range)
        bid_vol = sum(v for p, v in bids if p >= lower)
        ask_vol = sum(v for p, v in asks if p <= upper)
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return round((bid_vol - ask_vol) / total, 4)

    def _store_snapshot(self, snapshot: dict):
        """存储深度快照。"""
        self.db.conn.execute("""
            INSERT OR REPLACE INTO depth_snapshots
            (symbol, exchange, timestamp, bid_volume_total, ask_volume_total,
             depth_imbalance_1pct, depth_imbalance_5pct,
             buy_wall_price, buy_wall_size, sell_wall_price, sell_wall_size,
             mid_price, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (snapshot["symbol"], snapshot["exchange"], snapshot["timestamp"],
              snapshot["bid_volume_total"], snapshot["ask_volume_total"],
              snapshot["depth_imbalance_1pct"], snapshot["depth_imbalance_5pct"],
              snapshot["buy_wall_price"], snapshot["buy_wall_size"],
              snapshot["sell_wall_price"], snapshot["sell_wall_size"],
              snapshot["mid_price"], snapshot["timestamp"]))

    def _store_aggregated_levels(self, symbol, exchange, timestamp, bids, asks):
        """存储聚合后的深度档位（按百分比区间聚合，非全部5000档）。"""
        bid_prices = [(float(b[0]), float(b[1])) for b in bids if len(b) >= 2]
        ask_prices = [(float(a[0]), float(a[1])) for a in asks if len(a) >= 2]

        if not bid_prices or not ask_prices:
            return

        mid = (bid_prices[0][0] + ask_prices[0][0]) / 2
        # 按 0.1%, 0.5%, 1%, 2%, 5%, 10% 区间聚合
        pct_levels = [0.001, 0.005, 0.01, 0.02, 0.05, 0.10]

        for pct in pct_levels:
            bid_vol = sum(v for p, v in bid_prices if p >= mid * (1 - pct))
            ask_vol = sum(v for p, v in ask_prices if p <= mid * (1 + pct))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO depth_levels
                (symbol, exchange, timestamp, side, price_level, volume,
                 cumulative_volume, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, exchange, timestamp, "bid", pct, bid_vol, bid_vol, timestamp))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO depth_levels
                (symbol, exchange, timestamp, side, price_level, volume,
                 cumulative_volume, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, exchange, timestamp, "ask", pct, ask_vol, ask_vol, timestamp))

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的深度盘口上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        cursor = self.db.conn.execute("""
            SELECT symbol, exchange, timestamp, bid_volume_total, ask_volume_total,
                   depth_imbalance_1pct, depth_imbalance_5pct,
                   buy_wall_price, buy_wall_size, sell_wall_price, sell_wall_size,
                   mid_price
            FROM depth_snapshots
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM depth_snapshots
            )
            ORDER BY symbol, exchange
        """)
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        snapshots = []
        for row in rows:
            (symbol, exchange, ts, bid_vol, ask_vol, imb_1, imb_5,
             bw_price, bw_size, sw_price, sw_size, mid) = row
            snapshots.append({
                "symbol": symbol,
                "exchange": exchange,
                "mid_price": round(mid, 4),
                "bid_volume_total": round(bid_vol, 4),
                "ask_volume_total": round(ask_vol, 4),
                "depth_imbalance_1pct": round(imb_1, 4),
                "depth_imbalance_5pct": round(imb_5, 4),
                "buy_wall": {"price": round(bw_price, 4), "size": round(bw_size, 4)},
                "sell_wall": {"price": round(sw_price, 4), "size": round(sw_size, 4)},
            })

        return {
            "status": "ready",
            "as_of": now_iso,
            "depth_signals": {
                "snapshots_count": len(snapshots),
                "snapshots": snapshots,
            },
            "interpretation": {
                "depth_imbalance": "正值=买盘强于卖盘, 负值=卖盘强于买盘, 范围[-1,1]",
                "buy_wall": "最大买单挂单价格和数量",
                "sell_wall": "最大卖单挂单价格和数量",
                "bid_volume_total": "所有买盘挂单总量",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 秒采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", seconds=30,
            id="cex_orderbook_depth_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 秒采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", seconds=30,
            id="cex_orderbook_depth_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
