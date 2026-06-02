"""dex_trade_flow 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.dex_trade_flow.client import DexTradeFlowClient


class DexTradeFlowService:
    """DEX 大额交易流数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or DexTradeFlowClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS dex_large_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                token_in TEXT,
                token_out TEXT,
                amount_usd REAL DEFAULT 0,
                router TEXT,
                dex_venue TEXT,
                tx_hash TEXT,
                trader_address TEXT,
                is_mev_victim INTEGER DEFAULT 0,
                trade_type TEXT DEFAULT 'swap',
                collected_at TEXT NOT NULL,
                UNIQUE(tx_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS dex_router_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                router TEXT NOT NULL,
                volume_24h_usd REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                avg_trade_size REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(router, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dex_large_trades_time
            ON dex_large_trades(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dex_router_stats_time
            ON dex_router_stats(router, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("dex_trade_flow 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 bootstrap DEX 交易流数据")
        self._collect_trades()
        self._collect_router_stats()
        logger.info("bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_trades()
        self._collect_router_stats()
        logger.info("collect_once 完成")

    def _collect_trades(self):
        """采集大额 DEX 交易。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        trades = self.client.fetch_recent_trades(min_usd=50000)
        mev_victims = self.client.fetch_mev_victims()
        mev_tx_set = {v.get("txHash", "") for v in mev_victims}

        for trade in trades:
            tx_hash = trade.get("txHash", trade.get("hash", ""))
            is_mev = 1 if tx_hash in mev_tx_set else 0
            self.db.conn.execute("""
                INSERT OR IGNORE INTO dex_large_trades
                (timestamp, token_in, token_out, amount_usd, router,
                 dex_venue, tx_hash, trader_address, is_mev_victim,
                 trade_type, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.get("timestamp", now_iso),
                trade.get("tokenIn", {}).get("symbol", ""),
                trade.get("tokenOut", {}).get("symbol", ""),
                float(trade.get("amountUSD", 0) or 0),
                trade.get("router", "0x"),
                trade.get("source", ""),
                tx_hash,
                trade.get("trader", ""),
                is_mev,
                trade.get("type", "swap"),
                now_iso,
            ))
        self.db.conn.commit()

    def _collect_router_stats(self):
        """采集路由器交易量统计。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        sources = self.client.fetch_router_volume()

        for source in sources:
            router = source.get("name", "unknown")
            volume = float(source.get("volume24h", 0) or 0)
            count = int(source.get("tradeCount", 0) or 0)
            avg_size = volume / count if count > 0 else 0

            self.db.conn.execute("""
                INSERT OR REPLACE INTO dex_router_stats
                (router, volume_24h_usd, trade_count, avg_trade_size,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (router, volume, count, avg_size, now_iso, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 DEX 交易流上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 大额交易
        cursor = self.db.conn.execute("""
            SELECT timestamp, token_in, token_out, amount_usd, router,
                   dex_venue, is_mev_victim, trade_type
            FROM dex_large_trades
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY amount_usd DESC LIMIT 20
        """)
        trade_rows = cursor.fetchall()

        # 路由器统计
        cursor = self.db.conn.execute("""
            SELECT router, volume_24h_usd, trade_count, avg_trade_size
            FROM dex_router_stats
            ORDER BY timestamp DESC LIMIT 10
        """)
        router_rows = cursor.fetchall()

        if not trade_rows and not router_rows:
            return {"status": "no_data", "as_of": now_iso}

        large_trades = []
        for row in trade_rows:
            large_trades.append({
                "timestamp": row[0],
                "token_in": row[1],
                "token_out": row[2],
                "amount_usd": round(row[3], 2),
                "router": row[4],
                "dex_venue": row[5],
                "is_mev_victim": bool(row[6]),
                "trade_type": row[7],
            })

        router_stats = {}
        for row in router_rows:
            router_stats[row[0]] = {
                "volume_24h_usd": round(row[1], 2),
                "trade_count": row[2],
                "avg_trade_size": round(row[3], 2),
            }

        mev_count = sum(1 for t in large_trades if t["is_mev_victim"])
        total_volume = sum(t["amount_usd"] for t in large_trades)

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "market_signal": {
                "total_large_trade_volume_usd": round(total_volume, 2),
                "large_trade_count": len(large_trades),
                "mev_victim_count": mev_count,
                "mev_victim_pct": round(mev_count / max(len(large_trades), 1) * 100, 2),
            },
            "large_trades": large_trades[:10],
            "router_stats": router_stats,
        }

    def build_scheduler(self):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="dex_trade_flow_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="dex_trade_flow_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
