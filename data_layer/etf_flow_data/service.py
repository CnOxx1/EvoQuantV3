"""etf_flow_data 服务层。"""

import statistics
from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.etf_flow_data.client import EtfFlowClient


TARGET_ASSETS = ["BTC", "ETH"]


class EtfFlowDataService:
    """ETF 资金流追踪采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or EtfFlowClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_daily_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                etf_name TEXT NOT NULL,
                asset TEXT NOT NULL,
                issuer TEXT NOT NULL,
                net_flow_usd REAL DEFAULT 0,
                total_aum_usd REAL DEFAULT 0,
                shares_outstanding REAL DEFAULT 0,
                price REAL DEFAULT 0,
                premium_discount_pct REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(date, etf_name, asset)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_flow_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                asset TEXT NOT NULL,
                total_net_flow_usd REAL DEFAULT 0,
                cumulative_net_flow_usd REAL DEFAULT 0,
                top_inflow_issuer TEXT DEFAULT '',
                top_outflow_issuer TEXT DEFAULT '',
                collected_at TEXT NOT NULL,
                UNIQUE(date, asset)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_etf_flows_date
            ON etf_daily_flows(date DESC, asset)
        """)
        self.db.conn.commit()
        logger.info("etf_flow_data 存储初始化完成")

    def bootstrap(self, assets: list[str] | None = None):
        """首次回填：拉取最近 30 天 ETF 数据。"""
        assets = assets or TARGET_ASSETS
        logger.info(f"开始 bootstrap，目标资产: {assets}")
        for asset in assets:
            self._collect_flows(asset, days=30)
        self._compute_summaries(assets)
        logger.info("bootstrap 完成")

    def collect_once(self, assets: list[str] | None = None):
        """执行一次采集周期。"""
        assets = assets or TARGET_ASSETS
        for asset in assets:
            self._collect_flows(asset, days=7)
        self._compute_summaries(assets)
        logger.info(f"collect_once 完成，处理 {len(assets)} 个资产")

    def _collect_flows(self, asset: str, days: int = 7):
        """采集 ETF 资金流数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        flows = self.client.fetch_etf_flows(asset=asset, days=days)
        for item in flows:
            date = item.get("date", "")
            etf_name = item.get("etf_name", item.get("ticker", ""))
            if not date or not etf_name:
                continue
            self.db.conn.execute("""
                INSERT OR REPLACE INTO etf_daily_flows
                (date, etf_name, asset, issuer, net_flow_usd, total_aum_usd,
                 shares_outstanding, price, premium_discount_pct, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date, etf_name, asset,
                item.get("issuer", "unknown"),
                float(item.get("net_flow_usd", 0)),
                float(item.get("total_aum_usd", 0)),
                float(item.get("shares_outstanding", 0)),
                float(item.get("price", 0)),
                float(item.get("premium_discount_pct", 0)),
                now_iso,
            ))
        self.db.conn.commit()

    def _compute_summaries(self, assets: list[str]):
        """计算每日汇总。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for asset in assets:
            cursor = self.db.conn.execute("""
                SELECT date, SUM(net_flow_usd) as total_flow,
                       issuer, net_flow_usd
                FROM etf_daily_flows
                WHERE asset = ?
                GROUP BY date
                ORDER BY date DESC LIMIT 30
            """, (asset,))
            rows = cursor.fetchall()
            cumulative = 0.0
            for row in rows:
                date = row[0]
                total_flow = row[1] or 0.0
                cumulative += total_flow
                # 找最大流入/流出 issuer
                inflow_cursor = self.db.conn.execute("""
                    SELECT issuer FROM etf_daily_flows
                    WHERE asset = ? AND date = ?
                    ORDER BY net_flow_usd DESC LIMIT 1
                """, (asset, date))
                top_in = inflow_cursor.fetchone()
                outflow_cursor = self.db.conn.execute("""
                    SELECT issuer FROM etf_daily_flows
                    WHERE asset = ? AND date = ?
                    ORDER BY net_flow_usd ASC LIMIT 1
                """, (asset, date))
                top_out = outflow_cursor.fetchone()
                self.db.conn.execute("""
                    INSERT OR REPLACE INTO etf_flow_summary
                    (date, asset, total_net_flow_usd, cumulative_net_flow_usd,
                     top_inflow_issuer, top_outflow_issuer, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    date, asset, total_flow, cumulative,
                    top_in[0] if top_in else "",
                    top_out[0] if top_out else "",
                    now_iso,
                ))
            self.db.conn.commit()

    def load_latest_context_bundle(self, assets: list[str] | None = None) -> dict:
        """输出 AI 可读的 ETF 资金流上下文 bundle。"""
        assets = assets or TARGET_ASSETS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        result = {"status": "ready", "as_of": now_iso, "assets": {}}

        for asset in assets:
            cursor = self.db.conn.execute("""
                SELECT date, total_net_flow_usd, cumulative_net_flow_usd,
                       top_inflow_issuer, top_outflow_issuer
                FROM etf_flow_summary
                WHERE asset = ? ORDER BY date DESC LIMIT 7
            """, (asset,))
            rows = cursor.fetchall()
            if not rows:
                result["assets"][asset] = {"status": "no_data"}
                continue

            daily_flows = [row[1] for row in rows]
            consecutive_inflow = 0
            for f in daily_flows:
                if f > 0:
                    consecutive_inflow += 1
                else:
                    break
            consecutive_outflow = 0
            for f in daily_flows:
                if f < 0:
                    consecutive_outflow += 1
                else:
                    break

            # Z-score 异常检测
            z_score = None
            if len(daily_flows) >= 3:
                mean_flow = statistics.mean(daily_flows)
                std_flow = statistics.stdev(daily_flows) if len(daily_flows) > 1 else 1
                if std_flow > 0:
                    z_score = round((daily_flows[0] - mean_flow) / std_flow, 2)

            result["assets"][asset] = {
                "latest_date": rows[0][0],
                "latest_net_flow_usd": rows[0][1],
                "cumulative_net_flow_usd": rows[0][2],
                "top_inflow_issuer": rows[0][3],
                "top_outflow_issuer": rows[0][4],
                "trend_7d": daily_flows,
                "consecutive_inflow_days": consecutive_inflow,
                "consecutive_outflow_days": consecutive_outflow,
                "anomaly_z_score": z_score,
            }
        return result

    def build_scheduler(self, assets: list[str] | None = None):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "cron", hour=22, minute=0,
            kwargs={"assets": assets}, id="etf_flow_collect",
        )
        return scheduler

    def build_async_scheduler(self, assets: list[str] | None = None):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "cron", hour=22, minute=0,
            kwargs={"assets": assets}, id="etf_flow_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
