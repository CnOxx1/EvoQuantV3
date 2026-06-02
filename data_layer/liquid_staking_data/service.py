"""liquid_staking_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.liquid_staking_data.client import LiquidStakingDataClient


class LiquidStakingDataService:
    """流动性质押数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or LiquidStakingDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS staking_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                total_staked REAL DEFAULT 0,
                staking_apr REAL DEFAULT 0,
                lst_premium_discount REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS validator_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_entry_wait REAL DEFAULT 0,
                queue_exit_wait REAL DEFAULT 0,
                active_validators INTEGER DEFAULT 0,
                pending_validators INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS restaking_tvl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                restaking_tvl REAL DEFAULT 0,
                num_operators INTEGER DEFAULT 0,
                num_avs INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_staking_positions_protocol
            ON staking_positions(protocol, collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_restaking_tvl_protocol
            ON restaking_tvl(protocol, collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("liquid_staking_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 liquid_staking_data bootstrap")
        self._collect_all_sources()
        logger.info("liquid_staking_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_all_sources()
        logger.info("liquid_staking_data collect_once 完成")

    def _collect_all_sources(self):
        """从所有数据源采集数据。"""
        self._collect_lido()
        self._collect_rocketpool()
        self._collect_eigenlayer()
        self._collect_validator_queue()

    def _collect_lido(self):
        """从 DefiLlama 采集 Lido 质押数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_lido_stats()

        if not data:
            logger.warning("Lido 未返回数据")
            return

        total_staked = float(data.get("currentChainTvls", {}).get("Ethereum", 0) or 0)
        staking_apr = float(data.get("apy", 0) or 0)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO staking_positions
            (protocol, total_staked, staking_apr, lst_premium_discount, collected_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("lido", total_staked, staking_apr, 0.0, now_iso))

        self.db.conn.commit()
        logger.info(f"Lido 采集完成，total_staked={total_staked:.2f}")

    def _collect_rocketpool(self):
        """从 DefiLlama 采集 Rocket Pool 质押数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_rocketpool_stats()

        if not data:
            logger.warning("Rocket Pool 未返回数据")
            return

        total_staked = float(data.get("currentChainTvls", {}).get("Ethereum", 0) or 0)
        staking_apr = float(data.get("apy", 0) or 0)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO staking_positions
            (protocol, total_staked, staking_apr, lst_premium_discount, collected_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("rocketpool", total_staked, staking_apr, 0.0, now_iso))

        self.db.conn.commit()
        logger.info(f"Rocket Pool 采集完成，total_staked={total_staked:.2f}")

    def _collect_eigenlayer(self):
        """从 EigenExplorer 采集再质押 TVL 数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_eigenlayer_tvl()

        if not data:
            logger.warning("EigenLayer 未返回数据")
            return

        tvl = float(data.get("tvl", 0) or 0)
        num_operators = int(data.get("totalOperators", 0) or 0)
        num_avs = int(data.get("totalAvs", 0) or 0)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO restaking_tvl
            (protocol, restaking_tvl, num_operators, num_avs, collected_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("eigenlayer", tvl, num_operators, num_avs, now_iso))

        self.db.conn.commit()
        logger.info(f"EigenLayer 采集完成，tvl={tvl:.2f}")

    def _collect_validator_queue(self):
        """从 Beaconchain 采集验证者队列数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_validator_queue()

        if not data:
            logger.warning("Beaconchain 未返回验证者队列数据")
            return

        # 计算等待时间（根据队列长度估算）
        entering = int(data.get("beaconchain_entering", 0) or 0)
        exiting = int(data.get("beaconchain_exiting", 0) or 0)
        active = int(data.get("validatorscount", 0) or 0)

        # 每个 epoch 约 6.4 分钟，每 epoch 可处理的验证者数量
        churn_limit = max(4, active // 65536)
        entry_wait_hours = (entering / churn_limit * 6.4) / 60 if churn_limit else 0
        exit_wait_hours = (exiting / churn_limit * 6.4) / 60 if churn_limit else 0

        self.db.conn.execute("""
            INSERT OR REPLACE INTO validator_queue
            (queue_entry_wait, queue_exit_wait, active_validators,
             pending_validators, collected_at)
            VALUES (?, ?, ?, ?, ?)
        """, (entry_wait_hours, exit_wait_hours, active, entering, now_iso))

        self.db.conn.commit()
        logger.info(
            f"验证者队列采集完成，entry_wait={entry_wait_hours:.1f}h, "
            f"exit_wait={exit_wait_hours:.1f}h"
        )

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的流动性质押上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新质押仓位
        cursor = self.db.conn.execute("""
            SELECT protocol, total_staked, staking_apr, lst_premium_discount
            FROM staking_positions
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM staking_positions
            )
            ORDER BY total_staked DESC
        """)
        staking_rows = cursor.fetchall()

        if not staking_rows:
            return {"status": "no_data", "as_of": now_iso}

        staking_positions = []
        for row in staking_rows:
            protocol, total_staked, apr, premium = row
            staking_positions.append({
                "protocol": protocol,
                "total_staked": round(total_staked, 2),
                "staking_apr": round(apr, 4),
                "lst_premium_discount": round(premium, 4),
            })

        # 获取最新验证者队列
        q_cursor = self.db.conn.execute("""
            SELECT queue_entry_wait, queue_exit_wait,
                   active_validators, pending_validators
            FROM validator_queue
            ORDER BY collected_at DESC LIMIT 1
        """)
        q_row = q_cursor.fetchone()
        validator_queue = {}
        if q_row:
            validator_queue = {
                "queue_entry_wait_hours": round(q_row[0], 2),
                "queue_exit_wait_hours": round(q_row[1], 2),
                "active_validators": q_row[2],
                "pending_validators": q_row[3],
            }

        # 获取最新再质押 TVL
        r_cursor = self.db.conn.execute("""
            SELECT protocol, restaking_tvl, num_operators, num_avs
            FROM restaking_tvl
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM restaking_tvl
            )
        """)
        r_row = r_cursor.fetchone()
        restaking_data = {}
        if r_row:
            restaking_data = {
                "protocol": r_row[0],
                "restaking_tvl": round(r_row[1], 2),
                "num_operators": r_row[2],
                "num_avs": r_row[3],
            }

        # 计算质押趋势（对比前一次采集）
        trend_cursor = self.db.conn.execute("""
            SELECT protocol, total_staked
            FROM staking_positions
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM staking_positions
                WHERE collected_at < (SELECT MAX(collected_at) FROM staking_positions)
            )
        """)
        prev_rows = {row[0]: row[1] for row in trend_cursor.fetchall()}
        staking_trends = {}
        for pos in staking_positions:
            protocol = pos["protocol"]
            prev_staked = prev_rows.get(protocol, 0)
            if prev_staked > 0:
                change_pct = (pos["total_staked"] - prev_staked) / prev_staked
                staking_trends[protocol] = round(change_pct, 4)

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "staking_positions": staking_positions,
                "validator_queue": validator_queue,
                "restaking": restaking_data,
                "staking_trends": staking_trends,
            },
            "interpretation": {
                "staking": "ETH 质押流入/流出趋势，正值表示净流入",
                "queue_pressure": "验证者队列压力，等待时间越长表示需求越大",
                "restaking_tvl": "再质押 TVL 变化反映 EigenLayer 生态增长",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="liquid_staking_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="liquid_staking_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
