"""search_trend_data 服务层。"""

from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.search_trend_data.client import SearchTrendClient


class SearchTrendDataService:
    """搜索趋势数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or SearchTrendClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS search_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                interest_score INTEGER DEFAULT 0,
                interest_change_7d REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                category TEXT DEFAULT 'crypto',
                collected_at TEXT NOT NULL,
                UNIQUE(keyword, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS trend_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                interest_score INTEGER DEFAULT 0,
                date TEXT NOT NULL,
                category TEXT DEFAULT 'crypto',
                collected_at TEXT NOT NULL,
                UNIQUE(keyword, date)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_trends_time
            ON search_trends(timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trend_history_kw
            ON trend_history(keyword, date DESC)
        """)
        self.db.conn.commit()
        logger.info("search_trend_data 存储初始化完成")

    def bootstrap(self):
        """首次回填趋势数据。"""
        logger.info("开始 search_trend_data bootstrap")
        self.collect_once()
        logger.info("search_trend_data bootstrap 完成")

    def collect_once(self):
        """执行一次完整采集周期。"""
        self._collect_crypto_trends()
        self._collect_keyword_interest()
        logger.info("search_trend_data collect_once 完成")

    def _collect_crypto_trends(self):
        """采集加密货币趋势时间序列。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        trends_data = self.client.fetch_crypto_trends()
        if not trends_data:
            return

        for keyword, time_series in trends_data.items():
            if not isinstance(time_series, dict):
                continue
            for ts, score in time_series.items():
                date_str = str(ts)[:10]
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO trend_history
                    (keyword, interest_score, date, category, collected_at)
                    VALUES (?, ?, ?, 'crypto', ?)
                """, (keyword, int(score), date_str, now_iso))
        self.db.conn.commit()

    def _collect_keyword_interest(self):
        """采集关键词当前兴趣度。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        keywords = SearchTrendClient.DEFAULT_KEYWORDS
        scores = self.client.fetch_keyword_interest(keywords)
        if not scores:
            return

        for keyword, score in scores.items():
            # 计算7日变化
            change_7d = self._compute_7d_change(keyword, score)
            self.db.conn.execute("""
                INSERT OR REPLACE INTO search_trends
                (keyword, interest_score, interest_change_7d,
                 timestamp, category, collected_at)
                VALUES (?, ?, ?, ?, 'crypto', ?)
            """, (keyword, score, change_7d, now_iso, now_iso))
        self.db.conn.commit()

    def _compute_7d_change(self, keyword: str, current_score: int) -> float:
        """计算关键词7日兴趣度变化率。"""
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        cursor = self.db.conn.execute("""
            SELECT interest_score FROM trend_history
            WHERE keyword = ? AND date <= ?
            ORDER BY date DESC LIMIT 1
        """, (keyword, week_ago))
        row = cursor.fetchone()
        if row and row[0] > 0:
            return round((current_score - row[0]) / row[0], 4)
        return 0.0

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的搜索趋势上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        cursor = self.db.conn.execute("""
            SELECT keyword, interest_score, interest_change_7d, timestamp
            FROM search_trends
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY interest_score DESC
        """)
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        trends = {}
        for row in rows:
            keyword = row[0]
            if keyword not in trends:
                trends[keyword] = {
                    "interest_score": row[1],
                    "change_7d": round(row[2], 4),
                    "last_updated": row[3],
                }

        # 热度排名
        sorted_keywords = sorted(
            trends.items(), key=lambda x: x[1]["interest_score"], reverse=True
        )
        trending_up = [k for k, v in sorted_keywords if v["change_7d"] > 0.1]
        trending_down = [k for k, v in sorted_keywords if v["change_7d"] < -0.1]

        return {
            "status": "ready",
            "as_of": now_iso,
            "trends": trends,
            "signals": {
                "trending_up": trending_up,
                "trending_down": trending_down,
            },
            "coverage": {
                "keywords_tracked": len(trends),
            },
        }

    def build_scheduler(self):
        """构建 BlockingScheduler，每 4 小时采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", seconds=14400,
            id="search_trend_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建 AsyncIOScheduler，每 4 小时采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", seconds=14400,
            id="search_trend_data_collect",
        )
        return scheduler

    def close(self):
        """释放资源。"""
        self.client.close()
