"""whale_tracker_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from config.symbols import TARGET_ASSET_CODES
from data_layer.whale_tracker_data.client import WhaleTrackerClient


# 追踪的主要标的
TARGET_SYMBOLS = TARGET_ASSET_CODES

# 最小追踪金额（USD）
MIN_WHALE_TX_USD = 500_000


class WhaleTrackerDataService:
    """巨鲸追踪数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or WhaleTrackerClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT NOT NULL,
                chain TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                from_address TEXT,
                to_address TEXT,
                from_label TEXT DEFAULT 'unknown',
                to_label TEXT DEFAULT 'unknown',
                amount_usd REAL NOT NULL,
                amount_native REAL,
                tx_time TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(tx_hash, chain)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_flow_agg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                total_volume_usd REAL DEFAULT 0,
                deposit_volume_usd REAL DEFAULT 0,
                withdrawal_volume_usd REAL DEFAULT 0,
                net_flow_usd REAL DEFAULT 0,
                tx_count INTEGER DEFAULT 0,
                unique_whales INTEGER DEFAULT 0,
                largest_tx_usd REAL DEFAULT 0,
                flow_direction TEXT DEFAULT 'neutral',
                collected_at TEXT NOT NULL,
                UNIQUE(entity_key, interval, window_start)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_whale_tx_entity_time
            ON whale_transactions(entity_key, tx_time DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_whale_agg_entity_time
            ON whale_flow_agg(entity_key, window_start DESC)
        """)
        self.db.conn.commit()
        logger.info("whale_tracker_data 存储初始化完成")

    def bootstrap(self, symbols: list[str] | None = None):
        """首次回填：拉取最近交易数据。"""
        symbols = symbols or TARGET_SYMBOLS
        logger.info(f"开始 bootstrap，目标: {symbols}")
        self._collect_whale_alert(symbols)
        for symbol in symbols:
            self._collect_arkham(symbol)
        self._compute_aggregations(symbols)
        logger.info("bootstrap 完成")

    def collect_once(self, symbols: list[str] | None = None):
        """执行一次采集周期。"""
        symbols = symbols or TARGET_SYMBOLS
        self._collect_whale_alert(symbols)
        for symbol in symbols:
            self._collect_arkham(symbol)
        self._compute_aggregations(symbols)
        logger.info(f"collect_once 完成，处理 {len(symbols)} 个标的")

    def _collect_whale_alert(self, symbols: list[str]):
        """采集 Whale Alert 大额转账。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        txs = self.client.fetch_whale_alert_transactions(min_value_usd=MIN_WHALE_TX_USD)
        for tx in txs:
            symbol = tx.get("symbol", "").upper()
            if symbol not in symbols:
                continue
            tx_hash = tx.get("hash", tx.get("id", ""))
            chain = tx.get("blockchain", "unknown")
            amount_usd = float(tx.get("amount_usd", 0))
            amount_native = float(tx.get("amount", 0))
            tx_time = datetime.fromtimestamp(
                tx.get("timestamp", 0), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S")

            from_owner = tx.get("from", {}).get("owner_type", "unknown")
            to_owner = tx.get("to", {}).get("owner_type", "unknown")
            from_addr = tx.get("from", {}).get("address", "")
            to_addr = tx.get("to", {}).get("address", "")

            # 判断交易类型
            if to_owner == "exchange":
                tx_type = "deposit"
            elif from_owner == "exchange":
                tx_type = "withdrawal"
            else:
                tx_type = "transfer"

            self.db.conn.execute("""
                INSERT OR IGNORE INTO whale_transactions
                (tx_hash, chain, entity_key, from_address, to_address,
                 from_label, to_label, amount_usd, amount_native,
                 tx_time, tx_type, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tx_hash, chain, symbol, from_addr, to_addr,
                  from_owner, to_owner, amount_usd, amount_native,
                  tx_time, tx_type, now_iso))
        self.db.conn.commit()

    def _collect_arkham(self, symbol: str):
        """采集 Arkham 标记地址数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        transfers = self.client.fetch_arkham_transfers(symbol.lower())
        for tx in transfers:
            tx_hash = tx.get("transactionHash", "")
            if not tx_hash:
                continue
            chain = tx.get("chain", "ethereum")
            amount_usd = float(tx.get("unitValueUsd", 0) or 0)
            if amount_usd < MIN_WHALE_TX_USD:
                continue

            self.db.conn.execute("""
                INSERT OR IGNORE INTO whale_transactions
                (tx_hash, chain, entity_key, from_address, to_address,
                 from_label, to_label, amount_usd, amount_native,
                 tx_time, tx_type, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx_hash, chain, symbol,
                tx.get("fromAddress", ""),
                tx.get("toAddress", ""),
                tx.get("fromLabel", "unknown"),
                tx.get("toLabel", "unknown"),
                amount_usd,
                float(tx.get("unitValue", 0) or 0),
                tx.get("blockTimestamp", now_iso),
                self._infer_tx_type(tx.get("fromLabel", ""), tx.get("toLabel", "")),
                now_iso,
            ))
        self.db.conn.commit()

    @staticmethod
    def _infer_tx_type(from_label: str, to_label: str) -> str:
        if "exchange" in to_label.lower():
            return "deposit"
        if "exchange" in from_label.lower():
            return "withdrawal"
        return "transfer"

    def _compute_aggregations(self, symbols: list[str]):
        """计算巨鲸流向聚合。"""
        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        window_start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

        for symbol in symbols:
            cursor = self.db.conn.execute("""
                SELECT amount_usd, tx_type, from_address
                FROM whale_transactions
                WHERE entity_key = ? AND tx_time >= ?
            """, (symbol, window_start))
            rows = cursor.fetchall()
            if not rows:
                continue

            total_vol = sum(r[0] for r in rows)
            deposit_vol = sum(r[0] for r in rows if r[1] == "deposit")
            withdrawal_vol = sum(r[0] for r in rows if r[1] == "withdrawal")
            net_flow = deposit_vol - withdrawal_vol
            largest = max(r[0] for r in rows)
            unique_addrs = len(set(r[2] for r in rows if r[2]))

            if net_flow > total_vol * 0.2:
                direction = "distribution"
            elif net_flow < -total_vol * 0.2:
                direction = "accumulation"
            else:
                direction = "neutral"

            self.db.conn.execute("""
                INSERT OR REPLACE INTO whale_flow_agg
                (entity_key, interval, window_start, window_end,
                 total_volume_usd, deposit_volume_usd, withdrawal_volume_usd,
                 net_flow_usd, tx_count, unique_whales, largest_tx_usd,
                 flow_direction, collected_at)
                VALUES (?, '1d', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, window_start, now_iso, total_vol, deposit_vol,
                  withdrawal_vol, net_flow, len(rows), unique_addrs,
                  largest, direction, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的巨鲸活动上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        placeholders = ",".join("?" * len(symbols))
        cursor = self.db.conn.execute(f"""
            SELECT entity_key, interval, window_start, total_volume_usd,
                   deposit_volume_usd, withdrawal_volume_usd, net_flow_usd,
                   tx_count, unique_whales, largest_tx_usd, flow_direction
            FROM whale_flow_agg
            WHERE entity_key IN ({placeholders})
            ORDER BY window_start DESC
        """, tuple(symbols))
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        entity_data = {}
        for row in rows:
            key = row[0]
            if key in entity_data:
                continue  # 只取最新
            entity_data[key] = {
                "total_volume_usd": round(row[3], 2),
                "deposit_volume_usd": round(row[4], 2),
                "withdrawal_volume_usd": round(row[5], 2),
                "net_flow_usd": round(row[6], 2),
                "tx_count": row[7],
                "unique_whales": row[8],
                "largest_tx_usd": round(row[9], 2),
                "flow_direction": row[10],
            }

        # 全局信号
        total_net = sum(v["net_flow_usd"] for v in entity_data.values())
        distribution_count = sum(1 for v in entity_data.values() if v["flow_direction"] == "distribution")
        accumulation_count = sum(1 for v in entity_data.values() if v["flow_direction"] == "accumulation")

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "coverage": {
                "symbols_with_data": len(entity_data),
                "symbols_requested": len(symbols),
            },
            "market_signal": {
                "total_net_flow_usd": round(total_net, 2),
                "distribution_assets": distribution_count,
                "accumulation_assets": accumulation_count,
                "bias": "distribution" if total_net > 0 else "accumulation" if total_net < 0 else "neutral",
            },
            "entities": entity_data,
            "raw_row_count": len(rows),
        }

    def build_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            kwargs={"symbols": symbols}, id="whale_tracker_collect",
        )
        return scheduler

    def build_async_scheduler(self, symbols: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            kwargs={"symbols": symbols}, id="whale_tracker_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
