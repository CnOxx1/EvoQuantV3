"""bridge_flow_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.bridge_flow_data.client import BridgeFlowClient


class BridgeFlowDataService:
    """跨链桥资金流数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or BridgeFlowClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS bridge_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bridge_name TEXT NOT NULL,
                source_chain TEXT NOT NULL,
                dest_chain TEXT NOT NULL,
                token TEXT DEFAULT 'MIXED',
                volume_usd REAL DEFAULT 0,
                tx_count INTEGER DEFAULT 0,
                avg_time_seconds INTEGER DEFAULT 0,
                snapshot_time TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(bridge_name, source_chain, dest_chain, snapshot_time)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS chain_net_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                inflow_usd REAL DEFAULT 0,
                outflow_usd REAL DEFAULT 0,
                net_flow_usd REAL DEFAULT 0,
                top_source_chain TEXT,
                top_dest_chain TEXT,
                dominant_token TEXT,
                collected_at TEXT NOT NULL,
                UNIQUE(chain, interval, window_start)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bridge_flows_time
            ON bridge_flows(snapshot_time DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chain_net_flows_chain
            ON chain_net_flows(chain, window_start DESC)
        """)
        self.db.conn.commit()
        logger.info("bridge_flow_data 存储初始化完成")

    def bootstrap(self, chains: list[str] | None = None):
        """首次回填。"""
        chains = chains or BridgeFlowClient.TRACKED_CHAINS
        logger.info(f"开始 bootstrap，目标链: {chains}")
        self._collect_bridge_overview()
        self._collect_chain_flows(chains)
        logger.info("bootstrap 完成")

    def collect_once(self, chains: list[str] | None = None):
        """执行一次采集周期。"""
        chains = chains or BridgeFlowClient.TRACKED_CHAINS
        self._collect_bridge_overview()
        self._collect_chain_flows(chains)
        logger.info("collect_once 完成")

    def _collect_bridge_overview(self):
        """采集桥概览数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        bridges = self.client.fetch_bridges_overview()

        for bridge in bridges[:30]:  # Top 30 bridges
            name = bridge.get("displayName", bridge.get("name", "unknown"))
            vol_24h = float(bridge.get("lastDailyVolume", 0) or 0)
            if vol_24h <= 0:
                continue

            # 存储为聚合记录
            self.db.conn.execute("""
                INSERT OR REPLACE INTO bridge_flows
                (bridge_name, source_chain, dest_chain, token, volume_usd,
                 tx_count, avg_time_seconds, snapshot_time, collected_at)
                VALUES (?, 'multi', 'multi', 'MIXED', ?, 0, 0, ?, ?)
            """, (name, vol_24h, now_iso, now_iso))
        self.db.conn.commit()

    def _collect_chain_flows(self, chains: list[str]):
        """采集各链的跨链资金流向。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

        for chain in chains:
            flow_data = self.client.fetch_chain_flows(chain)
            if not flow_data:
                continue

            # DefiLlama 返回的是时间序列数据
            # 取最近的数据点
            inflow = 0.0
            outflow = 0.0

            if isinstance(flow_data, list) and flow_data:
                latest = flow_data[-1] if flow_data else {}
                inflow = float(latest.get("depositUSD", 0) or 0)
                outflow = float(latest.get("withdrawUSD", 0) or 0)
            elif isinstance(flow_data, dict):
                inflow = float(flow_data.get("currentDayDepositsUSD", 0) or 0)
                outflow = float(flow_data.get("currentDayWithdrawalsUSD", 0) or 0)

            net_flow = inflow - outflow

            self.db.conn.execute("""
                INSERT OR REPLACE INTO chain_net_flows
                (chain, interval, window_start, window_end,
                 inflow_usd, outflow_usd, net_flow_usd,
                 top_source_chain, top_dest_chain, dominant_token, collected_at)
                VALUES (?, '1d', ?, ?, ?, ?, ?, '', '', 'MIXED', ?)
            """, (chain, now_iso, now_iso, inflow, outflow, net_flow, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self, chains: list[str] | None = None) -> dict:
        """输出 AI 可读的跨链桥资金流上下文 bundle。"""
        chains = chains or BridgeFlowClient.TRACKED_CHAINS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 链净流向
        placeholders = ",".join("?" * len(chains))
        cursor = self.db.conn.execute(f"""
            SELECT chain, inflow_usd, outflow_usd, net_flow_usd
            FROM chain_net_flows
            WHERE chain IN ({placeholders})
            ORDER BY window_start DESC
        """, tuple(chains))
        flow_rows = cursor.fetchall()

        # 桥交易量
        cursor = self.db.conn.execute("""
            SELECT bridge_name, volume_usd
            FROM bridge_flows
            WHERE snapshot_time >= datetime('now', '-1 day')
            ORDER BY volume_usd DESC
            LIMIT 15
        """)
        bridge_rows = cursor.fetchall()

        if not flow_rows and not bridge_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 链流向摘要
        chain_flows = {}
        seen_chains = set()
        for row in flow_rows:
            chain = row[0]
            if chain in seen_chains:
                continue
            seen_chains.add(chain)
            net = row[3]
            if net > 1_000_000:
                direction = "net_inflow"
            elif net < -1_000_000:
                direction = "net_outflow"
            else:
                direction = "balanced"
            chain_flows[chain] = {
                "inflow_usd": round(row[1], 2),
                "outflow_usd": round(row[2], 2),
                "net_flow_usd": round(net, 2),
                "direction": direction,
            }

        # 桥交易量摘要
        bridge_volumes = {}
        for row in bridge_rows:
            bridge_volumes[row[0]] = {"volume_24h_usd": round(row[1], 2)}

        # 全局信号
        total_net = sum(v["net_flow_usd"] for v in chain_flows.values())
        inflow_chains = [k for k, v in chain_flows.items() if v["direction"] == "net_inflow"]
        outflow_chains = [k for k, v in chain_flows.items() if v["direction"] == "net_outflow"]

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "market_signal": {
                "capital_migration_bias": "l2_expansion" if len(inflow_chains) > len(outflow_chains) else "l1_consolidation",
                "net_inflow_chains": inflow_chains,
                "net_outflow_chains": outflow_chains,
            },
            "chain_flows": chain_flows,
            "bridge_volumes": bridge_volumes,
            "coverage": {
                "chains_tracked": len(chain_flows),
                "bridges_tracked": len(bridge_volumes),
            },
        }

    def build_scheduler(self, chains: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=1,
            kwargs={"chains": chains}, id="bridge_flow_collect",
        )
        return scheduler

    def build_async_scheduler(self, chains: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=1,
            kwargs={"chains": chains}, id="bridge_flow_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
