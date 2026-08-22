"""链上地址行为数据服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.onchain_address_data.client import OnchainAddressClient


class OnchainAddressService:
    """链上地址行为数据采集与分析服务。"""

    # 跟踪的知名巨鲸/基金地址
    TRACKED_ADDRESSES = [
        "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance Hot Wallet
        "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",  # Binance Cold Wallet
        "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F",  # Three Arrows Capital
        "0x1B3cB81E51011b549d78bf720b0d924ac763A7C2",  # Paradigm
        "0xDa9CE944a37d218c3302F6B82a094844C6ECEb17",  # Jump Trading
        "0x5f65f7b609678448494De4C87521CdF6cEf1e932",  # Wintermute
    ]

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or OnchainAddressClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS address_labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                label TEXT DEFAULT '',
                entity TEXT DEFAULT '',
                category TEXT DEFAULT '',
                source TEXT DEFAULT '',
                first_seen TEXT DEFAULT '',
                last_active TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        columns = {row[1] for row in self.db.conn.execute("PRAGMA table_info(address_labels)")}
        if "source" not in columns:
            self.db.conn.execute("ALTER TABLE address_labels ADD COLUMN source TEXT DEFAULT ''")
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS address_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                token TEXT DEFAULT '',
                direction TEXT DEFAULT '',
                amount_usd REAL DEFAULT 0,
                counterparty TEXT DEFAULT '',
                tx_hash TEXT DEFAULT '',
                timestamp TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(tx_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                entity TEXT DEFAULT '',
                token TEXT DEFAULT '',
                amount_usd REAL DEFAULT 0,
                direction TEXT DEFAULT '',
                from_exchange TEXT DEFAULT '',
                to_exchange TEXT DEFAULT '',
                timestamp TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(address, timestamp, token)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_address_flows_addr
            ON address_flows(address, timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_whale_moves_ts
            ON whale_moves(timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("onchain_address_data 存储初始化完成")

    def bootstrap(self):
        """首次回填：采集所有跟踪地址的标签和资金流。"""
        logger.info("开始 onchain_address_data bootstrap")
        self._update_labels()
        for addr in self.TRACKED_ADDRESSES:
            self._collect_address_flows(addr)
        self._collect_whale_alerts()
        logger.info("onchain_address_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期：公开地址标签 + 已授权时的巨鲸预警和资金流。"""
        self._update_labels()
        self._collect_whale_alerts()
        for addr in self.TRACKED_ADDRESSES:
            self._collect_address_flows(addr)
        logger.info("onchain_address_data collect_once 完成")

    def _collect_whale_alerts(self):
        """从 Arkham 获取并存储巨鲸异动事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        alerts = self.client.fetch_arkham_whale_alerts(min_usd=1_000_000)

        if not alerts:
            logger.debug("巨鲸预警数据为空")
            return

        count = 0
        for alert in alerts:
            address = alert.get("address", "")
            if not address:
                continue
            entity = alert.get("entity", "")
            token = alert.get("token", "ETH")
            amount_usd = float(alert.get("amount_usd", 0))
            direction = alert.get("direction", "transfer")
            from_exchange = alert.get("from_exchange", "")
            to_exchange = alert.get("to_exchange", "")
            timestamp = alert.get("timestamp", now_iso)

            try:
                self.db.conn.execute("""
                    INSERT OR IGNORE INTO whale_moves
                    (address, entity, token, amount_usd, direction,
                     from_exchange, to_exchange, timestamp, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (address, entity, token, amount_usd, direction,
                      from_exchange, to_exchange, timestamp, now_iso))
                count += 1
            except Exception as e:
                logger.debug(f"whale_moves 插入跳过: {e}")

        self.db.conn.commit()
        logger.info(f"巨鲸预警采集完成，处理 {count} 条记录")

    def _collect_address_flows(self, address: str):
        """从 Arkham 获取指定地址的资金流转记录。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        transfers = self.client.fetch_arkham_transfers(address, limit=50)

        if not transfers:
            logger.debug(f"地址 {address[:10]}... 无转账数据")
            return

        count = 0
        for tx in transfers:
            tx_hash = tx.get("tx_hash", "")
            if not tx_hash:
                continue
            token = tx.get("token", "ETH")
            amount_usd = float(tx.get("amount_usd", 0))
            counterparty = tx.get("counterparty", "")
            direction = tx.get("direction", "outflow")
            timestamp = tx.get("timestamp", now_iso)

            try:
                self.db.conn.execute("""
                    INSERT OR IGNORE INTO address_flows
                    (address, token, direction, amount_usd,
                     counterparty, tx_hash, timestamp, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (address, token, direction, amount_usd,
                      counterparty, tx_hash, timestamp, now_iso))
                count += 1
            except Exception as e:
                logger.debug(f"address_flows 插入跳过: {e}")

        self.db.conn.commit()
        logger.debug(f"地址 {address[:10]}... 资金流采集完成，{count} 条")

    def _update_labels(self):
        """从 Arkham 更新所有跟踪地址的标签信息。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        for address in self.TRACKED_ADDRESSES:
            entity_data = self.client.fetch_arkham_entity(address)
            if not entity_data:
                entity_data = self.client.fetch_public_label(address, chain="ethereum")
            if not entity_data:
                continue

            label = entity_data.get("label", "")
            entity = entity_data.get("entity", "")
            category = entity_data.get("category", "")
            first_seen = entity_data.get("first_seen", "")
            last_active = entity_data.get("last_active", "")
            source = entity_data.get("source", "arkham")

            self.db.conn.execute("""
            INSERT INTO address_labels
            (address, label, entity, category, source, first_seen, last_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                label=excluded.label,
                entity=excluded.entity,
                category=excluded.category,
                source=excluded.source,
                first_seen=excluded.first_seen,
                last_active=excluded.last_active,
                updated_at=excluded.updated_at
            """, (address, label, entity, category, source, first_seen,
                  last_active, now_iso))

        self.db.conn.commit()
        logger.info("地址标签更新完成")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的链上地址行为上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 最近巨鲸异动汇总
        cursor = self.db.conn.execute("""
            SELECT address, entity, token, amount_usd, direction,
                   from_exchange, to_exchange, timestamp
            FROM whale_moves
            ORDER BY timestamp DESC
            LIMIT 20
        """)
        whale_rows = cursor.fetchall()

        if not whale_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 统计净流向
        total_deposit = 0.0
        total_withdrawal = 0.0
        top_movers = {}

        whale_events = []
        for row in whale_rows:
            addr, entity, token, amount_usd, direction, from_ex, to_ex, ts = row
            whale_events.append({
                "address": addr[:10] + "...",
                "entity": entity,
                "token": token,
                "amount_usd": round(amount_usd, 2),
                "direction": direction,
                "timestamp": ts,
            })

            if direction == "deposit":
                total_deposit += amount_usd
            elif direction == "withdrawal":
                total_withdrawal += amount_usd

            # 统计 top movers
            key = entity or addr[:10]
            top_movers[key] = top_movers.get(key, 0) + amount_usd

        # 净流向判断
        net_flow = total_withdrawal - total_deposit
        if net_flow > 1_000_000:
            flow_direction = "net_withdrawal"
        elif net_flow < -1_000_000:
            flow_direction = "net_deposit"
        else:
            flow_direction = "neutral"

        # 排序 top movers
        sorted_movers = sorted(
            top_movers.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # 巨鲸活跃度
        whale_count = len(set(r[0] for r in whale_rows))
        activity_level = "high" if whale_count >= 5 else (
            "moderate" if whale_count >= 3 else "low"
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "whale_activity_level": activity_level,
                "net_flow_direction": flow_direction,
                "net_flow_usd": round(net_flow, 2),
                "total_deposit_usd": round(total_deposit, 2),
                "total_withdrawal_usd": round(total_withdrawal, 2),
            },
            "top_movers": [
                {"entity": k, "total_usd": round(v, 2)}
                for k, v in sorted_movers
            ],
            "recent_whale_events": whale_events[:10],
            "interpretation": {
                "activity": f"巨鲸活跃度: {activity_level}（{whale_count} 个独立地址）",
                "flow": f"净流向: {flow_direction}（净额 ${net_flow:,.0f}）",
                "signal": (
                    "大量提币离场，可能看涨持有" if flow_direction == "net_withdrawal"
                    else "大量充值入场，可能准备抛售" if flow_direction == "net_deposit"
                    else "资金流向中性，无明显方向"
                ),
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 10 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=10,
            id="onchain_address_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 10 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=10,
            id="onchain_address_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
