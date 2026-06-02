"""whale_wallet_pnl 服务层。"""

import json
from datetime import datetime, timezone

from loguru import logger

from data_layer.whale_wallet_pnl.client import WhaleWalletPnlClient


# 默认追踪的知名巨鲸钱包地址
DEFAULT_WHALE_WALLETS = [
    {"address": "0x28C6c06298d514Db089934071355E5743bf21d60", "label": "Binance Hot"},
    {"address": "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549", "label": "Binance Cold"},
    {"address": "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503", "label": "Binance 8"},
    {"address": "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d", "label": "Alameda"},
    {"address": "0x56Eddb7aa87536c09CCc2793473599fD21A8b17F", "label": "Cumberland"},
]


class WhaleWalletPnlService:
    """巨鲸钱包 PnL 追踪采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or WhaleWalletPnlClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                label TEXT DEFAULT '',
                total_value_usd REAL DEFAULT 0,
                pnl_24h REAL DEFAULT 0,
                pnl_7d REAL DEFAULT 0,
                pnl_30d REAL DEFAULT 0,
                top_holdings_json TEXT DEFAULT '[]',
                unrealized_pnl_pct REAL DEFAULT 0,
                realized_pnl_24h REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(address, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS whale_pnl_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                date TEXT NOT NULL,
                total_value_usd REAL DEFAULT 0,
                pnl_daily REAL DEFAULT 0,
                cumulative_pnl REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(address, date)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_whale_portfolios_address
            ON whale_portfolios(address, timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_whale_pnl_history_address
            ON whale_pnl_history(address, date DESC)
        """)
        self.db.conn.commit()
        logger.info("whale_wallet_pnl 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 whale_wallet_pnl bootstrap")
        self._collect_portfolios()
        self._collect_pnl_history()
        logger.info("whale_wallet_pnl bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_portfolios()
        logger.info("whale_wallet_pnl collect_once 完成")

    def _collect_portfolios(self):
        """采集所有追踪巨鲸钱包的投资组合。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        collected_count = 0

        for wallet in DEFAULT_WHALE_WALLETS:
            address = wallet["address"]
            label = wallet["label"]
            data = self.client.fetch_whale_portfolio(address)
            if not data:
                continue

            total_value = float(data.get("total_usd_value", 0) or 0)
            # 从 chain_list 中提取 top holdings
            chain_list = data.get("chain_list", [])
            top_holdings = []
            for chain_info in chain_list[:5]:
                top_holdings.append({
                    "chain": chain_info.get("id", ""),
                    "usd_value": chain_info.get("usd_value", 0),
                })

            self.db.conn.execute("""
                INSERT OR REPLACE INTO whale_portfolios
                (address, label, total_value_usd, pnl_24h, pnl_7d, pnl_30d,
                 top_holdings_json, unrealized_pnl_pct, realized_pnl_24h,
                 timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (address, label, total_value, 0.0, 0.0, 0.0,
                  json.dumps(top_holdings), 0.0, 0.0, now_iso, now_iso))
            collected_count += 1

        self.db.conn.commit()
        logger.info(f"巨鲸钱包组合采集完成，处理 {collected_count} 个钱包")

    def _collect_pnl_history(self):
        """采集巨鲸钱包的 PnL 历史数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        collected_count = 0

        for wallet in DEFAULT_WHALE_WALLETS:
            address = wallet["address"]
            history = self.client.fetch_pnl_history(address)
            if not history:
                continue

            prev_value = None
            cumulative_pnl = 0.0
            for entry in history:
                # DeBank 格式: [timestamp, usd_value]
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    ts = int(entry[0])
                    value = float(entry[1])
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                elif isinstance(entry, dict):
                    date_str = entry.get("date", "")
                    value = float(entry.get("total_value_usd", 0) or entry.get("usd_value", 0) or 0)
                else:
                    continue

                pnl_daily = 0.0
                if prev_value is not None:
                    pnl_daily = value - prev_value
                cumulative_pnl += pnl_daily
                prev_value = value

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO whale_pnl_history
                    (address, date, total_value_usd, pnl_daily, cumulative_pnl, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (address, date_str, value, pnl_daily, cumulative_pnl, now_iso))
                collected_count += 1

        self.db.conn.commit()
        logger.info(f"巨鲸 PnL 历史采集完成，处理 {collected_count} 条记录")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的巨鲸钱包 PnL 上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新钱包组合快照
        cursor = self.db.conn.execute("""
            SELECT address, label, total_value_usd, pnl_24h, pnl_7d, pnl_30d,
                   top_holdings_json, unrealized_pnl_pct, realized_pnl_24h
            FROM whale_portfolios
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM whale_portfolios
            )
            ORDER BY total_value_usd DESC
        """)
        portfolio_rows = cursor.fetchall()

        # 获取最近 PnL 历史
        cursor = self.db.conn.execute("""
            SELECT address, date, total_value_usd, pnl_daily, cumulative_pnl
            FROM whale_pnl_history
            ORDER BY date DESC
            LIMIT 50
        """)
        history_rows = cursor.fetchall()

        if not portfolio_rows and not history_rows:
            return {"status": "no_data", "as_of": now_iso}

        portfolios = []
        for row in portfolio_rows:
            (address, label, total_val, pnl_24, pnl_7, pnl_30,
             holdings_json, unrealized, realized) = row
            portfolios.append({
                "address": address[:10] + "...",
                "label": label,
                "total_value_usd": round(total_val, 2),
                "pnl_24h": round(pnl_24, 2),
                "pnl_7d": round(pnl_7, 2),
                "pnl_30d": round(pnl_30, 2),
                "top_holdings": json.loads(holdings_json) if holdings_json else [],
                "unrealized_pnl_pct": round(unrealized, 4),
                "realized_pnl_24h": round(realized, 2),
            })

        pnl_history = []
        for row in history_rows:
            address, date, total_val, pnl_daily, cum_pnl = row
            pnl_history.append({
                "address": address[:10] + "...",
                "date": date,
                "total_value_usd": round(total_val, 2),
                "pnl_daily": round(pnl_daily, 2),
                "cumulative_pnl": round(cum_pnl, 2),
            })

        return {
            "status": "ready",
            "as_of": now_iso,
            "whale_signals": {
                "tracked_wallets": len(portfolios),
                "portfolios": portfolios,
                "recent_pnl_history": pnl_history[:20],
            },
            "interpretation": {
                "total_value_usd": "钱包总资产价值 (USD)",
                "pnl_24h": "24小时盈亏 (正=盈利, 负=亏损)",
                "unrealized_pnl_pct": "未实现盈亏百分比",
                "cumulative_pnl": "从追踪开始的累计盈亏",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="whale_wallet_pnl_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 30 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=30,
            id="whale_wallet_pnl_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
