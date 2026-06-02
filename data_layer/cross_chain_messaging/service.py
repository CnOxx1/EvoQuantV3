"""cross_chain_messaging 服务层。"""

from datetime import datetime, timezone

from loguru import logger

from data_layer.cross_chain_messaging.client import CrossChainMessagingClient


class CrossChainMessagingService:
    """跨链消息协议数据采集与聚合服务。"""

    def __init__(self, client=None, db=None):
        if db is not None:
            self.db = db
        else:
            from database.router import DatabaseRouter, Domain
            self.db = DatabaseRouter().get_manager(Domain.MARKET_DATA)
        self.client = client or CrossChainMessagingClient()

    def init_storage(self):
        """初始化数据库表。"""
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_chain_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                src_chain TEXT NOT NULL,
                dst_chain TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                value_transferred_usd REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                avg_latency_seconds REAL DEFAULT 0,
                failure_rate REAL DEFAULT 0,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, src_chain, dst_chain, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE TABLE IF NOT EXISTS messaging_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                protocol TEXT NOT NULL,
                total_messages_24h INTEGER DEFAULT 0,
                total_value_24h_usd REAL DEFAULT 0,
                unique_chains INTEGER DEFAULT 0,
                avg_latency REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                UNIQUE(protocol, timestamp)
            )
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cross_chain_messages_time
            ON cross_chain_messages(protocol, timestamp DESC)
        """)
        self.db.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messaging_metrics_time
            ON messaging_metrics(protocol, timestamp DESC)
        """)
        self.db.conn.commit()
        logger.info("cross_chain_messaging 存储初始化完成")

    def bootstrap(self):
        """首次回填数据。"""
        logger.info("开始 bootstrap 跨链消息数据")
        self._collect_layerzero()
        self._collect_wormhole()
        self._collect_metrics()
        logger.info("bootstrap 完成")

    def collect_once(self):
        """执行一次采集周期。"""
        self._collect_layerzero()
        self._collect_wormhole()
        self._collect_metrics()
        logger.info("collect_once 完成")

    def _collect_layerzero(self):
        """采集 LayerZero 消息数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        stats = self.client.fetch_layerzero_stats()
        if not stats:
            return

        chains = stats.get("chains", stats.get("data", []))
        if isinstance(chains, list):
            for chain_data in chains[:20]:
                src = chain_data.get("srcChain", chain_data.get("chain", ""))
                dst = chain_data.get("dstChain", "multi")
                msg_count = int(chain_data.get("messageCount", 0) or 0)
                value = float(chain_data.get("valueUSD", 0) or 0)
                latency = float(chain_data.get("avgLatency", 0) or 0)
                failure = float(chain_data.get("failureRate", 0) or 0)

                self.db.conn.execute("""
                    INSERT OR REPLACE INTO cross_chain_messages
                    (protocol, src_chain, dst_chain, message_count,
                     value_transferred_usd, timestamp,
                     avg_latency_seconds, failure_rate, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, ("layerzero", src, dst, msg_count, value,
                      now_iso, latency, failure, now_iso))
        self.db.conn.commit()

    def _collect_wormhole(self):
        """采集 Wormhole 消息数据。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        stats = self.client.fetch_wormhole_stats()
        if not stats:
            return

        txs = stats if isinstance(stats, list) else stats.get("data", [])
        chain_pairs = {}
        for tx in txs[:100]:
            src = tx.get("emitterChain", tx.get("sourceChain", "unknown"))
            dst = tx.get("targetChain", tx.get("toChain", "unknown"))
            key = (str(src), str(dst))
            if key not in chain_pairs:
                chain_pairs[key] = {"count": 0, "value": 0.0}
            chain_pairs[key]["count"] += 1
            chain_pairs[key]["value"] += float(tx.get("usdAmount", 0) or 0)

        for (src, dst), data in chain_pairs.items():
            self.db.conn.execute("""
                INSERT OR REPLACE INTO cross_chain_messages
                (protocol, src_chain, dst_chain, message_count,
                 value_transferred_usd, timestamp,
                 avg_latency_seconds, failure_rate, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("wormhole", src, dst, data["count"], data["value"],
                  now_iso, 0.0, 0.0, now_iso))
        self.db.conn.commit()

    def _collect_metrics(self):
        """汇总各协议整体指标。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        for protocol in ("layerzero", "wormhole"):
            cursor = self.db.conn.execute("""
                SELECT SUM(message_count), SUM(value_transferred_usd),
                       COUNT(DISTINCT src_chain) + COUNT(DISTINCT dst_chain),
                       AVG(avg_latency_seconds)
                FROM cross_chain_messages
                WHERE protocol = ? AND timestamp >= datetime('now', '-1 day')
            """, (protocol,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                continue

            self.db.conn.execute("""
                INSERT OR REPLACE INTO messaging_metrics
                (protocol, total_messages_24h, total_value_24h_usd,
                 unique_chains, avg_latency, timestamp, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (protocol, int(row[0] or 0), float(row[1] or 0),
                  int(row[2] or 0), float(row[3] or 0), now_iso, now_iso))
        self.db.conn.commit()

    def load_latest_context_bundle(self) -> dict:
        """输出 AI 可读的跨链消息上下文 bundle。"""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        # 协议指标
        cursor = self.db.conn.execute("""
            SELECT protocol, total_messages_24h, total_value_24h_usd,
                   unique_chains, avg_latency
            FROM messaging_metrics
            ORDER BY timestamp DESC LIMIT 5
        """)
        metrics_rows = cursor.fetchall()

        # 热门链对
        cursor = self.db.conn.execute("""
            SELECT protocol, src_chain, dst_chain, message_count,
                   value_transferred_usd, avg_latency_seconds
            FROM cross_chain_messages
            WHERE timestamp >= datetime('now', '-1 day')
            ORDER BY message_count DESC LIMIT 15
        """)
        msg_rows = cursor.fetchall()

        if not metrics_rows and not msg_rows:
            return {"status": "no_data", "as_of": now_iso}

        protocol_metrics = {}
        for row in metrics_rows:
            protocol_metrics[row[0]] = {
                "total_messages_24h": row[1],
                "total_value_24h_usd": round(row[2], 2),
                "unique_chains": row[3],
                "avg_latency": round(row[4], 2),
            }

        top_routes = []
        for row in msg_rows:
            top_routes.append({
                "protocol": row[0],
                "src_chain": row[1],
                "dst_chain": row[2],
                "message_count": row[3],
                "value_transferred_usd": round(row[4], 2),
                "avg_latency_seconds": round(row[5], 2),
            })

        total_messages = sum(
            m.get("total_messages_24h", 0) for m in protocol_metrics.values()
        )
        total_value = sum(
            m.get("total_value_24h_usd", 0) for m in protocol_metrics.values()
        )

        return {
            "status": "ready",
            "as_of": now_iso,
            "window": "24h",
            "market_signal": {
                "total_cross_chain_messages": total_messages,
                "total_cross_chain_value_usd": round(total_value, 2),
                "protocols_tracked": list(protocol_metrics.keys()),
            },
            "protocol_metrics": protocol_metrics,
            "top_routes": top_routes[:10],
        }

    def build_scheduler(self):
        from apscheduler.schedulers.blocking import BlockingScheduler
        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=10,
            id="cross_chain_messaging_collect",
        )
        return scheduler

    def build_async_scheduler(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self.collect_once, "interval", minutes=10,
            id="cross_chain_messaging_collect",
        )
        return scheduler

    def close(self):
        self.client.close()
