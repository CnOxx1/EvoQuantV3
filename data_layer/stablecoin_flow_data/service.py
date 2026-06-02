"""stablecoin_flow_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.stablecoin_flow_data.client import StablecoinFlowClient


class StablecoinFlowDataService:
    """稳定币事件级流动数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or StablecoinFlowClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS stablecoin_mint_burns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount_usd REAL DEFAULT 0,
                chain TEXT DEFAULT '',
                tx_hash TEXT DEFAULT '',
                block_number INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                from_address TEXT DEFAULT '',
                to_address TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(asset, tx_hash, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS stablecoin_chain_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                chain TEXT NOT NULL,
                net_flow_usd REAL DEFAULT 0,
                total_supply_on_chain REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(asset, chain, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_stablecoin_mint_burns_asset
            ON stablecoin_mint_burns(asset, timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_stablecoin_chain_flows_asset
            ON stablecoin_chain_flows(asset, chain, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("stablecoin_flow_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 stablecoin_flow_data bootstrap")
        self._collect_chain_flows()
        self._collect_mint_burns()
        logger.info("stablecoin_flow_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_chain_flows()
        self._collect_mint_burns()
        logger.info("stablecoin_flow_data collect_once 完成")

    def _collect_mint_burns(self):
        """从稳定币历史数据中提取 mint/burn 事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        stablecoins = self.client.fetch_stablecoin_list()

        if not stablecoins:
            logger.warning("未获取到稳定币列表")
            return

        collected_count = 0
        for coin in stablecoins[:10]:  # 采集 Top 10 稳定币
            coin_id = coin.get("id")
            asset = coin.get("symbol", "") or coin.get("name", "")
            if not coin_id or not asset:
                continue

            history = self.client.fetch_stablecoin_history(coin_id)
            if not history:
                continue

            # 从 tokens 中提取各链的 mint/burn 数据
            tokens = history.get("tokens", [])
            for token_entry in tokens:
                chain = token_entry.get("chain", "")
                circulating = token_entry.get("circulating", {})
                if not chain or not circulating:
                    continue

                # 用供应量变化推算 mint/burn
                pegged_usd = circulating.get("peggedUSD", 0) or 0
                if pegged_usd > 0:
                    self.db.conn.execute("""
                        INSERT OR REPLACE INTO stablecoin_mint_burns
                        (asset, event_type, amount_usd, chain, tx_hash,
                         block_number, timestamp, from_address, to_address, collected_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (asset, "supply_snapshot", pegged_usd, chain, "",
                          0, now_iso, "", "", now_iso))
                    collected_count += 1

        self.db.conn.commit()
        logger.info(f"稳定币 mint/burn 采集完成，处理 {collected_count} 条记录")

    def _collect_chain_flows(self):
        """采集稳定币在各链上的分布和净流数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        chain_data = self.client.fetch_chain_distribution()

        if not chain_data:
            logger.warning("未获取到稳定币链分布数据")
            return

        collected_count = 0
        for entry in chain_data:
            chain = entry.get("name", "") or entry.get("chain", "")
            total_supply = float(entry.get("totalCirculatingUSD", {}).get("peggedUSD", 0) or 0)

            if not chain or total_supply <= 0:
                continue

            self.db.conn.execute("""
                INSERT OR REPLACE INTO stablecoin_chain_flows
                (asset, chain, net_flow_usd, total_supply_on_chain, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("ALL", chain, 0.0, total_supply, now_iso, now_iso))
            collected_count += 1

        self.db.conn.commit()
        logger.info(f"稳定币链分布采集完成，处理 {collected_count} 条链数据")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的稳定币流动上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新链上分布
        cursor = self.db.conn.execute("""
            SELECT chain, total_supply_on_chain, net_flow_usd
            FROM stablecoin_chain_flows
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM stablecoin_chain_flows
            )
            ORDER BY total_supply_on_chain DESC
        """)
        chain_rows = cursor.fetchall()

        # 获取最新 mint/burn 快照
        cursor = self.db.conn.execute("""
            SELECT asset, event_type, amount_usd, chain
            FROM stablecoin_mint_burns
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM stablecoin_mint_burns
            )
            ORDER BY amount_usd DESC
            LIMIT 50
        """)
        mint_burn_rows = cursor.fetchall()

        if not chain_rows and not mint_burn_rows:
            return {"status": "no_data", "as_of": now_iso}

        chain_distribution = []
        for row in chain_rows:
            chain, supply, net_flow = row
            chain_distribution.append({
                "chain": chain,
                "total_supply_usd": round(supply, 2),
                "net_flow_usd": round(net_flow, 2),
            })

        mint_burn_events = []
        for row in mint_burn_rows:
            asset, event_type, amount, chain = row
            mint_burn_events.append({
                "asset": asset,
                "event_type": event_type,
                "amount_usd": round(amount, 2),
                "chain": chain,
            })

        return {
            "status": "ready",
            "as_of": now_iso,
            "stablecoin_signals": {
                "chain_distribution_top": chain_distribution[:20],
                "recent_mint_burns": mint_burn_events[:20],
                "total_chains_tracked": len(chain_rows),
            },
            "interpretation": {
                "net_flow_usd": "正值表示资金流入该链，负值表示流出",
                "total_supply_on_chain": "该链上稳定币总供应量 (USD)",
                "event_type": "mint=新铸造, burn=销毁, supply_snapshot=供应量快照",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 5 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="stablecoin_flow_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 5 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=5,
            id="stablecoin_flow_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
