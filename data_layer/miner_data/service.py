"""miner_data 服务层。"""

from datetime import datetime, timezone
from math import isfinite

from loguru import logger

from data_layer.miner_data.client import MinerDataClient


class MinerDataService:
    """矿工数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or MinerDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS miner_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hashrate REAL DEFAULT 0,
                difficulty REAL DEFAULT 0,
                block_reward REAL DEFAULT 0,
                miner_revenue_24h REAL DEFAULT 0,
                miner_outflow_24h REAL DEFAULT 0,
                hash_price REAL DEFAULT 0,
                difficulty_adjustment_pct REAL DEFAULT 0,
                puell_multiple REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS hashrate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hashrate REAL DEFAULT 0,
                difficulty REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_miner_metrics_collected
            ON miner_metrics(collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hashrate_history_ts
            ON hashrate_history(timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("miner_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 miner_data bootstrap")
        self._collect_mining_data()
        self._collect_hashrate_history()
        logger.info("miner_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_mining_data()
        self._collect_hashrate_history()
        logger.info("miner_data collect_once 完成")

    def _collect_mining_data(self):
        """采集矿工指标数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        stats = self.client.fetch_mining_stats()
        outflows_data = self.client.fetch_miner_outflows()

        hashrate = self._finite_float(stats.get("hashrate", 0.0))
        difficulty = self._finite_float(stats.get("difficulty", 0.0))
        block_reward = self._finite_float(stats.get("block_reward", 0.0))
        miners_revenue = self._finite_float(stats.get("miners_revenue", 0.0))

        # A complete upstream failure must not be persisted as an all-zero
        # observation, which would make the data domain look falsely healthy.
        if not any((hashrate, difficulty, block_reward, miners_revenue)):
            logger.warning("miner_data 未取得可写入的真实公开指标，跳过本次快照")
            return

        # 估算矿工流出：使用算力波动作为代理指标
        miner_outflow_24h = self._estimate_miner_outflow(outflows_data)

        # Hash Price = miner revenue / hashrate
        hash_price = 0.0
        if hashrate > 0:
            hash_price = miners_revenue / hashrate

        # 难度调整预估
        difficulty_adjustment_pct = self._estimate_difficulty_adjustment(stats)

        # Puell Multiple = daily miner revenue / 365-day MA of daily miner revenue
        puell_multiple = self._calculate_puell_multiple(miners_revenue)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO miner_metrics
            (hashrate, difficulty, block_reward, miner_revenue_24h,
             miner_outflow_24h, hash_price, difficulty_adjustment_pct,
             puell_multiple, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hashrate, difficulty, block_reward, miners_revenue,
            miner_outflow_24h, hash_price, difficulty_adjustment_pct,
            puell_multiple, now_iso,
        ))
        self.db.conn.commit()
        logger.info(f"miner_metrics 采集完成: hashrate={hashrate}, puell={puell_multiple:.4f}")

    def _estimate_miner_outflow(self, outflows_data: dict) -> float:
        """估算矿工24h流出量。"""
        if not outflows_data:
            return 0.0
        hashrates = outflows_data.get("hashrates", [])
        if len(hashrates) < 2:
            return 0.0
        # 使用算力下降幅度作为流出压力代理
        recent = hashrates[-1].get("avgHashrate", 0)
        previous = hashrates[0].get("avgHashrate", 0)
        if previous > 0:
            change_pct = (recent - previous) / previous
            # 负变化意味着潜在矿工抛压
            return abs(min(change_pct, 0)) * 100
        return 0.0

    @staticmethod
    def _finite_float(value) -> float:
        """Convert public JSON numerics to SQLite-compatible REAL safely."""
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if isfinite(number) else 0.0

    def _estimate_difficulty_adjustment(self, stats: dict) -> float:
        """估算下次难度调整百分比。"""
        adjustments = stats.get("difficulty_adjustments", [])
        if not adjustments or not isinstance(adjustments, list):
            return 0.0
        # 最近一次难度调整记录
        if len(adjustments) >= 2:
            latest = adjustments[0]
            previous = adjustments[1]
            if isinstance(latest, list) and len(latest) >= 4:
                # mempool格式: [height, timestamp, difficulty, adjustment]
                return float(latest[3]) if len(latest) > 3 else 0.0
            elif isinstance(latest, dict):
                return float(latest.get("difficultyChange", 0))
        return 0.0

    def _calculate_puell_multiple(self, daily_revenue: float) -> float:
        """计算 Puell Multiple = daily revenue / 365-day MA of daily revenue。"""
        cursor = self.db.conn.execute("""
            SELECT AVG(miner_revenue_24h) FROM (
                SELECT miner_revenue_24h FROM miner_metrics
                WHERE miner_revenue_24h > 0
                ORDER BY collected_at DESC
                LIMIT 365
            )
        """)
        row = cursor.fetchone()
        ma_365 = row[0] if row and row[0] else 0.0

        if ma_365 > 0 and daily_revenue > 0:
            return daily_revenue / ma_365
        # 如果没有历史数据，返回 1.0（中性值）
        return 1.0 if daily_revenue > 0 else 0.0

    def _collect_hashrate_history(self):
        """采集算力历史数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        history = self.client.fetch_hashrate_history()

        if not history:
            logger.warning("未获取到算力历史数据")
            return

        for entry in history:
            ts = entry.get("timestamp", 0)
            avg_hashrate = self._finite_float(entry.get("avgHashrate", 0.0))
            difficulty = self._finite_float(entry.get("difficulty", 0.0))

            # 时间戳转换
            if isinstance(ts, (int, float)) and ts > 0:
                ts_iso = datetime.fromtimestamp(
                    ts, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S")
            else:
                ts_iso = str(ts)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO hashrate_history
                (hashrate, difficulty, timestamp, collected_at)
                VALUES (?, ?, ?, ?)
            """, (avg_hashrate, difficulty, ts_iso, now_iso))

        self.db.conn.commit()
        logger.info(f"hashrate_history 采集完成，{len(history)} 条记录")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的矿工数据上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新矿工指标
        cursor = self.db.conn.execute("""
            SELECT hashrate, difficulty, block_reward, miner_revenue_24h,
                   miner_outflow_24h, hash_price, difficulty_adjustment_pct,
                   puell_multiple, collected_at
            FROM miner_metrics
            ORDER BY collected_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            return {"status": "no_data", "as_of": now_iso}

        (hashrate, difficulty, block_reward, revenue_24h,
         outflow_24h, hash_price, diff_adj_pct, puell, collected_at) = row

        # Puell Multiple 解读
        if puell < 0.5:
            puell_interpretation = "capitulation_zone（矿工投降区域，历史底部信号）"
        elif puell < 1.0:
            puell_interpretation = "undervalued（矿工收入低于历史均值）"
        elif puell <= 4.0:
            puell_interpretation = "neutral（矿工收入正常区间）"
        else:
            puell_interpretation = "overheated（矿工收入过热，历史顶部信号）"

        # 算力趋势（7天对比）
        hashrate_trend = self._calculate_hashrate_trend()

        # 难度调整预估
        diff_adj_signal = "neutral"
        if diff_adj_pct > 5:
            diff_adj_signal = "算力大幅增长，矿工竞争加剧"
        elif diff_adj_pct < -5:
            diff_adj_signal = "算力下降，矿工可能关机或投降"

        return {
            "status": "ready",
            "as_of": now_iso,
            "current_metrics": {
                "hashrate": hashrate,
                "difficulty": difficulty,
                "block_reward": block_reward,
                "miner_revenue_24h_usd": revenue_24h,
                "miner_outflow_24h": outflow_24h,
                "hash_price_usd_per_th": hash_price,
                "difficulty_adjustment_pct": diff_adj_pct,
                "puell_multiple": round(puell, 4),
            },
            "signals": {
                "puell_multiple": {
                    "value": round(puell, 4),
                    "interpretation": puell_interpretation,
                    "thresholds": "< 0.5 = capitulation, > 4 = overheated",
                },
                "hashrate_trend": hashrate_trend,
                "difficulty_adjustment": {
                    "estimated_pct": round(diff_adj_pct, 2),
                    "signal": diff_adj_signal,
                },
                "miner_pressure": {
                    "outflow_indicator": outflow_24h,
                    "hash_price": round(hash_price, 4),
                    "note": "高流出 + 低算力价格 = 矿工抛压信号",
                },
            },
            "interpretation": {
                "puell": "Puell Multiple < 0.5 为矿工投降区（历史底部），> 4 为过热区（历史顶部）",
                "hashrate": "算力持续增长表示矿工信心充足，下降表示矿工压力增大",
                "difficulty": "难度上调意味着竞争加剧，下调意味着矿工退出",
            },
        }

    def _calculate_hashrate_trend(self) -> dict:
        """计算算力趋势（基于历史数据对比）。"""
        cursor = self.db.conn.execute("""
            SELECT hashrate, timestamp FROM hashrate_history
            ORDER BY timestamp DESC
            LIMIT 168
        """)
        rows = cursor.fetchall()

        if len(rows) < 2:
            return {"trend": "insufficient_data", "change_pct": 0.0}

        recent_hashrate = rows[0][0]
        # 取 7 天前（或最早可用）的算力
        older_hashrate = rows[-1][0]

        if older_hashrate > 0:
            change_pct = ((recent_hashrate - older_hashrate) / older_hashrate) * 100
        else:
            change_pct = 0.0

        if change_pct > 2:
            trend = "increasing"
        elif change_pct < -2:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "change_pct_7d": round(change_pct, 2),
            "latest_hashrate": recent_hashrate,
            "comparison_hashrate": older_hashrate,
            "note": "基于可用历史数据计算的算力变化趋势",
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            id="miner_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            id="miner_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
