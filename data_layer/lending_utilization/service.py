"""lending_utilization 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.lending_utilization.client import LendingUtilizationClient


class LendingUtilizationService:
    """借贷协议利用率数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or LendingUtilizationClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS lending_pools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                asset TEXT NOT NULL,
                total_supply_usd REAL DEFAULT 0,
                total_borrow_usd REAL DEFAULT 0,
                utilization_rate REAL DEFAULT 0,
                supply_apy REAL DEFAULT 0,
                borrow_apy REAL DEFAULT 0,
                kink_utilization REAL DEFAULT 0,
                kink_rate REAL DEFAULT 0,
                optimal_rate REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, asset, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS utilization_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                asset TEXT NOT NULL,
                utilization_rate REAL DEFAULT 0,
                supply_apy REAL DEFAULT 0,
                borrow_apy REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, asset, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lending_pools_time
            ON lending_pools(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_utilization_snapshots_proto
            ON utilization_snapshots(protocol, asset, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("lending_utilization 存储初始化完成")

    def bootstrap(self):
        """首次回填所有协议数据。"""
        logger.info("开始 lending_utilization bootstrap")
        self.collect_once()
        logger.info("lending_utilization bootstrap 完成")

    def collect_once(self):
        """执行一次完整采集周期。"""
        self._collect_aave()
        self._collect_compound()
        self._collect_morpho()
        logger.info("lending_utilization collect_once 完成")

    def _collect_aave(self):
        """采集 Aave V3 池数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        pools = self.client.fetch_aave_pools()
        for pool in pools:
            asset = pool.get("symbol", "UNKNOWN")
            supply = float(pool.get("totalATokenSupply", 0) or 0)
            borrow = float(pool.get("totalCurrentVariableDebt", 0) or 0)
            util = float(pool.get("utilizationRate", 0) or 0)
            supply_apy = float(pool.get("liquidityRate", 0) or 0)
            borrow_apy = float(pool.get("variableBorrowRate", 0) or 0)
            kink = float(pool.get("optimalUtilisationRate", 0) or 0)
            slope1 = float(pool.get("variableRateSlope1", 0) or 0)
            slope2 = float(pool.get("variableRateSlope2", 0) or 0)
            self.db.conn.execute("""
                INSERT OR REPLACE INTO lending_pools
                (protocol, asset, total_supply_usd, total_borrow_usd,
                 utilization_rate, supply_apy, borrow_apy,
                 kink_utilization, kink_rate, optimal_rate,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("aave", asset, supply, borrow, util, supply_apy,
                  borrow_apy, kink, slope1, slope2, now_iso, now_iso))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO utilization_snapshots
                (protocol, asset, utilization_rate, supply_apy,
                 borrow_apy, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("aave", asset, util, supply_apy, borrow_apy,
                  now_iso, now_iso))
        self.db.conn.commit()

    def _collect_compound(self):
        """采集 Compound V3 市场数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        markets = self.client.fetch_compound_markets()
        for market in markets:
            asset = market.get("inputToken", {}).get("symbol", "UNKNOWN")
            tvl = float(market.get("totalValueLockedUSD", 0) or 0)
            borrow = float(market.get("totalBorrowBalanceUSD", 0) or 0)
            util = borrow / tvl if tvl > 0 else 0.0
            supply_apy = 0.0
            borrow_apy = 0.0
            for rate in market.get("rates", []):
                if rate.get("side") == "LENDER":
                    supply_apy = float(rate.get("rate", 0) or 0)
                elif rate.get("side") == "BORROWER":
                    borrow_apy = float(rate.get("rate", 0) or 0)
            self.db.conn.execute("""
                INSERT OR REPLACE INTO lending_pools
                (protocol, asset, total_supply_usd, total_borrow_usd,
                 utilization_rate, supply_apy, borrow_apy,
                 kink_utilization, kink_rate, optimal_rate,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """, ("compound", asset, tvl, borrow, util, supply_apy,
                  borrow_apy, now_iso, now_iso))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO utilization_snapshots
                (protocol, asset, utilization_rate, supply_apy,
                 borrow_apy, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("compound", asset, util, supply_apy, borrow_apy,
                  now_iso, now_iso))
        self.db.conn.commit()

    def _collect_morpho(self):
        """采集 Morpho 市场数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        markets = self.client.fetch_morpho_markets()
        for market in markets:
            asset = market.get("loanAsset", {}).get("symbol", "UNKNOWN")
            state = market.get("state", {})
            supply = float(state.get("totalSupplyUsd", 0) or 0)
            borrow = float(state.get("totalBorrowUsd", 0) or 0)
            util = float(state.get("utilization", 0) or 0)
            supply_apy = float(state.get("supplyApy", 0) or 0)
            borrow_apy = float(state.get("borrowApy", 0) or 0)
            self.db.conn.execute("""
                INSERT OR REPLACE INTO lending_pools
                (protocol, asset, total_supply_usd, total_borrow_usd,
                 utilization_rate, supply_apy, borrow_apy,
                 kink_utilization, kink_rate, optimal_rate,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """, ("morpho", asset, supply, borrow, util, supply_apy,
                  borrow_apy, now_iso, now_iso))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO utilization_snapshots
                (protocol, asset, utilization_rate, supply_apy,
                 borrow_apy, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("morpho", asset, util, supply_apy, borrow_apy,
                  now_iso, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的借贷利用率上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        cursor = self.db.conn.execute("""
            SELECT protocol, asset, total_supply_usd, total_borrow_usd,
                   utilization_rate, supply_apy, borrow_apy
            FROM lending_pools
            WHERE timestamp >= datetime('now', '-1 hour')
            ORDER BY total_supply_usd DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        pools_by_protocol = {}
        for row in rows:
            protocol = row[0]
            if protocol not in pools_by_protocol:
                pools_by_protocol[protocol] = []
            pools_by_protocol[protocol].append({
                "asset": row[1],
                "total_supply_usd": round(row[2], 2),
                "total_borrow_usd": round(row[3], 2),
                "utilization_rate": round(row[4], 4),
                "supply_apy": round(row[5], 4),
                "borrow_apy": round(row[6], 4),
            })

        # 高利用率池警报
        high_util_pools = [
            {"protocol": row[0], "asset": row[1], "utilization": round(row[4], 4)}
            for row in rows if row[4] > 0.9
        ]

        return {
            "status": "ready",
            "as_of": now_iso,
            "pools_by_protocol": pools_by_protocol,
            "alerts": {
                "high_utilization_pools": high_util_pools,
            },
            "coverage": {
                "protocols_tracked": len(pools_by_protocol),
                "pools_tracked": len(rows),
            },
        }

    def build_scheduler(self):
        """构建 BlockingScheduler，每 5 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="lending_utilization_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建 AsyncIOScheduler，每 5 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="lending_utilization_collect",
        )
        return scheduler

    def close(self):
        """释放资源。"""
        self.client.close()
