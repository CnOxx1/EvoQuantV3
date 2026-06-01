"""mev_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.mev_data.client import MevDataClient


class MevDataService:
    """MEV 数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or MevDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS mev_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_number INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                mev_reward_eth REAL DEFAULT 0,
                mev_reward_usd REAL DEFAULT 0,
                sandwich_count INTEGER DEFAULT 0,
                arb_count INTEGER DEFAULT 0,
                liquidation_count INTEGER DEFAULT 0,
                builder TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(block_number)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS mev_agg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                interval TEXT NOT NULL,
                total_mev_usd REAL DEFAULT 0,
                sandwich_volume_usd REAL DEFAULT 0,
                arb_volume_usd REAL DEFAULT 0,
                liquidation_mev_usd REAL DEFAULT 0,
                avg_mev_per_block REAL DEFAULT 0,
                builder_hhi REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(ts, interval)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mev_blocks_number
            ON mev_blocks(block_number DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mev_agg_ts
            ON mev_agg(ts DESC, interval)
        """)
        self.db.conn.commit()
        logger.info("mev_data 存储初始化完成")

    def bootstrap(self):
        """首次回填。"""
        logger.info("开始 mev_data bootstrap")
        self._collect_flashbots()
        self._collect_eigenphi()
        self._compute_aggregations()
        logger.info("mev_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_flashbots()
        self._collect_eigenphi()
        self._compute_aggregations()
        logger.info("mev_data collect_once 完成")

    def _collect_flashbots(self):
        """从 Flashbots 采集 MEV 区块数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        blocks = self.client.fetch_flashbots_blocks(limit=100)

        if not blocks:
            logger.warning("Flashbots 未返回数据")
            return

        for block in blocks:
            block_number = int(block.get("block_number", 0))
            if block_number == 0:
                continue

            slot_ts = block.get("slot", "")
            value_wei = int(block.get("value", 0) or 0)
            mev_reward_eth = value_wei / 1e18
            builder_pubkey = block.get("builder_pubkey", "")[:16]

            self.db.conn.execute("""
                INSERT OR REPLACE INTO mev_blocks
                (block_number, timestamp, mev_reward_eth, mev_reward_usd,
                 sandwich_count, arb_count, liquidation_count, builder, collected_at)
                VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?)
            """, (block_number, slot_ts or now_iso, mev_reward_eth,
                  mev_reward_eth * 3500, builder_pubkey, now_iso))
        self.db.conn.commit()
        logger.info(f"Flashbots 采集完成，处理 {len(blocks)} 个区块")

    def _collect_eigenphi(self):
        """从 EigenPhi 采集 MEV 分析数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        summary = self.client.fetch_eigenphi_mev_summary(timeframe="1h")
        if not summary:
            logger.debug("EigenPhi 汇总数据为空，跳过")
            return

        sandwiches = self.client.fetch_eigenphi_sandwich(limit=50)
        sandwich_count = len(sandwiches)

        # 更新最近区块的 sandwich/arb 计数
        if sandwich_count > 0:
            cursor = self.db.conn.execute("""
                SELECT block_number FROM mev_blocks
                ORDER BY block_number DESC LIMIT ?
            """, (sandwich_count,))
            recent_blocks = [row[0] for row in cursor.fetchall()]

            if recent_blocks:
                avg_sandwich = max(1, sandwich_count // len(recent_blocks))
                for bn in recent_blocks:
                    self.db.conn.execute("""
                        UPDATE mev_blocks SET sandwich_count = ?
                        WHERE block_number = ?
                    """, (avg_sandwich, bn))

        self.db.conn.commit()
        logger.info(f"EigenPhi 采集完成，sandwich_count={sandwich_count}")

    def _compute_aggregations(self):
        """计算小时级聚合数据。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        day_ago = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

        for interval, start_ts in [("1h", hour_ago), ("24h", day_ago)]:
            cursor = self.db.conn.execute("""
                SELECT
                    COUNT(*) as cnt,
                    COALESCE(SUM(mev_reward_usd), 0) as total_usd,
                    COALESCE(SUM(sandwich_count), 0) as sandwiches,
                    COALESCE(SUM(arb_count), 0) as arbs,
                    COALESCE(SUM(liquidation_count), 0) as liqs,
                    COALESCE(AVG(mev_reward_usd), 0) as avg_mev
                FROM mev_blocks
                WHERE timestamp >= ?
            """, (start_ts,))
            row = cursor.fetchone()

            if not row or row[0] == 0:
                continue

            cnt, total_usd, sandwiches, arbs, liqs, avg_mev = row

            # 计算 Builder HHI（赫芬达尔指数）
            builder_cursor = self.db.conn.execute("""
                SELECT builder, COUNT(*) as block_count
                FROM mev_blocks
                WHERE timestamp >= ? AND builder != ''
                GROUP BY builder
            """, (start_ts,))
            builder_rows = builder_cursor.fetchall()

            hhi = 0.0
            if builder_rows:
                total_blocks = sum(r[1] for r in builder_rows)
                if total_blocks > 0:
                    hhi = sum((r[1] / total_blocks) ** 2 for r in builder_rows)

            # 估算各类 MEV 的 USD 占比
            sandwich_vol = (sandwiches / max(cnt, 1)) * total_usd * 0.4
            arb_vol = (arbs / max(cnt, 1)) * total_usd * 0.35
            liq_vol = (liqs / max(cnt, 1)) * total_usd * 0.25

            self.db.conn.execute("""
                INSERT OR REPLACE INTO mev_agg
                (ts, interval, total_mev_usd, sandwich_volume_usd,
                 arb_volume_usd, liquidation_mev_usd, avg_mev_per_block,
                 builder_hhi, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_iso, interval, total_usd, sandwich_vol, arb_vol,
                  liq_vol, avg_mev, round(hhi, 4), now_iso))

        self.db.conn.commit()
        logger.info("MEV 聚合计算完成")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 MEV 上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取 1h 和 24h 聚合
        cursor = self.db.conn.execute("""
            SELECT interval, total_mev_usd, sandwich_volume_usd, arb_volume_usd,
                   liquidation_mev_usd, avg_mev_per_block, builder_hhi
            FROM mev_agg
            WHERE interval IN ('1h', '24h')
            ORDER BY ts DESC
            LIMIT 2
        """)
        agg_rows = cursor.fetchall()

        if not agg_rows:
            return {"status": "no_data", "as_of": now_iso}

        agg_data = {}
        for row in agg_rows:
            interval = row[0]
            agg_data[interval] = {
                "total_mev_usd": round(row[1], 2),
                "sandwich_volume_usd": round(row[2], 2),
                "arb_volume_usd": round(row[3], 2),
                "liquidation_mev_usd": round(row[4], 2),
                "avg_mev_per_block": round(row[5], 4),
                "builder_hhi": round(row[6], 4),
            }

        # MEV 提取量趋势
        mev_1h = agg_data.get("1h", {}).get("total_mev_usd", 0)
        mev_24h = agg_data.get("24h", {}).get("total_mev_usd", 0)
        hourly_avg_24h = mev_24h / 24 if mev_24h > 0 else 0
        mev_trend = "rising" if mev_1h > hourly_avg_24h * 1.2 else (
            "falling" if mev_1h < hourly_avg_24h * 0.8 else "stable"
        )

        # 三明治攻击频率（散户压力指标）
        sandwich_1h = agg_data.get("1h", {}).get("sandwich_volume_usd", 0)
        sandwich_ratio = sandwich_1h / mev_1h if mev_1h > 0 else 0
        retail_pressure = "high" if sandwich_ratio > 0.5 else (
            "moderate" if sandwich_ratio > 0.25 else "low"
        )

        # 清算 MEV 占比（DeFi 压力指标）
        liq_1h = agg_data.get("1h", {}).get("liquidation_mev_usd", 0)
        liq_ratio = liq_1h / mev_1h if mev_1h > 0 else 0
        defi_stress = "high" if liq_ratio > 0.3 else (
            "moderate" if liq_ratio > 0.15 else "low"
        )

        # Builder 集中度（HHI）
        hhi = agg_data.get("1h", {}).get("builder_hhi", 0)
        centralization = "high" if hhi > 0.25 else (
            "moderate" if hhi > 0.15 else "low"
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "mev_extraction_trend": mev_trend,
                "retail_pressure_sandwich": retail_pressure,
                "defi_stress_liquidation": defi_stress,
                "builder_centralization_hhi": centralization,
            },
            "aggregations": agg_data,
            "interpretation": {
                "mev_trend": f"1h/24h MEV 提取量趋势: {mev_trend}",
                "sandwich_freq": f"三明治攻击频率（散户压力指标）: {retail_pressure}",
                "liquidation_share": f"清算 MEV 占比（DeFi 压力指标）: {defi_stress}",
                "builder_hhi": f"Builder 集中度（HHI={hhi:.4f}）: {centralization}",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="mev_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="mev_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
