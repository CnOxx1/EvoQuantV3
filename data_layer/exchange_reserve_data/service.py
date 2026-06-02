"""exchange_reserve_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.exchange_reserve_data.client import ExchangeReserveDataClient


class ExchangeReserveDataService:
    """交易所储备数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or ExchangeReserveDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_reserves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                asset TEXT NOT NULL,
                reserve_balance REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, asset, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS reserve_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                asset TEXT NOT NULL,
                change_24h REAL DEFAULT 0,
                change_7d REAL DEFAULT 0,
                netflow_24h REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, asset, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchange_reserves_lookup
            ON exchange_reserves(exchange, asset, collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reserve_changes_lookup
            ON reserve_changes(exchange, asset, collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("exchange_reserve_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 exchange_reserve_data bootstrap")
        self._collect_all_reserves()
        logger.info("exchange_reserve_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_all_reserves()
        logger.info("exchange_reserve_data collect_once 完成")

    def _collect_all_reserves(self):
        """从所有数据源采集储备数据。"""
        self._collect_btc_reserves()
        self._collect_eth_reserves()
        self._collect_stablecoin_reserves()
        self._compute_reserve_changes()

    def _collect_btc_reserves(self):
        """采集 BTC 交易所储备。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_btc_reserves()

        if not data:
            logger.warning("BTC reserves 未返回数据")
            return

        for item in data:
            address = item.get("address", "unknown")
            balance = float(item.get("balance", 0)) / 1e8  # satoshi to BTC

            self.db.conn.execute("""
                INSERT OR REPLACE INTO exchange_reserves
                (exchange, asset, reserve_balance, collected_at)
                VALUES (?, ?, ?, ?)
            """, (address, "BTC", balance, now_iso))

        self.db.conn.commit()
        logger.info(f"BTC reserves 采集完成，处理 {len(data)} 条记录")

    def _collect_eth_reserves(self):
        """采集 ETH 交易所储备。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_eth_reserves()

        if not data:
            logger.warning("ETH reserves 未返回数据")
            return

        for item in data:
            exchange = item.get("exchange", "unknown")
            balance = float(item.get("reserve_balance", 0))

            self.db.conn.execute("""
                INSERT OR REPLACE INTO exchange_reserves
                (exchange, asset, reserve_balance, collected_at)
                VALUES (?, ?, ?, ?)
            """, (exchange, "ETH", balance, now_iso))

        self.db.conn.commit()
        logger.info(f"ETH reserves 采集完成，处理 {len(data)} 条记录")

    def _collect_stablecoin_reserves(self):
        """采集稳定币交易所储备。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_stablecoin_reserves()

        if not data:
            logger.warning("Stablecoin reserves 未返回数据")
            return

        for item in data:
            exchange = item.get("exchange", "unknown")
            balance = float(item.get("reserve_balance", 0))

            self.db.conn.execute("""
                INSERT OR REPLACE INTO exchange_reserves
                (exchange, asset, reserve_balance, collected_at)
                VALUES (?, ?, ?, ?)
            """, (exchange, "USDT", balance, now_iso))

        self.db.conn.commit()
        logger.info(f"Stablecoin reserves 采集完成，处理 {len(data)} 条记录")

    def _compute_reserve_changes(self):
        """计算储备变动并写入 reserve_changes 表。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取当前最新储备
        cursor = self.db.conn.execute("""
            SELECT exchange, asset, reserve_balance
            FROM exchange_reserves
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM exchange_reserves
            )
        """)
        current_rows = cursor.fetchall()

        for row in current_rows:
            exchange, asset, current_balance = row

            # 24h 前的储备
            cursor_24h = self.db.conn.execute("""
                SELECT reserve_balance FROM exchange_reserves
                WHERE exchange = ? AND asset = ?
                AND collected_at <= datetime(?, '-24 hours')
                ORDER BY collected_at DESC LIMIT 1
            """, (exchange, asset, now_iso))
            row_24h = cursor_24h.fetchone()
            balance_24h = row_24h[0] if row_24h else current_balance

            # 7d 前的储备
            cursor_7d = self.db.conn.execute("""
                SELECT reserve_balance FROM exchange_reserves
                WHERE exchange = ? AND asset = ?
                AND collected_at <= datetime(?, '-7 days')
                ORDER BY collected_at DESC LIMIT 1
            """, (exchange, asset, now_iso))
            row_7d = cursor_7d.fetchone()
            balance_7d = row_7d[0] if row_7d else current_balance

            change_24h = current_balance - balance_24h
            change_7d = current_balance - balance_7d
            netflow_24h = change_24h  # 正值=净流入, 负值=净流出

            self.db.conn.execute("""
                INSERT OR REPLACE INTO reserve_changes
                (exchange, asset, change_24h, change_7d, netflow_24h, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (exchange, asset, change_24h, change_7d, netflow_24h, now_iso))

        self.db.conn.commit()
        logger.info(f"reserve_changes 计算完成，处理 {len(current_rows)} 条记录")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的交易所储备上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新储备数据（按资产分组）
        cursor = self.db.conn.execute("""
            SELECT exchange, asset, reserve_balance
            FROM exchange_reserves
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM exchange_reserves
            )
            ORDER BY reserve_balance DESC
        """)
        reserve_rows = cursor.fetchall()

        if not reserve_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 按资产聚合当前储备
        reserves_by_asset = {}
        for exchange, asset, balance in reserve_rows:
            if asset not in reserves_by_asset:
                reserves_by_asset[asset] = []
            reserves_by_asset[asset].append({
                "exchange": exchange,
                "reserve_balance": round(balance, 4),
            })

        # 资产总量汇总（全市场视角）
        total_by_asset = {}
        for asset, entries in reserves_by_asset.items():
            total_by_asset[asset] = round(
                sum(e["reserve_balance"] for e in entries), 4
            )

        # 获取净流动数据
        flow_cursor = self.db.conn.execute("""
            SELECT exchange, asset, change_24h, change_7d, netflow_24h
            FROM reserve_changes
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM reserve_changes
            )
            ORDER BY ABS(netflow_24h) DESC
        """)
        flow_rows = flow_cursor.fetchall()

        # 净流动汇总
        net_flows = {}
        for exchange, asset, c24h, c7d, nf24h in flow_rows:
            if asset not in net_flows:
                net_flows[asset] = {"total_netflow_24h": 0, "details": []}
            net_flows[asset]["total_netflow_24h"] += nf24h
            net_flows[asset]["details"].append({
                "exchange": exchange,
                "change_24h": round(c24h, 4),
                "change_7d": round(c7d, 4),
                "netflow_24h": round(nf24h, 4),
            })
        # 四舍五入汇总值
        for asset in net_flows:
            net_flows[asset]["total_netflow_24h"] = round(
                net_flows[asset]["total_netflow_24h"], 4
            )

        # 历史低点检测
        historical_low_alerts = []
        for exchange, asset, balance in reserve_rows:
            min_cursor = self.db.conn.execute("""
                SELECT MIN(reserve_balance) FROM exchange_reserves
                WHERE exchange = ? AND asset = ?
            """, (exchange, asset))
            min_row = min_cursor.fetchone()
            if min_row and min_row[0] is not None:
                if balance <= min_row[0]:
                    historical_low_alerts.append({
                        "exchange": exchange,
                        "asset": asset,
                        "current_balance": round(balance, 4),
                        "historical_low": round(min_row[0], 4),
                    })

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "reserves_by_asset": reserves_by_asset,
                "total_market_reserves": total_by_asset,
                "net_flows": net_flows,
                "historical_low_alerts": historical_low_alerts,
            },
            "interpretation": {
                "reserves": "各交易所当前储备余额，按资产分组",
                "net_flows": "正值表示净流入交易所（潜在卖压），负值表示净流出（囤积信号）",
                "historical_lows": "储备触及历史低点的交易所，可能暗示供应紧缩",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="exchange_reserve_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="exchange_reserve_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
