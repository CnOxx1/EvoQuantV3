"""social_sentiment_data 服务层。"""

import json
import statistics
from datetime import datetime, timezone, timedelta

from loguru import logger

from data_layer.social_sentiment_data.client import SocialSentimentClient
from data_layer.social_sentiment_data.models import SentimentAggregation


# symbol → santiment slug 映射
SYMBOL_SLUG_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ARB": "arbitrum",
    "OP": "optimism",
    "APT": "aptos",
}

TARGET_SYMBOLS = list(SYMBOL_SLUG_MAP.keys())


class SocialSentimentDataService:
    """社交情绪数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or SocialSentimentClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS social_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                entity_key TEXT NOT NULL,
                mention_time TEXT NOT NULL,
                author_tier TEXT DEFAULT 'retail',
                content_hash TEXT NOT NULL,
                sentiment_score REAL DEFAULT 0.0,
                engagement INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0,
                raw_text_snippet TEXT,
                collected_at TEXT NOT NULL,
                UNIQUE(platform, content_hash)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS social_sentiment_agg (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_key TEXT NOT NULL,
                platform TEXT NOT NULL,
                interval TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                mention_count INTEGER DEFAULT 0,
                avg_sentiment REAL DEFAULT 0.0,
                weighted_sentiment REAL DEFAULT 0.0,
                bullish_ratio REAL DEFAULT 0.0,
                bearish_ratio REAL DEFAULT 0.0,
                kol_sentiment REAL DEFAULT 0.0,
                volume_zscore REAL DEFAULT 0.0,
                collected_at TEXT NOT NULL,
                UNIQUE(entity_key, platform, interval, window_start)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_mentions_entity_time
            ON social_mentions(entity_key, mention_time DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_social_agg_entity_time
            ON social_sentiment_agg(entity_key, window_start DESC)
        """)
        self.db.conn.commit()
        logger.info("social_sentiment_data 存储初始化完成")

    def bootstrap(self, symbols: list[str] | None = None):
        """首次回填：拉取最近 7 天的社交数据。"""
        symbols = symbols or TARGET_SYMBOLS
        logger.info(f"开始 bootstrap，目标: {symbols}")
        now = datetime.now(timezone.utc)
        from_dt = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_dt = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for symbol in symbols:
            slug = SYMBOL_SLUG_MAP.get(symbol, symbol.lower())
            self._collect_santiment(symbol, slug, from_dt, to_dt)
            self._collect_lunarcrush(symbol)
        logger.info("bootstrap 完成")

    def collect_once(self, symbols: list[str] | None = None):
        """执行一次采集周期。"""
        symbols = symbols or TARGET_SYMBOLS
        now = datetime.now(timezone.utc)
        from_dt = (now - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_dt = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for symbol in symbols:
            slug = SYMBOL_SLUG_MAP.get(symbol, symbol.lower())
            self._collect_santiment(symbol, slug, from_dt, to_dt)
            self._collect_lunarcrush(symbol)
        self._compute_aggregations(symbols)
        logger.info(f"collect_once 完成，处理 {len(symbols)} 个标的")

    def _collect_santiment(self, symbol: str, slug: str, from_dt: str, to_dt: str):
        """采集 Santiment 社交量和情绪数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        volume_data = self.client.fetch_santiment_social_volume(slug, from_dt, to_dt)
        sentiment_data = self.client.fetch_santiment_sentiment(slug, from_dt, to_dt)

        # 合并为聚合记录
        sent_map = {r["datetime"]: r["value"] for r in sentiment_data}
        for row in volume_data:
            dt = row["datetime"]
            mention_count = int(row.get("value", 0))
            sentiment_val = sent_map.get(dt, 0.0)
            # 归一化 sentiment 到 -1~1 范围
            norm_sentiment = max(-1.0, min(1.0, sentiment_val / 5.0)) if sentiment_val else 0.0

            self.db.conn.execute("""
                INSERT OR REPLACE INTO social_sentiment_agg
                (entity_key, platform, interval, window_start, window_end,
                 mention_count, avg_sentiment, weighted_sentiment,
                 bullish_ratio, bearish_ratio, kol_sentiment, volume_zscore, collected_at)
                VALUES (?, 'santiment', '1h', ?, ?, ?, ?, ?, 0, 0, 0, 0, ?)
            """, (symbol, dt, dt, mention_count, norm_sentiment, norm_sentiment, now_iso))
        self.db.conn.commit()

    def _collect_lunarcrush(self, symbol: str):
        """采集 LunarCrush 社交指标。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        data = self.client.fetch_lunarcrush_social(symbol)
        for row in data:
            ts = row.get("time", "")
            if not ts:
                continue
            self.db.conn.execute("""
                INSERT OR REPLACE INTO social_sentiment_agg
                (entity_key, platform, interval, window_start, window_end,
                 mention_count, avg_sentiment, weighted_sentiment,
                 bullish_ratio, bearish_ratio, kol_sentiment, volume_zscore, collected_at)
                VALUES (?, 'lunarcrush', '1d', ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            """, (
                symbol, ts, ts,
                row.get("posts_total", 0),
                row.get("sentiment", 0.0),
                row.get("sentiment", 0.0),
                row.get("bullish", 0.0),
                row.get("bearish", 0.0),
                now_iso,
            ))
        self.db.conn.commit()

    def _compute_aggregations(self, symbols: list[str]):
        """基于原始数据计算聚合指标。"""
        now = datetime.now(timezone.utc)
        window_start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

        for symbol in symbols:
            cursor = self.db.conn.execute("""
                SELECT mention_count, avg_sentiment FROM social_sentiment_agg
                WHERE entity_key = ? AND window_start >= ?
                ORDER BY window_start DESC
            """, (symbol, window_start))
            rows = cursor.fetchall()
            if not rows:
                continue

            counts = [r[0] for r in rows]
            sentiments = [r[1] for r in rows]
            mean_count = statistics.mean(counts) if counts else 0
            std_count = statistics.stdev(counts) if len(counts) > 1 else 1
            latest_zscore = (counts[0] - mean_count) / std_count if std_count > 0 else 0

            # 更新最新记录的 volume_zscore
            self.db.conn.execute("""
                UPDATE social_sentiment_agg SET volume_zscore = ?
                WHERE entity_key = ? AND window_start = (
                    SELECT MAX(window_start) FROM social_sentiment_agg WHERE entity_key = ?
                )
            """, (latest_zscore, symbol, symbol))
        self.db.conn.commit()

    def load_latest_context_bundle(self, symbols: list[str] | None = None) -> dict:
        """输出 AI 可读的社交情绪上下文 bundle。"""
        symbols = symbols or TARGET_SYMBOLS
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        window_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

        placeholders = ",".join("?" * len(symbols))
        cursor = self.db.conn.execute(f"""
            SELECT entity_key, platform, interval, window_start,
                   mention_count, avg_sentiment, weighted_sentiment,
                   bullish_ratio, bearish_ratio, kol_sentiment, volume_zscore
            FROM social_sentiment_agg
            WHERE entity_key IN ({placeholders}) AND window_start >= ?
            ORDER BY entity_key, window_start DESC
        """, (*symbols, window_24h))
        rows = cursor.fetchall()

        if not rows:
            return {"status": "no_data", "as_of": now_iso}

        # 按 entity 聚合
        entity_data = {}
        for row in rows:
            key = row[0]
            if key not in entity_data:
                entity_data[key] = []
            entity_data[key].append({
                "platform": row[1],
                "interval": row[2],
                "window_start": row[3],
                "mention_count": row[4],
                "avg_sentiment": round(row[5], 4),
                "weighted_sentiment": round(row[6], 4),
                "bullish_ratio": round(row[7], 4),
                "bearish_ratio": round(row[8], 4),
                "kol_sentiment": round(row[9], 4),
                "volume_zscore": round(row[10], 4),
            })

        # 生成摘要
        summaries = {}
        for entity, records in entity_data.items():
            sentiments = [r["avg_sentiment"] for r in records]
            counts = [r["mention_count"] for r in records]
            avg_sent = statistics.mean(sentiments) if sentiments else 0
            total_mentions = sum(counts)
            max_zscore = max((r["volume_zscore"] for r in records), default=0)

            if avg_sent > 0.3:
                mood = "bullish"
            elif avg_sent < -0.3:
                mood = "bearish"
            else:
                mood = "neutral"

            summaries[entity] = {
                "mood": mood,
                "avg_sentiment_24h": round(avg_sent, 4),
                "total_mentions_24h": total_mentions,
                "volume_zscore_peak": round(max_zscore, 2),
                "data_points": len(records),
                "latest": records[0] if records else None,
            }

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "coverage": {
                "symbols_with_data": len(entity_data),
                "symbols_requested": len(symbols),
            },
            "summaries": summaries,
            "raw_row_count": len(rows),
        }

    def build_scheduler(self, symbols: list[str] | None = None):
        """构建 BlockingScheduler。"""
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once,
            "interval",
            minutes=30,
            kwargs={"symbols": symbols},
            id="social_sentiment_collect",
        )
        return scheduler

    def build_async_scheduler(self, symbols: list[str] | None = None):
        """构建 AsyncIOScheduler。"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once,
            "interval",
            minutes=30,
            kwargs={"symbols": symbols},
            id="social_sentiment_collect",
        )
        return scheduler

    def close(self):
        """释放资源。"""
        self.client.close()
