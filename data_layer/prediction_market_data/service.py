"""prediction_market_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.prediction_market_data.client import PredictionMarketClient


CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain",
    "solana", "sol", "defi", "nft", "web3", "token", "coin",
    "binance", "coinbase", "ripple", "xrp", "dogecoin", "doge",
]


class PredictionMarketDataService:
    """预测市场数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or PredictionMarketClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_markets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                question TEXT NOT NULL,
                outcome_yes_price REAL DEFAULT 0,
                outcome_no_price REAL DEFAULT 0,
                volume_24h REAL DEFAULT 0,
                liquidity REAL DEFAULT 0,
                end_date TEXT DEFAULT '',
                category TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(market_id, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS prediction_market_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                question TEXT NOT NULL,
                outcome_yes_price REAL DEFAULT 0,
                outcome_no_price REAL DEFAULT 0,
                volume_24h REAL DEFAULT 0,
                liquidity REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(market_id, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prediction_markets_id
            ON prediction_markets(market_id, collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_prediction_market_history_id
            ON prediction_market_history(market_id, collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("prediction_market_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 prediction_market_data bootstrap")
        self._collect_markets()
        logger.info("prediction_market_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_markets()
        logger.info("prediction_market_data collect_once 完成")

    def _collect_markets(self):
        """从 Polymarket 采集活跃市场数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        markets = self.client.fetch_active_markets()

        if not markets:
            logger.warning("Polymarket 未返回活跃市场数据")
            return

        collected_count = 0
        for market in markets:
            market_id = market.get("condition_id", "") or market.get("id", "")
            question = market.get("question", "")
            if not market_id or not question:
                continue

            # 解析价格数据
            tokens = market.get("tokens", [])
            outcome_yes_price = 0.0
            outcome_no_price = 0.0
            if tokens and len(tokens) >= 2:
                outcome_yes_price = float(tokens[0].get("price", 0) or 0)
                outcome_no_price = float(tokens[1].get("price", 0) or 0)
            elif tokens and len(tokens) == 1:
                outcome_yes_price = float(tokens[0].get("price", 0) or 0)
                outcome_no_price = round(1.0 - outcome_yes_price, 4)

            volume_24h = float(market.get("volume_num_24hr", 0) or market.get("volume24hr", 0) or 0)
            liquidity = float(market.get("liquidity", 0) or 0)
            end_date = market.get("end_date_iso", "") or market.get("end_date", "")
            category = market.get("category", "") or market.get("tags", [""])[0] if market.get("tags") else ""

            self.db.conn.execute("""
                INSERT OR REPLACE INTO prediction_markets
                (market_id, question, outcome_yes_price, outcome_no_price,
                 volume_24h, liquidity, end_date, category, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (market_id, question, outcome_yes_price, outcome_no_price,
                  volume_24h, liquidity, end_date, category, now_iso))

            # 同时写入历史表用于追踪概率变化
            self.db.conn.execute("""
                INSERT OR REPLACE INTO prediction_market_history
                (market_id, question, outcome_yes_price, outcome_no_price,
                 volume_24h, liquidity, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (market_id, question, outcome_yes_price, outcome_no_price,
                  volume_24h, liquidity, now_iso))

            collected_count += 1

        self.db.conn.commit()
        logger.info(f"Polymarket 采集完成，处理 {collected_count} 个市场")

    def _is_crypto_related(self, question: str) -> bool:
        """判断市场问题是否与加密货币相关。"""
        q_lower = question.lower()
        return any(kw in q_lower for kw in CRYPTO_KEYWORDS)

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的预测市场上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新活跃市场快照
        cursor = self.db.conn.execute("""
            SELECT market_id, question, outcome_yes_price, outcome_no_price,
                   volume_24h, liquidity, end_date, category
            FROM prediction_markets
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM prediction_markets
            )
            ORDER BY volume_24h DESC
        """)
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        # 分离加密相关市场
        crypto_markets = []
        all_markets = []
        for row in rows:
            market_id, question, yes_price, no_price, vol, liq, end, cat = row
            entry = {
                "market_id": market_id,
                "question": question,
                "yes_probability": round(yes_price, 4),
                "no_probability": round(no_price, 4),
                "volume_24h": round(vol, 2),
                "liquidity": round(liq, 2),
                "end_date": end,
                "category": cat,
            }
            all_markets.append(entry)
            if self._is_crypto_related(question):
                crypto_markets.append(entry)

        # 概率变化检测（与上一次采集比较）
        probability_changes = self._detect_probability_changes()

        return {
            "status": "ready",
            "as_of": now_iso,
            "market_signals": {
                "active_markets_count": len(all_markets),
                "crypto_related_markets": crypto_markets[:20],
                "top_volume_markets": all_markets[:20],
                "probability_changes": probability_changes[:15],
            },
            "interpretation": {
                "yes_probability": "YES 结果价格即为市场预测概率 (0-1)",
                "volume": "24h 交易量越高表示市场关注度越大",
                "probability_changes": "概率显著变化的市场可能反映重要事件或信息",
            },
        }

    def _detect_probability_changes(self) -> list[dict]:
        """检测概率显著变化的市场。"""
        cursor = self.db.conn.execute("""
            SELECT DISTINCT collected_at
            FROM prediction_market_history
            ORDER BY collected_at DESC
            LIMIT 2
        """)
        timestamps = [row[0] for row in cursor.fetchall()]

        if len(timestamps) < 2:
            return []

        latest_ts, prev_ts = timestamps[0], timestamps[1]

        cursor = self.db.conn.execute("""
            SELECT h1.market_id, h1.question,
                   h1.outcome_yes_price AS current_yes,
                   h2.outcome_yes_price AS prev_yes
            FROM prediction_market_history h1
            JOIN prediction_market_history h2
                ON h1.market_id = h2.market_id
            WHERE h1.collected_at = ? AND h2.collected_at = ?
        """, (latest_ts, prev_ts))

        changes = []
        for row in cursor.fetchall():
            market_id, question, current_yes, prev_yes = row
            delta = current_yes - prev_yes
            if abs(delta) >= 0.02:  # 2% 概率变化视为显著
                changes.append({
                    "market_id": market_id,
                    "question": question,
                    "current_probability": round(current_yes, 4),
                    "previous_probability": round(prev_yes, 4),
                    "change": round(delta, 4),
                })

        changes.sort(key=lambda x: abs(x["change"]), reverse=True)
        return changes

    def build_scheduler(self):
        """构建阻塞式调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="prediction_market_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="prediction_market_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
