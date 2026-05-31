"""regulatory_data 服务层。"""

import hashlib
from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.regulatory_data.client import RegulatoryDataClient


# 已知 ETF 追踪列表
TRACKED_ETFS = [
    {"etf_name": "iShares Bitcoin Trust", "asset": "BTC", "jurisdiction": "US", "applicant": "BlackRock"},
    {"etf_name": "Wise Origin Bitcoin Fund", "asset": "BTC", "jurisdiction": "US", "applicant": "Fidelity"},
    {"etf_name": "ARK 21Shares Bitcoin ETF", "asset": "BTC", "jurisdiction": "US", "applicant": "ARK/21Shares"},
    {"etf_name": "iShares Ethereum Trust", "asset": "ETH", "jurisdiction": "US", "applicant": "BlackRock"},
    {"etf_name": "Fidelity Ethereum Fund", "asset": "ETH", "jurisdiction": "US", "applicant": "Fidelity"},
    {"etf_name": "Solana ETF", "asset": "SOL", "jurisdiction": "US", "applicant": "VanEck"},
    {"etf_name": "XRP ETF", "asset": "XRP", "jurisdiction": "US", "applicant": "Bitwise"},
]


class RegulatoryDataService:
    """监管动态数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or RegulatoryDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS regulatory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                jurisdiction TEXT NOT NULL,
                regulator TEXT DEFAULT '',
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                impact_scope TEXT DEFAULT 'market_wide',
                impact_severity TEXT DEFAULT 'medium',
                affected_assets TEXT DEFAULT '',
                event_date TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                collected_at TEXT NOT NULL
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_tracker (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                etf_name TEXT NOT NULL,
                asset TEXT NOT NULL,
                jurisdiction TEXT NOT NULL,
                applicant TEXT NOT NULL,
                status TEXT DEFAULT 'under_review',
                filing_date TEXT,
                decision_deadline TEXT,
                last_update TEXT NOT NULL,
                notes TEXT DEFAULT '',
                UNIQUE(etf_name, applicant)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_reg_events_date
            ON regulatory_events(event_date DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_etf_tracker_asset
            ON etf_tracker(asset, status)
        """)
        self.db.conn.commit()
        logger.info("regulatory_data 存储初始化完成")

    def bootstrap(self):
        """首次回填：初始化 ETF 追踪列表并拉取近期监管新闻。"""
        logger.info("开始 bootstrap")
        self._init_etf_tracker()
        self._collect_regulatory_news()
        logger.info("bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_regulatory_news()
        logger.info("collect_once 完成")

    def _init_etf_tracker(self):
        """初始化 ETF 追踪列表。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for etf in TRACKED_ETFS:
            self.db.conn.execute("""
                INSERT OR IGNORE INTO etf_tracker
                (etf_name, asset, jurisdiction, applicant, status, last_update)
                VALUES (?, ?, ?, ?, 'under_review', ?)
            """, (etf["etf_name"], etf["asset"], etf["jurisdiction"],
                  etf["applicant"], now_iso))
        self.db.conn.commit()

    def _collect_regulatory_news(self):
        """采集监管类新闻并分类存储。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        articles = self.client.fetch_regulatory_news()

        for article in articles:
            title = article.get("title", "")
            body = article.get("body", "")
            url = article.get("url", "")
            published = article.get("published_on", 0)

            if not title:
                continue

            event_id = hashlib.md5(f"{title}_{published}".encode()).hexdigest()
            event_date = datetime.fromtimestamp(
                published, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S") if published else now_iso

            # 推断事件类型和严重程度
            event_type = self._classify_event_type(title, body)
            severity = self._classify_severity(title, body)
            jurisdiction = self._infer_jurisdiction(title, body)
            affected = self._infer_affected_assets(title, body)

            self.db.conn.execute("""
                INSERT OR IGNORE INTO regulatory_events
                (event_id, jurisdiction, regulator, event_type, title, summary,
                 impact_scope, impact_severity, affected_assets, event_date,
                 source_url, collected_at)
                VALUES (?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, jurisdiction, event_type, title,
                body[:500] if body else "",
                "market_wide" if not affected else "sector",
                severity, affected, event_date, url, now_iso,
            ))
        self.db.conn.commit()

    @staticmethod
    def _classify_event_type(title: str, body: str) -> str:
        text = (title + " " + body).lower()
        if any(w in text for w in ["enforcement", "fine", "penalty", "sue", "charged"]):
            return "enforcement"
        if any(w in text for w in ["etf", "fund approval", "spot etf"]):
            return "etf_decision"
        if any(w in text for w in ["bill", "legislation", "law", "act"]):
            return "legislation"
        if any(w in text for w in ["guidance", "framework", "proposal", "rule"]):
            return "guidance"
        if any(w in text for w in ["license", "registration", "permit"]):
            return "license"
        return "general"

    @staticmethod
    def _classify_severity(title: str, body: str) -> str:
        text = (title + " " + body).lower()
        high_keywords = ["ban", "criminal", "fraud", "shutdown", "emergency", "systemic"]
        medium_keywords = ["fine", "enforcement", "restriction", "delay", "reject"]
        if any(w in text for w in high_keywords):
            return "high"
        if any(w in text for w in medium_keywords):
            return "medium"
        return "low"

    @staticmethod
    def _infer_jurisdiction(title: str, body: str) -> str:
        text = (title + " " + body).lower()
        if any(w in text for w in ["sec", "cftc", "us ", "united states", "american"]):
            return "US"
        if any(w in text for w in ["eu ", "europe", "mica", "esma"]):
            return "EU"
        if any(w in text for w in ["china", "pboc", "chinese"]):
            return "CN"
        if any(w in text for w in ["uk ", "fca", "britain"]):
            return "UK"
        if any(w in text for w in ["japan", "jfsa"]):
            return "JP"
        if any(w in text for w in ["korea", "fsc"]):
            return "KR"
        return "global"

    @staticmethod
    def _infer_affected_assets(title: str, body: str) -> str:
        text = (title + " " + body).upper()
        assets = []
        for symbol in ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE"]:
            if symbol in text:
                assets.append(symbol)
        # 也检查全名
        name_map = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "RIPPLE": "XRP"}
        for name, sym in name_map.items():
            if name in text and sym not in assets:
                assets.append(sym)
        return ",".join(assets)

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的监管动态上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")

        # 近 7 天监管事件
        cursor = self.db.conn.execute("""
            SELECT jurisdiction, event_type, title, impact_severity,
                   affected_assets, event_date
            FROM regulatory_events
            WHERE event_date >= ?
            ORDER BY event_date DESC
            LIMIT 30
        """, (week_ago,))
        events = cursor.fetchall()

        # ETF 状态
        cursor = self.db.conn.execute("""
            SELECT etf_name, asset, jurisdiction, applicant, status, last_update
            FROM etf_tracker
            ORDER BY asset, applicant
        """)
        etf_rows = cursor.fetchall()

        if not events and not etf_rows:
            return {"status": "no_data", "as_of": now_iso}

        # 事件摘要
        event_list = []
        high_severity_count = 0
        for row in events:
            if row[3] == "high":
                high_severity_count += 1
            event_list.append({
                "jurisdiction": row[0],
                "type": row[1],
                "title": row[2],
                "severity": row[3],
                "affected_assets": row[4],
                "date": row[5],
            })

        # ETF 摘要
        etf_list = []
        for row in etf_rows:
            etf_list.append({
                "name": row[0],
                "asset": row[1],
                "jurisdiction": row[2],
                "applicant": row[3],
                "status": row[4],
                "last_update": row[5],
            })

        # 风险信号
        if high_severity_count >= 3:
            risk_level = "elevated"
        elif high_severity_count >= 1:
            risk_level = "moderate"
        else:
            risk_level = "low"

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "7d",
            "risk_signal": {
                "regulatory_risk_level": risk_level,
                "high_severity_events_7d": high_severity_count,
                "total_events_7d": len(events),
            },
            "recent_events": event_list[:10],
            "etf_tracker": etf_list,
            "coverage": {
                "events_count": len(events),
                "etf_tracked": len(etf_list),
            },
        }

    def build_scheduler(self):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=2,
            id="regulatory_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", hours=2,
            id="regulatory_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
