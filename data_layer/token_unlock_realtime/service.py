"""token_unlock_realtime 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.token_unlock_realtime.client import TokenUnlockClient


class TokenUnlockRealtimeService:
    """代币解锁实时数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or TokenUnlockClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS upcoming_unlocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                token TEXT NOT NULL,
                unlock_date TEXT NOT NULL,
                amount_tokens REAL DEFAULT 0,
                amount_usd REAL DEFAULT 0,
                unlock_type TEXT DEFAULT '',
                pct_of_supply REAL DEFAULT 0,
                days_until INTEGER DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(project, token, unlock_date, collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS unlock_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                token TEXT NOT NULL,
                unlock_date TEXT NOT NULL,
                amount_tokens REAL DEFAULT 0,
                amount_usd REAL DEFAULT 0,
                unlock_type TEXT DEFAULT '',
                actual_price_impact REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(project, token, unlock_date, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upcoming_unlocks_date
            ON upcoming_unlocks(unlock_date, days_until)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_unlock_events_token
            ON unlock_events(token, unlock_date DESC)
        """)
        self.db.conn.commit()
        logger.info("token_unlock_realtime 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 token_unlock_realtime bootstrap")
        self._collect_upcoming_unlocks()
        self._collect_unlock_history()
        logger.info("token_unlock_realtime bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_upcoming_unlocks()
        logger.info("token_unlock_realtime collect_once 完成")

    def _collect_upcoming_unlocks(self):
        """采集即将到来的代币解锁事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        unlocks = self.client.fetch_upcoming_unlocks(days=30)

        if not unlocks:
            logger.warning("未获取到即将解锁的代币数据")
            return

        collected_count = 0
        for unlock in unlocks:
            project = unlock.get("project", "") or unlock.get("name", "")
            token = unlock.get("token", "") or unlock.get("symbol", "")
            unlock_date = unlock.get("unlock_date", "") or unlock.get("date", "")
            if not project or not token:
                continue

            amount_tokens = float(unlock.get("amount_tokens", 0) or 0)
            amount_usd = float(unlock.get("amount_usd", 0) or unlock.get("value_usd", 0) or 0)
            unlock_type = unlock.get("unlock_type", "") or unlock.get("type", "")
            pct_of_supply = float(unlock.get("pct_of_supply", 0) or unlock.get("percent", 0) or 0)
            days_until = int(unlock.get("days_until", 0) or 0)

            self.db.conn.execute("""
                INSERT OR REPLACE INTO upcoming_unlocks
                (project, token, unlock_date, amount_tokens, amount_usd,
                 unlock_type, pct_of_supply, days_until, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (project, token, unlock_date, amount_tokens, amount_usd,
                  unlock_type, pct_of_supply, days_until, now_iso))
            collected_count += 1

        self.db.conn.commit()
        logger.info(f"即将解锁事件采集完成，处理 {collected_count} 条记录")

    def _collect_unlock_history(self):
        """采集主要代币的历史解锁事件。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 从 upcoming 中获取活跃项目的 token 列表
        cursor = self.db.conn.execute("""
            SELECT DISTINCT token FROM upcoming_unlocks
            ORDER BY amount_usd DESC LIMIT 20
        """)
        tokens = [row[0] for row in cursor.fetchall()]

        if not tokens:
            logger.warning("无可用代币列表，跳过历史解锁采集")
            return

        collected_count = 0
        for token in tokens:
            events = self.client.fetch_unlock_history(token)
            if not events:
                continue

            for event in events:
                project = event.get("project", "") or event.get("name", "")
                unlock_date = event.get("unlock_date", "") or event.get("date", "")
                if not unlock_date:
                    continue

                amount_tokens = float(event.get("amount_tokens", 0) or 0)
                amount_usd = float(event.get("amount_usd", 0) or 0)
                unlock_type = event.get("unlock_type", "") or event.get("type", "")
                price_impact = float(event.get("actual_price_impact", 0) or event.get("price_impact", 0) or 0)

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO unlock_events
                    (project, token, unlock_date, amount_tokens, amount_usd,
                     unlock_type, actual_price_impact, timestamp, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (project, token, unlock_date, amount_tokens, amount_usd,
                      unlock_type, price_impact, now_iso, now_iso))
                collected_count += 1

        self.db.conn.commit()
        logger.info(f"历史解锁事件采集完成，处理 {collected_count} 条记录")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的代币解锁上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 获取最新即将解锁事件
        cursor = self.db.conn.execute("""
            SELECT project, token, unlock_date, amount_tokens, amount_usd,
                   unlock_type, pct_of_supply, days_until
            FROM upcoming_unlocks
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM upcoming_unlocks
            )
            ORDER BY days_until ASC, amount_usd DESC
        """)
        upcoming_rows = cursor.fetchall()

        # 获取历史解锁事件（最近）
        cursor = self.db.conn.execute("""
            SELECT project, token, unlock_date, amount_tokens, amount_usd,
                   unlock_type, actual_price_impact
            FROM unlock_events
            ORDER BY unlock_date DESC
            LIMIT 20
        """)
        history_rows = cursor.fetchall()

        if not upcoming_rows and not history_rows:
            return {"status": "no_data", "as_of": now_iso}

        upcoming_events = []
        for row in upcoming_rows:
            project, token, unlock_date, amount_tokens, amount_usd, \
                unlock_type, pct_of_supply, days_until = row
            upcoming_events.append({
                "project": project,
                "token": token,
                "unlock_date": unlock_date,
                "amount_tokens": round(amount_tokens, 2),
                "amount_usd": round(amount_usd, 2),
                "unlock_type": unlock_type,
                "pct_of_supply": round(pct_of_supply, 4),
                "days_until": days_until,
            })

        history_events = []
        for row in history_rows:
            project, token, unlock_date, amount_tokens, amount_usd, \
                unlock_type, price_impact = row
            history_events.append({
                "project": project,
                "token": token,
                "unlock_date": unlock_date,
                "amount_usd": round(amount_usd, 2),
                "unlock_type": unlock_type,
                "price_impact_pct": round(price_impact, 4),
            })

        return {
            "status": "ready",
            "as_of": now_iso,
            "unlock_signals": {
                "upcoming_count": len(upcoming_events),
                "upcoming_7d": [e for e in upcoming_events if e["days_until"] <= 7][:15],
                "upcoming_30d": upcoming_events[:20],
                "recent_history": history_events[:15],
            },
            "interpretation": {
                "pct_of_supply": "解锁占总供应量的百分比，越高对价格冲击越大",
                "days_until": "距解锁天数，0表示今天解锁",
                "price_impact_pct": "历史解锁后实际价格变化百分比（负=下跌）",
                "unlock_type": "cliff=一次性, linear=线性, team=团队, investor=投资者",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            id="token_unlock_realtime_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 60 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=60,
            id="token_unlock_realtime_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
