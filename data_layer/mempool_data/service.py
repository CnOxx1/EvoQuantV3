"""mempool_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.mempool_data.client import MempoolDataClient


class MempoolDataService:
    """比特币内存池数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or MempoolDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS mempool_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                pending_count INTEGER DEFAULT 0,
                pending_vsize_mb REAL DEFAULT 0,
                fee_rate_fastest REAL DEFAULT 0,
                fee_rate_median REAL DEFAULT 0,
                fee_rate_slow REAL DEFAULT 0,
                large_tx_count INTEGER DEFAULT 0,
                large_tx_total_value REAL DEFAULT 0,
                UNIQUE(timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_large_txs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txid TEXT NOT NULL,
                value_btc REAL DEFAULT 0,
                fee_rate REAL DEFAULT 0,
                vsize INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(txid, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mempool_snapshots_ts
            ON mempool_snapshots(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_large_txs_collected
            ON pending_large_txs(collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("mempool_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 mempool_data bootstrap")
        self._collect_mempool()
        logger.info("mempool_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_mempool()
        logger.info("mempool_data collect_once 完成")

    def _collect_mempool(self):
        """采集内存池快照和大额交易数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取内存池统计
        stats = self.client.fetch_mempool_stats()
        fees = self.client.fetch_recommended_fees()
        large_txs = self.client.fetch_pending_large_txs(min_value_btc=10)

        pending_count = stats.get("count", 0)
        vsize_bytes = stats.get("vsize", 0)
        pending_vsize_mb = round(vsize_bytes / (1024 * 1024), 4)

        fee_rate_fastest = float(fees.get("fastestFee", 0))
        fee_rate_median = float(fees.get("halfHourFee", 0))
        fee_rate_slow = float(fees.get("hourFee", 0))

        # 计算大额交易汇总
        large_tx_count = len(large_txs)
        large_tx_total_value = round(
            sum(tx.get("value", 0) for tx in large_txs) / 1e8, 8
        )

        # 写入快照
        self.db.conn.execute("""
            INSERT OR REPLACE INTO mempool_snapshots
            (timestamp, pending_count, pending_vsize_mb,
             fee_rate_fastest, fee_rate_median, fee_rate_slow,
             large_tx_count, large_tx_total_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_iso, pending_count, pending_vsize_mb,
              fee_rate_fastest, fee_rate_median, fee_rate_slow,
              large_tx_count, large_tx_total_value))

        # 写入大额交易明细
        for tx in large_txs:
            txid = tx.get("txid", "")
            value_btc = round(tx.get("value", 0) / 1e8, 8)
            fee_rate = float(tx.get("rate", 0))
            vsize = int(tx.get("vsize", 0))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO pending_large_txs
                (txid, value_btc, fee_rate, vsize, collected_at)
                VALUES (?, ?, ?, ?, ?)
            """, (txid, value_btc, fee_rate, vsize, now_iso))

        self.db.conn.commit()
        logger.info(
            f"mempool_data 采集完成: pending={pending_count}, "
            f"vsize={pending_vsize_mb}MB, large_txs={large_tx_count}"
        )

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的内存池压力上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新快照
        cursor = self.db.conn.execute("""
            SELECT timestamp, pending_count, pending_vsize_mb,
                   fee_rate_fastest, fee_rate_median, fee_rate_slow,
                   large_tx_count, large_tx_total_value
            FROM mempool_snapshots
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            return {"status": "no_data", "as_of": now_iso}

        snapshot = {
            "timestamp": row[0],
            "pending_count": row[1],
            "pending_vsize_mb": row[2],
            "fee_rate_fastest": row[3],
            "fee_rate_median": row[4],
            "fee_rate_slow": row[5],
            "large_tx_count": row[6],
            "large_tx_total_value": row[7],
        }

        # 获取最近大额交易
        tx_cursor = self.db.conn.execute("""
            SELECT txid, value_btc, fee_rate, vsize
            FROM pending_large_txs
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM pending_large_txs
            )
            ORDER BY value_btc DESC
            LIMIT 20
        """)
        large_txs = [
            {
                "txid": r[0],
                "value_btc": r[1],
                "fee_rate": r[2],
                "vsize": r[3],
            }
            for r in tx_cursor.fetchall()
        ]

        # 费率趋势（最近 10 条快照）
        trend_cursor = self.db.conn.execute("""
            SELECT timestamp, fee_rate_fastest, fee_rate_median, fee_rate_slow
            FROM mempool_snapshots
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        fee_trend = [
            {
                "timestamp": r[0],
                "fastest": r[1],
                "median": r[2],
                "slow": r[3],
            }
            for r in trend_cursor.fetchall()
        ]

        # 计算压力指数 (简单归一化)
        pressure_index = min(
            round(snapshot["pending_vsize_mb"] / 300, 4), 1.0
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "mempool_pressure": {
                "current_snapshot": snapshot,
                "pressure_index": pressure_index,
                "fee_trend": fee_trend,
                "pending_large_txs": large_txs,
            },
            "interpretation": {
                "pressure_index": "0-1 归一化值，基于 vsize/300MB 阈值",
                "fee_trend": "最近 10 次快照的费率变化趋势",
                "large_txs": "当前内存池中价值 >= 10 BTC 的待确认交易",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 1 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=1,
            id="mempool_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 1 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=1,
            id="mempool_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
