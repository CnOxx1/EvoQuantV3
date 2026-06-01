"""DEX 流动性数据服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.dex_liquidity_data.client import DexLiquidityClient


class DexLiquidityService:
    """DEX 流动性池数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or DexLiquidityClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS dex_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                pool_address TEXT NOT NULL,
                token0 TEXT NOT NULL,
                token1 TEXT NOT NULL,
                tvl_usd REAL DEFAULT 0,
                volume_24h_usd REAL DEFAULT 0,
                fee_tier REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, pool_address, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS dex_tick_liquidity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pool_address TEXT NOT NULL,
                tick_lower INTEGER NOT NULL,
                tick_upper INTEGER NOT NULL,
                liquidity_usd REAL DEFAULT 0,
                price_range_low REAL DEFAULT 0,
                price_range_high REAL DEFAULT 0,
                collected_at TEXT NOT NULL
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS dex_liquidity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                pool_address TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount_usd REAL DEFAULT 0,
                sender TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                tx_hash TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(tx_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dex_pools_protocol
            ON dex_pools(protocol, collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dex_events_pool
            ON dex_liquidity_events(pool_address, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("dex_liquidity_data 存储初始化完成")

    def bootstrap(self):
        """首次回填：采集所有池子 + tick 数据。"""
        logger.info("开始 dex_liquidity_data bootstrap")
        self._collect_uniswap()
        self._collect_curve()
        logger.info("dex_liquidity_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期：池快照 + 最近事件。"""
        self._collect_uniswap()
        self._collect_curve()
        logger.info("dex_liquidity_data collect_once 完成")

    def _collect_uniswap(self):
        """从 Uniswap V3 采集 Top 池、tick 分布和流动性事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        pools = self.client.fetch_uniswap_pools(first=50)

        if not pools:
            logger.warning("Uniswap V3 未返回池数据")
            return

        for pool in pools:
            pool_address = pool.get("id", "")
            token0 = pool.get("token0", {}).get("symbol", "")
            token1 = pool.get("token1", {}).get("symbol", "")
            tvl_usd = float(pool.get("totalValueLockedUSD", 0))
            volume_usd = float(pool.get("volumeUSD", 0))
            fee_tier = int(pool.get("feeTier", 0)) / 1_000_000

            self.db.conn.execute("""
                INSERT OR IGNORE INTO dex_pools
                (protocol, pool_address, token0, token1, tvl_usd,
                 volume_24h_usd, fee_tier, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("uniswap_v3", pool_address, token0, token1,
                  tvl_usd, volume_usd, fee_tier, now_iso))

        self.db.conn.commit()
        logger.info(f"Uniswap V3 池快照采集完成，共 {len(pools)} 个池")

        # 采集 Top 5 池的 tick 分布
        top_pools = pools[:5]
        for pool in top_pools:
            pool_id = pool.get("id", "")
            ticks = self.client.fetch_uniswap_pool_ticks(pool_id, first=100)
            for tick in ticks:
                tick_idx = int(tick.get("tickIdx", 0))
                liq_gross = float(tick.get("liquidityGross", 0))
                price0 = float(tick.get("price0", 0))
                price1 = float(tick.get("price1", 0))

                self.db.conn.execute("""
                    INSERT INTO dex_tick_liquidity
                    (pool_address, tick_lower, tick_upper, liquidity_usd,
                     price_range_low, price_range_high, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (pool_id, tick_idx, tick_idx + 60, liq_gross,
                      price0, price1, now_iso))

        self.db.conn.commit()

        # 采集 Top 5 池的流动性事件
        for pool in top_pools:
            pool_id = pool.get("id", "")
            events = self.client.fetch_uniswap_mints_burns(pool_id, first=50)

            for mint in events.get("mints", []):
                tx_hash = mint.get("transaction", {}).get("id", "")
                if not tx_hash:
                    continue
                self.db.conn.execute("""
                    INSERT OR IGNORE INTO dex_liquidity_events
                    (protocol, pool_address, event_type, amount_usd,
                     sender, timestamp, tx_hash, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, ("uniswap_v3", pool_id, "mint",
                      float(mint.get("amountUSD", 0)),
                      mint.get("sender", ""), mint.get("timestamp", ""),
                      tx_hash, now_iso))

            for burn in events.get("burns", []):
                tx_hash = burn.get("transaction", {}).get("id", "")
                if not tx_hash:
                    continue
                self.db.conn.execute("""
                    INSERT OR IGNORE INTO dex_liquidity_events
                    (protocol, pool_address, event_type, amount_usd,
                     sender, timestamp, tx_hash, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, ("uniswap_v3", pool_id, "burn",
                      float(burn.get("amountUSD", 0)),
                      burn.get("owner", ""), burn.get("timestamp", ""),
                      tx_hash, now_iso))

        self.db.conn.commit()
        logger.info("Uniswap V3 tick + 事件采集完成")

    def _collect_curve(self):
        """从 Curve 采集流动性池数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        pools = self.client.fetch_curve_pools(first=50)

        if not pools:
            logger.warning("Curve 未返回池数据")
            return

        for pool in pools:
            pool_address = pool.get("id", "")
            name = pool.get("name", "")
            coins = pool.get("coins", [])
            token0 = coins[0] if len(coins) > 0 else ""
            token1 = coins[1] if len(coins) > 1 else ""
            tvl_usd = float(pool.get("totalValueLockedUSD", 0))
            volume_usd = float(pool.get("volumeUSD", 0))

            self.db.conn.execute("""
                INSERT OR IGNORE INTO dex_pools
                (protocol, pool_address, token0, token1, tvl_usd,
                 volume_24h_usd, fee_tier, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("curve", pool_address, token0, token1,
                  tvl_usd, volume_usd, 0.0004, now_iso))

        self.db.conn.commit()
        logger.info(f"Curve 池快照采集完成，共 {len(pools)} 个池")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 DEX 流动性上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # TVL 分布统计
        cursor = self.db.conn.execute("""
            SELECT protocol, COUNT(*) as pool_count,
                   COALESCE(SUM(tvl_usd), 0) as total_tvl,
                   COALESCE(AVG(tvl_usd), 0) as avg_tvl,
                   COALESCE(MAX(tvl_usd), 0) as max_tvl
            FROM dex_pools
            WHERE collected_at = (SELECT MAX(collected_at) FROM dex_pools)
            GROUP BY protocol
        """)
        tvl_rows = cursor.fetchall()

        if not tvl_rows:
            return {"status": "no_data", "as_of": now_iso}

        tvl_distribution = {}
        for row in tvl_rows:
            tvl_distribution[row[0]] = {
                "pool_count": row[1],
                "total_tvl_usd": round(row[2], 2),
                "avg_tvl_usd": round(row[3], 2),
                "max_tvl_usd": round(row[4], 2),
            }

        # 流动性集中度指标（Top 5 池占比）
        cursor = self.db.conn.execute("""
            SELECT SUM(tvl_usd) FROM dex_pools
            WHERE collected_at = (SELECT MAX(collected_at) FROM dex_pools)
        """)
        total_tvl = cursor.fetchone()[0] or 1

        cursor = self.db.conn.execute("""
            SELECT tvl_usd FROM dex_pools
            WHERE collected_at = (SELECT MAX(collected_at) FROM dex_pools)
            ORDER BY tvl_usd DESC LIMIT 5
        """)
        top5_tvl = sum(row[0] for row in cursor.fetchall())
        concentration_ratio = top5_tvl / total_tvl if total_tvl > 0 else 0

        # 大额流动性事件（最近 24h 内 > $100k 的事件）
        cursor = self.db.conn.execute("""
            SELECT protocol, pool_address, event_type, amount_usd, sender, timestamp
            FROM dex_liquidity_events
            WHERE amount_usd > 100000
            ORDER BY timestamp DESC LIMIT 20
        """)
        large_events = []
        for row in cursor.fetchall():
            large_events.append({
                "protocol": row[0],
                "pool_address": row[1],
                "event_type": row[2],
                "amount_usd": round(row[3], 2),
                "sender": row[4],
                "timestamp": row[5],
            })

        # 流动性集中度评级
        concentration_level = "high" if concentration_ratio > 0.6 else (
            "moderate" if concentration_ratio > 0.35 else "low"
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "tvl_concentration": concentration_level,
                "top5_tvl_ratio": round(concentration_ratio, 4),
                "large_event_count": len(large_events),
            },
            "tvl_distribution": tvl_distribution,
            "large_liquidity_events": large_events,
            "interpretation": {
                "concentration": f"Top 5 池 TVL 占比: {concentration_ratio:.2%}，集中度: {concentration_level}",
                "large_events": f"近期大额流动性事件: {len(large_events)} 笔 (>$100k)",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 20 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=20,
            id="dex_liquidity_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 20 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=20,
            id="dex_liquidity_collect",
        )
        return scheduler

    def close(self):
        """关闭客户端连接。"""
        self.client.close()
