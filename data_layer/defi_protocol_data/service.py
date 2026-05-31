"""defi_protocol_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.defi_protocol_data.client import DefiProtocolClient


class DefiProtocolDataService:
    """DeFi 协议数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or DefiProtocolClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS defi_tvl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                chain TEXT DEFAULT 'multi',
                tvl_usd REAL NOT NULL,
                tvl_change_1d_pct REAL DEFAULT 0,
                tvl_change_7d_pct REAL DEFAULT 0,
                snapshot_time TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, chain, snapshot_time)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS defi_lending_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                chain TEXT NOT NULL,
                asset TEXT NOT NULL,
                supply_apy REAL DEFAULT 0,
                borrow_apy REAL DEFAULT 0,
                utilization REAL DEFAULT 0,
                total_supply_usd REAL DEFAULT 0,
                total_borrow_usd REAL DEFAULT 0,
                snapshot_time TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, chain, asset, snapshot_time)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS defi_dex_volume (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                chain TEXT DEFAULT 'multi',
                volume_24h_usd REAL DEFAULT 0,
                trades_24h INTEGER DEFAULT 0,
                unique_traders_24h INTEGER DEFAULT 0,
                fees_24h_usd REAL DEFAULT 0,
                snapshot_time TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, chain, snapshot_time)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_defi_tvl_protocol
            ON defi_tvl(protocol, snapshot_time DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_defi_lending_asset
            ON defi_lending_rates(asset, snapshot_time DESC)
        """)
        self.db.conn.commit()
        logger.info("defi_protocol_data 存储初始化完成")

    def bootstrap(self, protocols: list[str] | None = None):
        """首次回填。"""
        protocols = protocols or DefiProtocolClient.TRACKED_PROTOCOLS
        logger.info(f"开始 bootstrap，目标协议: {len(protocols)} 个")
        self._collect_tvl(protocols)
        self._collect_lending_rates()
        self._collect_dex_volumes()
        logger.info("bootstrap 完成")

    def collect_once(self, protocols: list[str] | None = None):
        """执行一次采集周期。"""
        protocols = protocols or DefiProtocolClient.TRACKED_PROTOCOLS
        self._collect_tvl(protocols)
        self._collect_lending_rates()
        self._collect_dex_volumes()
        logger.info("collect_once 完成")

    def _collect_tvl(self, protocols: list[str]):
        """采集协议 TVL。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        all_protocols = self.client.fetch_all_protocols_tvl()
        protocol_map = {p.get("slug", ""): p for p in all_protocols}

        for slug in protocols:
            p = protocol_map.get(slug)
            if not p:
                continue
            tvl = float(p.get("tvl", 0) or 0)
            change_1d = float(p.get("change_1d", 0) or 0)
            change_7d = float(p.get("change_7d", 0) or 0)
            chain = p.get("chain", "Multi")

            self.db.conn.execute("""
                INSERT OR REPLACE INTO defi_tvl
                (protocol, chain, tvl_usd, tvl_change_1d_pct, tvl_change_7d_pct,
                 snapshot_time, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (slug, chain, tvl, change_1d, change_7d, now_iso, now_iso))
        self.db.conn.commit()

    def _collect_lending_rates(self):
        """采集借贷利率。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        pools = self.client.fetch_yields_pools()

        # 只关注主要借贷协议和主要资产
        target_projects = {"aave-v3", "compound-v3", "morpho", "aave-v2"}
        target_assets = {"USDC", "USDT", "ETH", "WETH", "WBTC", "DAI", "WSTETH"}

        for pool in pools:
            project = pool.get("project", "")
            symbol = pool.get("symbol", "").upper()
            if project not in target_projects:
                continue
            # 检查是否包含目标资产
            if not any(asset in symbol for asset in target_assets):
                continue

            chain = pool.get("chain", "Ethereum")
            apy = float(pool.get("apy", 0) or 0)
            apy_borrow = float(pool.get("apyBorrow", 0) or 0)
            tvl = float(pool.get("tvlUsd", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO defi_lending_rates
                (protocol, chain, asset, supply_apy, borrow_apy,
                 utilization, total_supply_usd, total_borrow_usd,
                 snapshot_time, collected_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?, ?)
            """, (project, chain, symbol, apy, apy_borrow, tvl, now_iso, now_iso))
        self.db.conn.commit()

    def _collect_dex_volumes(self):
        """采集 DEX 交易量。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        dex_data = self.client.fetch_dex_overview()
        protocols = dex_data.get("protocols", [])

        for p in protocols[:20]:  # Top 20 DEX
            name = p.get("name", "").lower().replace(" ", "-")
            vol_24h = float(p.get("total24h", 0) or 0)
            change_1d = float(p.get("change_1d", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO defi_dex_volume
                (protocol, chain, volume_24h_usd, trades_24h,
                 unique_traders_24h, fees_24h_usd, snapshot_time, collected_at)
                VALUES (?, 'multi', ?, 0, 0, 0, ?, ?)
            """, (name, vol_24h, now_iso, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self, protocols: list[str] | None = None) -> dict:
        """输出 AI 可读的 DeFi 协议上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # TVL 数据
        cursor = self.db.conn.execute("""
            SELECT protocol, chain, tvl_usd, tvl_change_1d_pct, tvl_change_7d_pct
            FROM defi_tvl
            WHERE snapshot_time >= datetime('now', '-1 day')
            ORDER BY tvl_usd DESC
        """)
        tvl_rows = cursor.fetchall()

        # 借贷利率
        cursor = self.db.conn.execute("""
            SELECT protocol, chain, asset, supply_apy, borrow_apy, total_supply_usd
            FROM defi_lending_rates
            WHERE snapshot_time >= datetime('now', '-1 day')
            ORDER BY total_supply_usd DESC
        """)
        lending_rows = cursor.fetchall()

        # DEX 交易量
        cursor = self.db.conn.execute("""
            SELECT protocol, volume_24h_usd
            FROM defi_dex_volume
            WHERE snapshot_time >= datetime('now', '-1 day')
            ORDER BY volume_24h_usd DESC
        """)
        dex_rows = cursor.fetchall()

        if not tvl_rows and not lending_rows and not dex_rows:
            return {"status": "no_data", "as_of": now_iso}

        # TVL 摘要
        tvl_summary = {}
        total_tvl = 0
        for row in tvl_rows:
            tvl_summary[row[0]] = {
                "chain": row[1],
                "tvl_usd": round(row[2], 2),
                "change_1d_pct": round(row[3], 2),
                "change_7d_pct": round(row[4], 2),
            }
            total_tvl += row[2]

        # 借贷摘要
        lending_summary = {}
        for row in lending_rows:
            key = f"{row[0]}_{row[2]}"
            lending_summary[key] = {
                "protocol": row[0],
                "chain": row[1],
                "asset": row[2],
                "supply_apy_pct": round(row[3], 2),
                "borrow_apy_pct": round(row[4], 2),
                "tvl_usd": round(row[5], 2),
            }

        # DEX 摘要
        dex_summary = {}
        total_dex_vol = 0
        for row in dex_rows:
            dex_summary[row[0]] = {"volume_24h_usd": round(row[1], 2)}
            total_dex_vol += row[1]

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "tvl": {
                "total_tracked_tvl_usd": round(total_tvl, 2),
                "protocol_count": len(tvl_summary),
                "protocols": tvl_summary,
            },
            "lending": {
                "pool_count": len(lending_summary),
                "pools": lending_summary,
            },
            "dex": {
                "total_volume_24h_usd": round(total_dex_vol, 2),
                "protocol_count": len(dex_summary),
                "protocols": dex_summary,
            },
        }

    def build_scheduler(self, protocols: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=1,
            kwargs={"protocols": protocols}, id="defi_protocol_collect",
        )
        return scheduler

    def build_async_scheduler(self, protocols: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=1,
            kwargs={"protocols": protocols}, id="defi_protocol_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
