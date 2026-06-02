"""funding_round_data 服务层。"""

from collections import defaultdict
from datetime import datetime, timezone

from loguru import logger

from data_layer.funding_round_data.client import FundingRoundDataClient


class FundingRoundDataService:
    """融资轮次数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or FundingRoundDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                round_type TEXT NOT NULL,
                amount_usd REAL DEFAULT 0,
                valuation REAL DEFAULT 0,
                lead_investors TEXT DEFAULT '',
                date TEXT NOT NULL,
                category TEXT DEFAULT '',
                chain TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(project, date, round_type)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS investor_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investor TEXT NOT NULL,
                rounds_count INTEGER DEFAULT 0,
                total_invested_usd REAL DEFAULT 0,
                categories TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(investor, collected_at)
            )
        """)
        self.db.conn.commit()
        logger.info("funding_round_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 funding_round_data bootstrap")
        self._collect_rounds(days=90)
        self._collect_investor_activity()
        logger.info("funding_round_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_rounds(days=30)
        self._collect_investor_activity()
        logger.info("funding_round_data collect_once 完成")

    def _collect_rounds(self, days: int = 30):
        """采集最近融资轮次数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        rounds = self.client.fetch_recent_rounds(days=days)

        if not rounds:
            logger.warning("DefiLlama 未返回融资轮次数据")
            return

        for item in rounds:
            project = item.get("name", "") or ""
            if not project:
                continue

            round_type = item.get("round", "") or "unknown"
            amount_usd = float(item.get("amount", 0) or 0) * 1_000_000
            valuation = float(item.get("valuation", 0) or 0) * 1_000_000

            investors = item.get("leadInvestors", []) or []
            if not investors:
                investors = item.get("investors", []) or []
            lead_investors = ", ".join(investors) if isinstance(investors, list) else str(investors)

            date_ts = item.get("date")
            if date_ts:
                date_str = datetime.fromtimestamp(
                    date_ts, tz=timezone.utc
                ).strftime("%Y-%m-%d")
            else:
                date_str = ""

            category = item.get("category", "") or ""
            chain = ", ".join(item.get("chains", [])) if item.get("chains") else ""

            self.db.conn.execute("""
                INSERT OR REPLACE INTO funding_rounds
                (project, round_type, amount_usd, valuation, lead_investors,
                 date, category, chain, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (project, round_type, amount_usd, valuation,
                  lead_investors, date_str, category, chain, now_iso))

        self.db.conn.commit()
        logger.info(f"融资轮次采集完成，处理 {len(rounds)} 条记录")

    def _collect_investor_activity(self):
        """聚合投资者活动数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        all_raises = self.client.fetch_investor_activity()

        if not all_raises:
            logger.warning("DefiLlama 未返回投资者活动数据")
            return

        investor_map = defaultdict(lambda: {
            "rounds_count": 0,
            "total_invested_usd": 0.0,
            "categories": set(),
        })

        for item in all_raises:
            amount = float(item.get("amount", 0) or 0) * 1_000_000
            category = item.get("category", "") or ""
            investors = item.get("leadInvestors", []) or []
            if not investors:
                investors = item.get("investors", []) or []
            if not isinstance(investors, list):
                continue

            per_investor_amount = amount / len(investors) if investors else 0

            for inv in investors:
                if not inv:
                    continue
                investor_map[inv]["rounds_count"] += 1
                investor_map[inv]["total_invested_usd"] += per_investor_amount
                if category:
                    investor_map[inv]["categories"].add(category)

        for investor, stats in investor_map.items():
            categories_str = ", ".join(sorted(stats["categories"]))
            self.db.conn.execute("""
                INSERT OR REPLACE INTO investor_activity
                (investor, rounds_count, total_invested_usd, categories, collected_at)
                VALUES (?, ?, ?, ?, ?)
            """, (investor, stats["rounds_count"],
                  round(stats["total_invested_usd"], 2),
                  categories_str, now_iso))

        self.db.conn.commit()
        logger.info(f"投资者活动聚合完成，处理 {len(investor_map)} 个投资者")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的融资轮次上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 按类别聚合融资数据
        cursor = self.db.conn.execute("""
            SELECT category, COUNT(*) as round_count,
                   SUM(amount_usd) as total_amount,
                   AVG(amount_usd) as avg_amount
            FROM funding_rounds
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM funding_rounds
            )
            GROUP BY category
            ORDER BY total_amount DESC
        """)
        category_rows = cursor.fetchall()

        if not category_rows:
            return {"status": "no_data", "as_of": now_iso}

        category_breakdown = []
        for row in category_rows:
            cat, count, total, avg = row
            category_breakdown.append({
                "category": cat or "unknown",
                "rounds_count": count,
                "total_amount_usd": round(total or 0, 2),
                "avg_amount_usd": round(avg or 0, 2),
            })

        # 最近的大额融资
        large_cursor = self.db.conn.execute("""
            SELECT project, round_type, amount_usd, valuation,
                   lead_investors, date, category, chain
            FROM funding_rounds
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM funding_rounds
            )
            ORDER BY amount_usd DESC
            LIMIT 15
        """)
        large_rows = large_cursor.fetchall()
        recent_large_rounds = []
        for row in large_rows:
            proj, rtype, amt, val, leads, dt, cat, ch = row
            recent_large_rounds.append({
                "project": proj,
                "round_type": rtype,
                "amount_usd": round(amt, 2),
                "valuation": round(val, 2) if val else None,
                "lead_investors": leads,
                "date": dt,
                "category": cat,
                "chain": ch,
            })

        # 顶级投资者活动
        inv_cursor = self.db.conn.execute("""
            SELECT investor, rounds_count, total_invested_usd, categories
            FROM investor_activity
            WHERE collected_at = (
                SELECT MAX(collected_at) FROM investor_activity
            )
            ORDER BY total_invested_usd DESC
            LIMIT 20
        """)
        inv_rows = inv_cursor.fetchall()
        top_investors = []
        for row in inv_rows:
            inv, count, total, cats = row
            top_investors.append({
                "investor": inv,
                "rounds_count": count,
                "total_invested_usd": round(total, 2),
                "categories": cats,
            })

        return {
            "status": "ready",
            "as_of": now_iso,
            "funding_trends": {
                "hot_sectors": category_breakdown,
                "recent_large_rounds": recent_large_rounds,
                "top_vc_activity": top_investors,
            },
            "interpretation": {
                "hot_sectors": "按类别聚合的融资趋势，反映市场热点方向",
                "large_rounds": "近期大额融资项目，反映资本流向",
                "top_vcs": "最活跃投资机构及其偏好类别",
            },
        }

    def build_scheduler(self):
        """构建阻塞式调度器，每 1440 分钟（每日）采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=1440,
            id="funding_round_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 1440 分钟（每日）采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=1440,
            id="funding_round_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
