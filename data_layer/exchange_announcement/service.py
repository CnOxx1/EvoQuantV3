"""exchange_announcement 服务层。"""

import json
import re
from datetime import datetime, timezone

from loguru import logger

from data_layer.exchange_announcement.client import ExchangeAnnouncementClient


class ExchangeAnnouncementService:
    """交易所公告数据采集与聚合服务。"""

    # 用于从标题中提取代币名称的正则
    TOKEN_PATTERN = re.compile(r'\b([A-Z]{2,10})\b')

    # 关键词分类映射
    CATEGORY_KEYWORDS = {
        "listing": ["list", "trading", "new", "launch", "add"],
        "delisting": ["delist", "remov", "suspend"],
        "maintenance": ["maintenance", "upgrade", "wallet"],
    }

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or ExchangeAnnouncementClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                affected_tokens_json TEXT DEFAULT '[]',
                published_at TEXT NOT NULL,
                url TEXT DEFAULT '',
                severity TEXT DEFAULT 'low',
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, title, published_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS listing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                token TEXT NOT NULL,
                event_type TEXT NOT NULL,
                announced_at TEXT NOT NULL,
                effective_at TEXT DEFAULT '',
                url TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(exchange, token, event_type, announced_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcements_time
            ON exchange_announcements(published_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_listing_events_token
            ON listing_events(token, announced_at DESC)
        """)
        self.db.conn.commit()
        logger.info("exchange_announcement 存储初始化完成")

    def bootstrap(self):
        """首次回填公告数据。"""
        logger.info("开始 exchange_announcement bootstrap")
        self.collect_once()
        logger.info("exchange_announcement bootstrap 完成")

    def collect_once(self):
        """执行一次完整采集周期。"""
        self._collect_binance()
        self._collect_okx()
        self._collect_bybit()
        logger.info("exchange_announcement collect_once 完成")

    def _classify_announcement(self, title: str) -> tuple[str, str]:
        """根据标题关键词分类公告，返回 (category, severity)。"""
        title_lower = title.lower()
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in title_lower:
                    severity = "high" if category in ("listing", "delisting") else "medium"
                    return category, severity
        return "other", "low"

    def _extract_tokens(self, title: str) -> list[str]:
        """从标题中提取可能的代币名称。"""
        # 排除常见非代币大写词
        exclude = {"THE", "AND", "FOR", "NEW", "ALL", "NOW", "USD", "API", "APP"}
        matches = self.TOKEN_PATTERN.findall(title)
        return [m for m in matches if m not in exclude]

    def _collect_binance(self):
        """采集 Binance 公告。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        articles = self.client.fetch_binance_announcements()
        for article in articles:
            title = article.get("title", "")
            pub_ts = article.get("releaseDate", 0)
            if pub_ts:
                published_at = datetime.fromtimestamp(
                    pub_ts / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S")
            else:
                published_at = now_iso
            url = f"https://www.binance.com/en/support/announcement/{article.get('code', '')}"
            category, severity = self._classify_announcement(title)
            tokens = self._extract_tokens(title)
            self.db.conn.execute("""
                INSERT OR IGNORE INTO exchange_announcements
                (exchange, title, category, affected_tokens_json,
                 published_at, url, severity, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("binance", title, category, json.dumps(tokens),
                  published_at, url, severity, now_iso, now_iso))
            # 提取上币/下币事件
            if category in ("listing", "delisting"):
                for token in tokens:
                    event_type = category
                    self.db.conn.execute("""
                        INSERT OR IGNORE INTO listing_events
                        (exchange, token, event_type, announced_at,
                         effective_at, url, collected_at)
                        VALUES (?, ?, ?, ?, '', ?, ?)
                    """, ("binance", token, event_type, published_at,
                          url, now_iso))
        self.db.conn.commit()

    def _collect_okx(self):
        """采集 OKX 公告。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        announcements = self.client.fetch_okx_announcements()
        for ann in announcements:
            title = ann.get("title", "")
            published_at = ann.get("pTime", now_iso)
            url = ann.get("url", "")
            category, severity = self._classify_announcement(title)
            tokens = self._extract_tokens(title)
            self.db.conn.execute("""
                INSERT OR IGNORE INTO exchange_announcements
                (exchange, title, category, affected_tokens_json,
                 published_at, url, severity, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("okx", title, category, json.dumps(tokens),
                  published_at, url, severity, now_iso, now_iso))
            if category in ("listing", "delisting"):
                for token in tokens:
                    self.db.conn.execute("""
                        INSERT OR IGNORE INTO listing_events
                        (exchange, token, event_type, announced_at,
                         effective_at, url, collected_at)
                        VALUES (?, ?, ?, ?, '', ?, ?)
                    """, ("okx", token, category, published_at,
                          url, now_iso))
        self.db.conn.commit()

    def _collect_bybit(self):
        """采集 Bybit 公告。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        announcements = self.client.fetch_bybit_announcements()
        for ann in announcements:
            title = ann.get("title", "")
            pub_ts = ann.get("publishTime", 0)
            if pub_ts:
                published_at = datetime.fromtimestamp(
                    int(pub_ts) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S")
            else:
                published_at = now_iso
            url = ann.get("url", "")
            category, severity = self._classify_announcement(title)
            tokens = self._extract_tokens(title)
            self.db.conn.execute("""
                INSERT OR IGNORE INTO exchange_announcements
                (exchange, title, category, affected_tokens_json,
                 published_at, url, severity, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("bybit", title, category, json.dumps(tokens),
                  published_at, url, severity, now_iso, now_iso))
            if category in ("listing", "delisting"):
                for token in tokens:
                    self.db.conn.execute("""
                        INSERT OR IGNORE INTO listing_events
                        (exchange, token, event_type, announced_at,
                         effective_at, url, collected_at)
                        VALUES (?, ?, ?, ?, '', ?, ?)
                    """, ("bybit", token, category, published_at,
                          url, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的交易所公告上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 最近公告
        cursor = self.db.conn.execute("""
            SELECT exchange, title, category, affected_tokens_json,
                   published_at, severity
            FROM exchange_announcements
            WHERE published_at >= datetime('now', '-24 hours')
            ORDER BY published_at DESC
            LIMIT 30
        """)
        ann_rows = cursor.fetchall()

        # 最近上币/下币事件
        cursor = self.db.conn.execute("""
            SELECT exchange, token, event_type, announced_at, url
            FROM listing_events
            WHERE announced_at >= datetime('now', '-7 days')
            ORDER BY announced_at DESC
            LIMIT 20
        """)
        event_rows = cursor.fetchall()

        if not ann_rows and not event_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 公告摘要
        announcements = []
        for row in ann_rows:
            announcements.append({
                "exchange": row[0],
                "title": row[1],
                "category": row[2],
                "affected_tokens": json.loads(row[3]) if row[3] else [],
                "published_at": row[4],
                "severity": row[5],
            })

        # 上币/下币事件
        listing_events = []
        for row in event_rows:
            listing_events.append({
                "exchange": row[0],
                "token": row[1],
                "event_type": row[2],
                "announced_at": row[3],
            })

        # 高严重性警报
        high_severity = [a for a in announcements if a["severity"] == "high"]

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "announcements": announcements,
            "listing_events": listing_events,
            "alerts": {
                "high_severity_count": len(high_severity),
                "new_listings": [e for e in listing_events if e["event_type"] == "listing"],
                "delistings": [e for e in listing_events if e["event_type"] == "delisting"],
            },
            "coverage": {
                "exchanges_tracked": 3,
                "announcements_24h": len(ann_rows),
            },
        }

    def build_scheduler(self):
        """构建 BlockingScheduler，每 15 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="exchange_announcement_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建 AsyncIOScheduler，每 15 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="exchange_announcement_collect",
        )
        return scheduler

    def close(self):
        """释放资源。"""
        self.client.close()
