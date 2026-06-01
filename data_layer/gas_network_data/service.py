"""gas_network_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.gas_network_data.client import GasNetworkClient


class GasNetworkService:
    """Gas 与网络拥堵数据采集与分析服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or GasNetworkClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS gas_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_fee_gwei REAL NOT NULL,
                priority_fee_gwei REAL DEFAULT 0,
                gas_used_ratio REAL DEFAULT 0,
                block_number INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(block_number)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS network_congestion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pending_tx_count INTEGER DEFAULT 0,
                block_utilization_pct REAL DEFAULT 0,
                avg_wait_seconds REAL DEFAULT 0,
                congestion_level TEXT DEFAULT 'low',
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS gas_spikes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_number INTEGER NOT NULL,
                base_fee_gwei REAL NOT NULL,
                spike_ratio REAL DEFAULT 0,
                probable_cause TEXT DEFAULT 'unknown',
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(block_number)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gas_prices_block
            ON gas_prices(block_number DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_network_congestion_ts
            ON network_congestion(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gas_spikes_block
            ON gas_spikes(block_number DESC)
        """)
        self.db.conn.commit()
        logger.info("gas_network_data 存储初始化完成")

    def bootstrap(self):
        """首次回填：采集近期 Gas 历史数据。"""
        logger.info("开始 gas_network_data bootstrap")
        self._collect_gas_prices()
        self._collect_congestion()
        self._detect_spikes()
        logger.info("gas_network_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期：Gas 价格 + 拥堵状态 + 突增检测。"""
        self._collect_gas_prices()
        self._collect_congestion()
        self._detect_spikes()
        logger.info("gas_network_data collect_once 完成")

    def _collect_gas_prices(self):
        """从 Etherscan / Blocknative 采集当前 Gas 价格。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 优先使用 Etherscan Gas Oracle
        oracle = self.client.fetch_etherscan_gas_oracle()
        if oracle and isinstance(oracle, dict):
            try:
                base_fee = float(oracle.get("suggestBaseFee", 0))
                priority_fee = float(oracle.get("FastGasPrice", 0)) - base_fee
                gas_used_ratio = float(oracle.get("gasUsedRatio", "0").split(",")[0])
                block_number = int(oracle.get("LastBlock", 0))

                if block_number > 0:
                    self.db.conn.execute("""
                        INSERT OR REPLACE INTO gas_prices
                        (base_fee_gwei, priority_fee_gwei, gas_used_ratio,
                         block_number, timestamp, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (base_fee, max(priority_fee, 0), gas_used_ratio,
                          block_number, now_iso, now_iso))
                    self.db.conn.commit()
                    logger.info(f"Gas 价格采集完成: base={base_fee:.2f} gwei, block={block_number}")
                    return
            except (ValueError, TypeError) as e:
                logger.warning(f"Etherscan Gas Oracle 数据解析失败: {e}")

        # 备用：Blocknative
        bn_data = self.client.fetch_blocknative_gas()
        if bn_data:
            try:
                block_prices = bn_data.get("blockPrices", [])
                if block_prices:
                    latest = block_prices[0]
                    base_fee = float(latest.get("baseFeePerGas", 0))
                    block_number = int(latest.get("blockNumber", 0))
                    # 从估算价格中提取 priority fee
                    estimated = latest.get("estimatedPrices", [])
                    priority_fee = float(estimated[0].get("maxPriorityFeePerGas", 0)) if estimated else 0

                    if block_number > 0:
                        self.db.conn.execute("""
                            INSERT OR REPLACE INTO gas_prices
                            (base_fee_gwei, priority_fee_gwei, gas_used_ratio,
                             block_number, timestamp, collected_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (base_fee, priority_fee, 0.0, block_number, now_iso, now_iso))
                        self.db.conn.commit()
                        logger.info(f"Blocknative Gas 采集完成: base={base_fee:.2f} gwei")
                        return
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Blocknative Gas 数据解析失败: {e}")

        logger.warning("Gas 价格采集失败：所有数据源均无有效数据")

    def _collect_congestion(self):
        """采集网络拥堵状态：pending 交易数 + mempool 统计。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        pending_count = self.client.fetch_pending_tx_count()
        mempool = self.client.fetch_blocknative_mempool_stats()

        # 从最近 gas_prices 获取 block utilization
        cursor = self.db.conn.execute("""
            SELECT gas_used_ratio FROM gas_prices
            ORDER BY block_number DESC LIMIT 1
        """)
        row = cursor.fetchone()
        block_utilization = row[0] * 100 if row else 0.0

        # 估算平均等待时间（基于 pending 数量）
        if pending_count > 10000:
            avg_wait = 60.0
        elif pending_count > 5000:
            avg_wait = 30.0
        elif pending_count > 2000:
            avg_wait = 15.0
        else:
            avg_wait = 6.0

        # 如果 Blocknative 有 mempool 数据，使用更精确的值
        if mempool:
            avg_wait = float(mempool.get("avgWaitSeconds", avg_wait))
            pending_count = pending_count or int(mempool.get("pendingCount", 0))

        # 计算拥堵等级
        if block_utilization > 95 or pending_count > 10000:
            congestion_level = "extreme"
        elif block_utilization > 80 or pending_count > 5000:
            congestion_level = "high"
        elif block_utilization > 50 or pending_count > 2000:
            congestion_level = "moderate"
        else:
            congestion_level = "low"

        self.db.conn.execute("""
            INSERT OR REPLACE INTO network_congestion
            (pending_tx_count, block_utilization_pct, avg_wait_seconds,
             congestion_level, timestamp, collected_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pending_count, block_utilization, avg_wait,
              congestion_level, now_iso, now_iso))
        self.db.conn.commit()
        logger.info(f"网络拥堵采集完成: level={congestion_level}, pending={pending_count}")

    def _detect_spikes(self):
        """检测 Gas 突增：当前 base fee 超过 1h 均值 2 倍时标记。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取 1h 内平均 base fee
        cursor = self.db.conn.execute("""
            SELECT AVG(base_fee_gwei) FROM gas_prices
            WHERE timestamp >= ?
        """, (hour_ago,))
        row = cursor.fetchone()
        avg_base_fee = row[0] if row and row[0] else None

        if avg_base_fee is None or avg_base_fee == 0:
            return

        # 获取最新 base fee
        cursor = self.db.conn.execute("""
            SELECT base_fee_gwei, block_number FROM gas_prices
            ORDER BY block_number DESC LIMIT 1
        """)
        latest = cursor.fetchone()
        if not latest:
            return

        current_fee, block_number = latest
        spike_ratio = current_fee / avg_base_fee

        # 超过 2 倍均值视为 spike
        if spike_ratio >= 2.0:
            # 推测原因
            if spike_ratio > 5.0:
                probable_cause = "NFT mint / airdrop"
            elif spike_ratio > 3.0:
                probable_cause = "liquidation cascade"
            else:
                probable_cause = "unknown"

            self.db.conn.execute("""
                INSERT OR REPLACE INTO gas_spikes
                (block_number, base_fee_gwei, spike_ratio, probable_cause,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (block_number, current_fee, round(spike_ratio, 2),
                  probable_cause, now_iso, now_iso))
            self.db.conn.commit()
            logger.warning(
                f"Gas 突增检测: block={block_number}, "
                f"fee={current_fee:.2f} gwei, ratio={spike_ratio:.2f}x, "
                f"cause={probable_cause}"
            )

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 Gas 与网络拥堵上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新 Gas 价格
        cursor = self.db.conn.execute("""
            SELECT base_fee_gwei, priority_fee_gwei, gas_used_ratio, block_number
            FROM gas_prices ORDER BY block_number DESC LIMIT 1
        """)
        gas_row = cursor.fetchone()

        # 获取最新拥堵状态
        cursor = self.db.conn.execute("""
            SELECT pending_tx_count, block_utilization_pct, avg_wait_seconds, congestion_level
            FROM network_congestion ORDER BY timestamp DESC LIMIT 1
        """)
        congestion_row = cursor.fetchone()

        # 获取近期 spikes（24h 内）
        day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        cursor = self.db.conn.execute("""
            SELECT block_number, base_fee_gwei, spike_ratio, probable_cause, timestamp
            FROM gas_spikes WHERE timestamp >= ?
            ORDER BY timestamp DESC LIMIT 10
        """, (day_ago,))
        spike_rows = cursor.fetchall()

        if not gas_row and not congestion_row:
            return {"status": "no_data", "as_of": now_iso}

        # Gas 趋势：对比最近 5 条记录
        cursor = self.db.conn.execute("""
            SELECT base_fee_gwei FROM gas_prices
            ORDER BY block_number DESC LIMIT 5
        """)
        recent_fees = [r[0] for r in cursor.fetchall()]
        if len(recent_fees) >= 2:
            if recent_fees[0] > recent_fees[-1] * 1.2:
                gas_trend = "rising"
            elif recent_fees[0] < recent_fees[-1] * 0.8:
                gas_trend = "falling"
            else:
                gas_trend = "stable"
        else:
            gas_trend = "insufficient_data"

        # 构建 bundle
        gas_level = "unknown"
        if gas_row:
            base_fee = gas_row[0]
            if base_fee > 100:
                gas_level = "very_high"
            elif base_fee > 50:
                gas_level = "high"
            elif base_fee > 20:
                gas_level = "moderate"
            else:
                gas_level = "low"

        return {
            "status": "ready",
            "as_of": now_iso,
            "current_gas": {
                "base_fee_gwei": round(gas_row[0], 2) if gas_row else None,
                "priority_fee_gwei": round(gas_row[1], 2) if gas_row else None,
                "gas_used_ratio": round(gas_row[2], 4) if gas_row else None,
                "block_number": gas_row[3] if gas_row else None,
                "level": gas_level,
            },
            "congestion": {
                "pending_tx_count": congestion_row[0] if congestion_row else None,
                "block_utilization_pct": round(congestion_row[1], 2) if congestion_row else None,
                "avg_wait_seconds": round(congestion_row[2], 1) if congestion_row else None,
                "congestion_level": congestion_row[3] if congestion_row else None,
            },
            "recent_spikes": [
                {
                    "block_number": s[0],
                    "base_fee_gwei": round(s[1], 2),
                    "spike_ratio": s[2],
                    "probable_cause": s[3],
                    "timestamp": s[4],
                }
                for s in spike_rows
            ],
            "trend": gas_trend,
            "interpretation": {
                "gas_level": f"当前 Gas 水平: {gas_level}",
                "congestion": f"网络拥堵等级: {congestion_row[3] if congestion_row else 'unknown'}",
                "trend": f"Gas 价格趋势: {gas_trend}",
                "spike_count_24h": f"24h 内 Gas 突增次数: {len(spike_rows)}",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 5 分钟采集一次（Gas 变化快）。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="gas_network_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 5 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="gas_network_data_collect",
        )
        return scheduler

    def close(self):
        """关闭客户端连接。"""
        self.client.close()
