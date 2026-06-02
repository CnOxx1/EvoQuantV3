"""derivatives_sentiment_data 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.derivatives_sentiment_data.client import DerivativesSentimentDataClient


class DerivativesSentimentDataService:
    """衍生品情绪数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or DerivativesSentimentDataClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fear_greed_index INTEGER NOT NULL,
                fear_greed_class TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS derivatives_sentiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                btc_long_short_ratio REAL DEFAULT 0,
                eth_long_short_ratio REAL DEFAULT 0,
                total_open_interest_usd REAL DEFAULT 0,
                oi_change_24h REAL DEFAULT 0,
                estimated_leverage_ratio REAL DEFAULT 0,
                put_call_ratio REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(collected_at)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sentiment_index_collected
            ON sentiment_index(collected_at DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_derivatives_sentiment_collected
            ON derivatives_sentiment(collected_at DESC)
        """)
        self.db.conn.commit()
        logger.info("derivatives_sentiment_data 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 derivatives_sentiment_data bootstrap")
        self._collect_fear_greed()
        self._collect_derivatives_sentiment()
        logger.info("derivatives_sentiment_data bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_fear_greed()
        self._collect_derivatives_sentiment()
        logger.info("derivatives_sentiment_data collect_once 完成")

    def _collect_fear_greed(self):
        """采集恐惧与贪婪指数。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_fear_greed()

        if not data:
            logger.warning("Fear & Greed 未返回数据")
            return

        index_value = int(data.get("value", 0))
        classification = data.get("value_classification", "Unknown")

        self.db.conn.execute("""
            INSERT OR REPLACE INTO sentiment_index
            (fear_greed_index, fear_greed_class, collected_at)
            VALUES (?, ?, ?)
        """, (index_value, classification, now_iso))
        self.db.conn.commit()
        logger.info(f"Fear & Greed 采集完成: {index_value} ({classification})")

    def _collect_derivatives_sentiment(self):
        """采集衍生品情绪综合数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 多空比
        ls_data = self.client.fetch_long_short_ratios()
        btc_ls = float(ls_data.get("btc", {}).get("ratio", 0) if isinstance(ls_data, dict) else 0)
        eth_ls = float(ls_data.get("eth", {}).get("ratio", 0) if isinstance(ls_data, dict) else 0)

        # 全网 OI
        oi_data = self.client.fetch_open_interest_global()
        total_oi = float(oi_data.get("totalOpenInterest", 0) if isinstance(oi_data, dict) else 0)
        oi_change = float(oi_data.get("change24h", 0) if isinstance(oi_data, dict) else 0)
        leverage_ratio = float(oi_data.get("estimatedLeverageRatio", 0) if isinstance(oi_data, dict) else 0)

        # Put/Call 比率
        pc_data = self.client.fetch_put_call_ratio()
        pc_ratio = float(pc_data.get("putCallRatio", 0) if isinstance(pc_data, dict) else 0)

        self.db.conn.execute("""
            INSERT OR REPLACE INTO derivatives_sentiment
            (btc_long_short_ratio, eth_long_short_ratio, total_open_interest_usd,
             oi_change_24h, estimated_leverage_ratio, put_call_ratio, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (btc_ls, eth_ls, total_oi, oi_change, leverage_ratio, pc_ratio, now_iso))
        self.db.conn.commit()
        logger.info(f"衍生品情绪数据采集完成: OI=${total_oi:,.0f}, BTC L/S={btc_ls:.2f}")

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的衍生品情绪上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 最新 Fear & Greed
        cursor = self.db.conn.execute("""
            SELECT fear_greed_index, fear_greed_class, collected_at
            FROM sentiment_index
            ORDER BY collected_at DESC LIMIT 1
        """)
        fg_row = cursor.fetchone()

        # 最新衍生品情绪
        cursor = self.db.conn.execute("""
            SELECT btc_long_short_ratio, eth_long_short_ratio,
                   total_open_interest_usd, oi_change_24h,
                   estimated_leverage_ratio, put_call_ratio, collected_at
            FROM derivatives_sentiment
            ORDER BY collected_at DESC LIMIT 1
        """)
        ds_row = cursor.fetchone()

        if not fg_row and not ds_row:
            return {"status": "no_data", "as_of": now_iso}

        bundle = {"status": "ready", "as_of": now_iso, "sentiment": {}, "interpretation": {}}

        if fg_row:
            fg_index, fg_class, fg_at = fg_row
            bundle["sentiment"]["fear_greed"] = {
                "index": fg_index,
                "classification": fg_class,
                "collected_at": fg_at,
            }
            bundle["interpretation"]["fear_greed"] = self._interpret_fear_greed(fg_index, fg_class)

        if ds_row:
            btc_ls, eth_ls, total_oi, oi_chg, lev, pc, ds_at = ds_row
            bundle["sentiment"]["derivatives"] = {
                "btc_long_short_ratio": round(btc_ls, 4),
                "eth_long_short_ratio": round(eth_ls, 4),
                "total_open_interest_usd": round(total_oi, 2),
                "oi_change_24h_pct": round(oi_chg, 4),
                "estimated_leverage_ratio": round(lev, 4),
                "put_call_ratio": round(pc, 4),
                "collected_at": ds_at,
            }
            bundle["interpretation"]["long_short"] = self._interpret_long_short(btc_ls, eth_ls)
            bundle["interpretation"]["oi_trend"] = self._interpret_oi_trend(oi_chg)
            bundle["interpretation"]["leverage_risk"] = self._interpret_leverage_risk(lev)

        return bundle

    @staticmethod
    def _interpret_fear_greed(index: int, classification: str) -> str:
        """解读恐惧与贪婪指数。"""
        if index <= 20:
            return f"Extreme Fear ({index}/100) - 市场极度恐慌，可能存在超卖机会"
        elif index <= 40:
            return f"Fear ({index}/100) - 市场偏恐惧，投资者谨慎"
        elif index <= 60:
            return f"Neutral ({index}/100) - 市场情绪中性"
        elif index <= 80:
            return f"Greed ({index}/100) - 市场偏贪婪，注意过热风险"
        else:
            return f"Extreme Greed ({index}/100) - 市场极度贪婪，高度警惕回调风险"

    @staticmethod
    def _interpret_long_short(btc_ratio: float, eth_ratio: float) -> str:
        """解读多空比。"""
        signals = []
        if btc_ratio > 1.5:
            signals.append(f"BTC 多头主导 (L/S={btc_ratio:.2f})，市场看涨情绪强")
        elif btc_ratio < 0.7:
            signals.append(f"BTC 空头主导 (L/S={btc_ratio:.2f})，市场看跌情绪强")
        else:
            signals.append(f"BTC 多空均衡 (L/S={btc_ratio:.2f})")

        if eth_ratio > 1.5:
            signals.append(f"ETH 多头主导 (L/S={eth_ratio:.2f})")
        elif eth_ratio < 0.7:
            signals.append(f"ETH 空头主导 (L/S={eth_ratio:.2f})")
        else:
            signals.append(f"ETH 多空均衡 (L/S={eth_ratio:.2f})")

        return "; ".join(signals)

    @staticmethod
    def _interpret_oi_trend(oi_change_24h: float) -> str:
        """解读 OI 趋势。"""
        if oi_change_24h > 5:
            return f"OI 大幅上升 (+{oi_change_24h:.1f}%) - 投机活动剧增，杠杆风险上升"
        elif oi_change_24h > 2:
            return f"OI 上升 (+{oi_change_24h:.1f}%) - 投机情绪升温"
        elif oi_change_24h < -5:
            return f"OI 大幅下降 ({oi_change_24h:.1f}%) - 大规模去杠杆进行中"
        elif oi_change_24h < -2:
            return f"OI 下降 ({oi_change_24h:.1f}%) - 去杠杆化进行中"
        else:
            return f"OI 稳定 ({oi_change_24h:+.1f}%) - 市场杠杆水平平稳"

    @staticmethod
    def _interpret_leverage_risk(leverage_ratio: float) -> str:
        """解读杠杆风险。"""
        if leverage_ratio > 0.5:
            return f"高杠杆风险 (预估杠杆率={leverage_ratio:.3f}) - 连环清算风险极高"
        elif leverage_ratio > 0.3:
            return f"中等杠杆风险 (预估杠杆率={leverage_ratio:.3f}) - 需关注清算级联"
        elif leverage_ratio > 0.15:
            return f"低杠杆风险 (预估杠杆率={leverage_ratio:.3f}) - 市场杠杆在合理范围"
        else:
            return f"极低杠杆 (预估杠杆率={leverage_ratio:.3f}) - 市场去杠杆充分"

    def build_scheduler(self):
        """构建阻塞式调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="derivatives_sentiment_data_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        """构建异步调度器，每 15 分钟采集一次。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=15,
            id="derivatives_sentiment_data_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
