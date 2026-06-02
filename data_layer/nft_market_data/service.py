"""nft_market_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.nft_market_data.client import NftMarketClient


class NftMarketDataService:
    """NFT 市场数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or NftMarketClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS nft_collection_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                floor_price_eth REAL DEFAULT 0,
                volume_24h_eth REAL DEFAULT 0,
                sales_count INTEGER DEFAULT 0,
                unique_buyers INTEGER DEFAULT 0,
                unique_sellers INTEGER DEFAULT 0,
                wash_trade_pct REAL DEFAULT 0,
                listed_pct REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(collection, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS nft_market_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_volume_24h_eth REAL DEFAULT 0,
                total_sales_count INTEGER DEFAULT 0,
                blue_chip_index REAL DEFAULT 0,
                avg_floor_change_pct REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_collection_stats_time
            ON nft_collection_stats(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_nft_market_metrics_time
            ON nft_market_metrics(timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("nft_market_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 bootstrap NFT 市场数据")
        self._collect_collections()
        self._compute_market_metrics()
        logger.info("bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_collections()
        self._compute_market_metrics()
        logger.info("collect_once 完成")

    def _collect_collections(self):
        """采集 Top NFT 集合数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        collections = self.client.fetch_top_collections(limit=50)

        for col in collections:
            name = col.get("name", col.get("slug", "unknown"))
            floor_price = float(col.get("floorAsk", {}).get("price", {}).get("amount", {}).get("native", 0) or 0)
            volume_24h = float(col.get("volume", {}).get("1day", 0) or 0)
            sales_count = int(col.get("salesCount", {}).get("1day", 0) or 0)
            unique_buyers = int(col.get("uniqueBuyers", 0) or 0)
            unique_sellers = int(col.get("uniqueSellers", 0) or 0)
            wash_trade_pct = float(col.get("washTradingPercentage", 0) or 0)
            listed_pct = float(col.get("listedPercentage", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO nft_collection_stats
                (collection, floor_price_eth, volume_24h_eth, sales_count,
                 unique_buyers, unique_sellers, wash_trade_pct, listed_pct,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, floor_price, volume_24h, sales_count,
                  unique_buyers, unique_sellers, wash_trade_pct, listed_pct,
                  now_iso, now_iso))
        self.db.conn.commit()

    def _compute_market_metrics(self):
        """计算 NFT 市场整体指标。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        cursor = self.db.conn.execute("""
            SELECT SUM(volume_24h_eth), SUM(sales_count), AVG(floor_price_eth)
            FROM nft_collection_stats
            WHERE timestamp >= datetime('now', '-1 day')
        """)
        row = cursor.fetchone()

        total_volume = float(row[0] or 0)
        total_sales = int(row[1] or 0)
        avg_floor = float(row[2] or 0)

        # Blue chip index: 简化为 top 10 集合平均地板价
        cursor = self.db.conn.execute("""
            SELECT AVG(floor_price_eth)
            FROM (
                SELECT floor_price_eth FROM nft_collection_stats
                WHERE timestamp >= datetime('now', '-1 day')
                ORDER BY volume_24h_eth DESC LIMIT 10
            )
        """)
        blue_chip_row = cursor.fetchone()
        blue_chip_index = float(blue_chip_row[0] or 0)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO nft_market_metrics
            (total_volume_24h_eth, total_sales_count, blue_chip_index,
             avg_floor_change_pct, timestamp, collected_at)
            VALUES (?, ?, ?, 0, ?, ?)
        """, (total_volume, total_sales, blue_chip_index, now_iso, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 NFT 市场上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 市场指标
        cursor = self.db.conn.execute("""
            SELECT total_volume_24h_eth, total_sales_count, blue_chip_index,
                   avg_floor_change_pct
            FROM nft_market_metrics
            ORDER BY timestamp DESC LIMIT 1
        """)
        metrics_row = cursor.fetchone()

        # Top 集合
        cursor = self.db.conn.execute("""
            SELECT collection, floor_price_eth, volume_24h_eth, sales_count,
                   wash_trade_pct
            FROM nft_collection_stats
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY volume_24h_eth DESC LIMIT 10
        """)
        collection_rows = cursor.fetchall()

        if not metrics_row and not collection_rows:
            return {"status": "no_data", "as_of": now_iso}

        top_collections = []
        for row in collection_rows:
            top_collections.append({
                "collection": row[0],
                "floor_price_eth": round(row[1], 4),
                "volume_24h_eth": round(row[2], 2),
                "sales_count": row[3],
                "wash_trade_pct": round(row[4], 2),
            })

        market_metrics = {}
        if metrics_row:
            market_metrics = {
                "total_volume_24h_eth": round(metrics_row[0], 2),
                "total_sales_count": metrics_row[1],
                "blue_chip_index": round(metrics_row[2], 4),
                "avg_floor_change_pct": round(metrics_row[3], 2),
            }

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "market_metrics": market_metrics,
            "top_collections": top_collections,
            "coverage": {
                "collections_tracked": len(collection_rows),
            },
        }

    def build_scheduler(self):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="nft_market_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="nft_market_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
