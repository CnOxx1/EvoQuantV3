"""defi_liquidation_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.defi_liquidation_data.client import DefiLiquidationClient


class DefiLiquidationDataService:
    """DeFi 清算事件数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or DefiLiquidationClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS defi_liquidations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                liquidator TEXT,
                borrower TEXT,
                collateral_asset TEXT,
                debt_asset TEXT,
                debt_repaid_usd REAL DEFAULT 0,
                collateral_seized_usd REAL DEFAULT 0,
                health_factor_before REAL DEFAULT 0,
                tx_hash TEXT,
                block_number INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, tx_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS health_factor_distribution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                hf_bucket TEXT NOT NULL,
                position_count INTEGER DEFAULT 0,
                total_collateral_usd REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, timestamp, hf_bucket)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_defi_liquidations_time
            ON defi_liquidations(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_health_factor_dist_time
            ON health_factor_distribution(protocol, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("defi_liquidation_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 bootstrap DeFi 清算数据")
        since = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
        self._collect_liquidations(since)
        self._collect_health_factors()
        logger.info("bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        since = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())
        self._collect_liquidations(since)
        self._collect_health_factors()
        logger.info("collect_once 完成")

    def _collect_liquidations(self, since_timestamp: int):
        """采集清算事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # Aave V3
        aave_liqs = self.client.fetch_aave_liquidations(since_timestamp)
        for liq in aave_liqs:
            tx_hash = liq.get("transaction", {}).get("id", "")
            block = int(liq.get("transaction", {}).get("blockNumber", 0) or 0)
            ts = datetime.fromtimestamp(
                int(liq.get("timestamp", 0)), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")
            self.db.conn.execute("""
                INSERT OR IGNORE INTO defi_liquidations
                (protocol, timestamp, liquidator, borrower,
                 collateral_asset, debt_asset, debt_repaid_usd,
                 collateral_seized_usd, health_factor_before,
                 tx_hash, block_number, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "aave_v3", ts,
                liq.get("liquidator", ""),
                liq.get("user", {}).get("id", ""),
                liq.get("collateralAsset", {}).get("symbol", ""),
                liq.get("debtAsset", {}).get("symbol", ""),
                float(liq.get("debtToCover", 0) or 0),
                float(liq.get("liquidatedCollateralAmount", 0) or 0),
                0.0, tx_hash, block, now_iso,
            ))

        # Compound V3
        comp_liqs = self.client.fetch_compound_liquidations(since_timestamp)
        for liq in comp_liqs:
            tx_hash = liq.get("transaction", {}).get("id", "")
            block = int(liq.get("transaction", {}).get("blockNumber", 0) or 0)
            ts = datetime.fromtimestamp(
                int(liq.get("timestamp", 0)), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")
            self.db.conn.execute("""
                INSERT OR IGNORE INTO defi_liquidations
                (protocol, timestamp, liquidator, borrower,
                 collateral_asset, debt_asset, debt_repaid_usd,
                 collateral_seized_usd, health_factor_before,
                 tx_hash, block_number, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "compound_v3", ts,
                liq.get("liquidator", {}).get("id", ""),
                liq.get("liquidatee", {}).get("id", ""),
                liq.get("market", {}).get("inputToken", {}).get("symbol", ""),
                liq.get("asset", {}).get("symbol", ""),
                float(liq.get("amountUSD", 0) or 0),
                float(liq.get("amountUSD", 0) or 0),
                0.0, tx_hash, block, now_iso,
            ))
        self.db.conn.commit()

    def _collect_health_factors(self):
        """采集健康因子分布。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        buckets = {"<1.0": 0, "1.0-1.1": 0, "1.1-1.25": 0, "1.25-1.5": 0, ">1.5": 0}
        collateral_by_bucket = {"<1.0": 0.0, "1.0-1.1": 0.0, "1.1-1.25": 0.0, "1.25-1.5": 0.0, ">1.5": 0.0}

        users = self.client.fetch_health_factors(protocol="aave")
        for user in users:
            hf = float(user.get("healthFactor", 0) or 0) / 1e18 if user.get("healthFactor") else 999
            collateral = float(user.get("totalCollateralUSD", 0) or 0)
            if hf < 1.0:
                bucket = "<1.0"
            elif hf < 1.1:
                bucket = "1.0-1.1"
            elif hf < 1.25:
                bucket = "1.1-1.25"
            elif hf < 1.5:
                bucket = "1.25-1.5"
            else:
                bucket = ">1.5"
            buckets[bucket] += 1
            collateral_by_bucket[bucket] += collateral

        for bucket, count in buckets.items():
            self.db.conn.execute("""
                INSERT OR REPLACE INTO health_factor_distribution
                (protocol, timestamp, hf_bucket, position_count,
                 total_collateral_usd, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("aave_v3", now_iso, bucket, count,
                  collateral_by_bucket[bucket], now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的 DeFi 清算上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        cursor = self.db.conn.execute("""
            SELECT protocol, timestamp, collateral_asset, debt_asset,
                   debt_repaid_usd, collateral_seized_usd
            FROM defi_liquidations
            ORDER BY timestamp DESC LIMIT 20
        """)
        liq_rows = cursor.fetchall()

        cursor = self.db.conn.execute("""
            SELECT protocol, hf_bucket, position_count, total_collateral_usd
            FROM health_factor_distribution
            ORDER BY timestamp DESC LIMIT 10
        """)
        hf_rows = cursor.fetchall()

        if not liq_rows and not hf_rows:
            return {"status": "no_data", "as_of": now_iso}

        recent_liquidations = []
        for row in liq_rows:
            recent_liquidations.append({
                "protocol": row[0],
                "timestamp": row[1],
                "collateral_asset": row[2],
                "debt_asset": row[3],
                "debt_repaid_usd": round(row[4], 2),
                "collateral_seized_usd": round(row[5], 2),
            })

        health_factors = {}
        for row in hf_rows:
            protocol = row[0]
            if protocol not in health_factors:
                health_factors[protocol] = {}
            health_factors[protocol][row[1]] = {
                "position_count": row[2],
                "total_collateral_usd": round(row[3], 2),
            }

        total_liq_volume = sum(r[4] for r in liq_rows)

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "recent",
            "market_signal": {
                "total_liquidation_volume_usd": round(total_liq_volume, 2),
                "liquidation_count": len(liq_rows),
                "high_risk_positions": health_factors,
            },
            "recent_liquidations": recent_liquidations[:10],
            "health_factor_distribution": health_factors,
        }

    def build_scheduler(self):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=2,
            id="defi_liquidation_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=2,
            id="defi_liquidation_collect",
        )
        return scheduler

    def close(self):
        self.client.close()