"""perpetual_dex_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.perpetual_dex_data.client import PerpDexDataClient


class PerpDexDataService:
    """永续合约 DEX 数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or PerpDexDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS perp_dex_funding (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                funding_rate REAL DEFAULT 0,
                next_funding_ts TEXT DEFAULT '',
                open_interest_usd REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, symbol, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS perp_dex_volume (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                volume_24h_usd REAL DEFAULT 0,
                trades_24h INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, symbol, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_perp_funding_exchange
            ON perp_dex_funding(exchange, symbol, collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_perp_volume_exchange
            ON perp_dex_volume(exchange, symbol, collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("perpetual_dex_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 perpetual_dex_data bootstrap")
        self._collect_all_exchanges()
        logger.info("perpetual_dex_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_all_exchanges()
        logger.info("perpetual_dex_data collect_once 完成")

    def _collect_all_exchanges(self):
        """从所有交易所采集数据。"""
        self._collect_dydx()
        self._collect_hyperliquid()
        self._collect_gmx()

    def _collect_dydx(self):
        """从 dYdX 采集资金费率和交易量数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        markets = self.client.fetch_dydx_markets()

        if not markets:
            logger.warning("dYdX 未返回市场数据")
            return

        for market in markets:
            symbol = market.get("ticker", "")
            if not symbol:
                continue

            # 资金费率与未平仓合约
            funding_rate = float(market.get("nextFundingRate", 0) or 0)
            open_interest = float(market.get("openInterest", 0) or 0)
            oracle_price = float(market.get("oraclePrice", 0) or 0)
            oi_usd = open_interest * oracle_price

            self.db.conn.execute("""
                INSERT OR REPLACE INTO perp_dex_funding
                (exchange, symbol, funding_rate, next_funding_ts,
                 open_interest_usd, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("dydx", symbol, funding_rate, "", oi_usd, now_iso))

            # 交易量数据
            volume_24h = float(market.get("volume24H", 0) or 0)
            trades_24h = int(market.get("trades24H", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO perp_dex_volume
                (exchange, symbol, volume_24h_usd, trades_24h, collected_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("dydx", symbol, volume_24h, trades_24h, now_iso))

        self.db.conn.commit()
        logger.info(f"dYdX 采集完成，处理 {len(markets)} 个市场")

    def _collect_hyperliquid(self):
        """从 Hyperliquid 采集资金费率和未平仓合约数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取元数据和资产上下文（包含 OI 和资金费率）
        meta_and_ctxs = self.client.fetch_hyperliquid_open_interest()
        if not meta_and_ctxs or len(meta_and_ctxs) < 2:
            logger.warning("Hyperliquid metaAndAssetCtxs 数据不完整")
            return

        meta = meta_and_ctxs[0] if isinstance(meta_and_ctxs[0], dict) else {}
        asset_ctxs = meta_and_ctxs[1] if isinstance(meta_and_ctxs[1], list) else []
        universe = meta.get("universe", [])

        for i, ctx in enumerate(asset_ctxs):
            if i >= len(universe):
                break

            symbol = universe[i].get("name", "")
            if not symbol:
                continue

            funding_rate = float(ctx.get("funding", 0) or 0)
            open_interest = float(ctx.get("openInterest", 0) or 0)
            mark_price = float(ctx.get("markPx", 0) or 0)
            oi_usd = open_interest * mark_price

            self.db.conn.execute("""
                INSERT OR REPLACE INTO perp_dex_funding
                (exchange, symbol, funding_rate, next_funding_ts,
                 open_interest_usd, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("hyperliquid", symbol, funding_rate, "", oi_usd, now_iso))

            # Hyperliquid 交易量（从 ctx 中提取）
            volume_24h = float(ctx.get("dayNtlVlm", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO perp_dex_volume
                (exchange, symbol, volume_24h_usd, trades_24h, collected_at)
                VALUES (?, ?, ?, ?, ?)
            """, ("hyperliquid", symbol, volume_24h, 0, now_iso))

        self.db.conn.commit()
        logger.info(f"Hyperliquid 采集完成，处理 {len(asset_ctxs)} 个资产")

    def _collect_gmx(self):
        """从 GMX 采集资金费率数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        funding_data = self.client.fetch_gmx_funding()

        if not funding_data:
            logger.warning("GMX 未返回资金费率数据")
            return

        for item in funding_data:
            symbol = item.get("symbol", "") or item.get("token", "")
            if not symbol:
                continue

            funding_rate = float(item.get("fundingRate", 0) or 0)
            open_interest = float(item.get("openInterest", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO perp_dex_funding
                (exchange, symbol, funding_rate, next_funding_ts,
                 open_interest_usd, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("gmx", symbol, funding_rate, "", open_interest, now_iso))

        self.db.conn.commit()
        logger.info(f"GMX 采集完成，处理 {len(funding_data)} 条记录")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的永续合约 DEX 上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取各交易所最新资金费率
        cursor = self.db.conn.execute("""
            SELECT exchange, symbol, funding_rate, open_interest_usd
            FROM perp_dex_funding
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM perp_dex_funding
            )
            ORDER BY open_interest_usd DESC
        """)
        funding_rows = cursor.fetchall()

        if not funding_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 按交易所分组资金费率
        exchange_funding = {}
        for row in funding_rows:
            exchange, symbol, rate, oi = row
            if exchange not in exchange_funding:
                exchange_funding[exchange] = []
            exchange_funding[exchange].append({
                "symbol": symbol,
                "funding_rate": round(rate, 6),
                "open_interest_usd": round(oi, 2),
            })

        # 获取交易量分布
        vol_cursor = self.db.conn.execute("""
            SELECT exchange, SUM(volume_24h_usd) as total_vol
            FROM perp_dex_volume
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM perp_dex_volume
            )
            GROUP BY exchange
            ORDER BY total_vol DESC
        """)
        vol_rows = vol_cursor.fetchall()
        volume_distribution = {
            row[0]: round(row[1], 2) for row in vol_rows
        }

        # 计算跨交易所资金费率对比
        funding_comparison = {}
        for row in funding_rows:
            exchange, symbol, rate, oi = row
            if symbol not in funding_comparison:
                funding_comparison[symbol] = {}
            funding_comparison[symbol][exchange] = round(rate, 6)

        # OI 趋势（按交易所汇总）
        oi_by_exchange = {}
        for row in funding_rows:
            exchange, symbol, rate, oi = row
            oi_by_exchange[exchange] = oi_by_exchange.get(exchange, 0) + oi
        oi_by_exchange = {k: round(v, 2) for k, v in oi_by_exchange.items()}

        # 资金费率异常检测（绝对值 > 0.01% 视为显著）
        significant_funding = []
        for row in funding_rows:
            exchange, symbol, rate, oi = row
            if abs(rate) > 0.0001:
                significant_funding.append({
                    "exchange": exchange,
                    "symbol": symbol,
                    "funding_rate": round(rate, 6),
                })

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "funding_rate_comparison": funding_comparison,
                "oi_by_exchange": oi_by_exchange,
                "volume_distribution": volume_distribution,
                "significant_funding_rates": significant_funding[:20],
            },
            "interpretation": {
                "funding": "跨交易所资金费率对比，正值表示多头支付空头",
                "oi_trend": "各交易所未平仓合约总量分布",
                "volume": "24h 交易量在各 DEX 之间的分布",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="perpetual_dex_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="perpetual_dex_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
